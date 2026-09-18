import json
import socket
import uuid

import pytest

from inspector.supervisor import ProxySupervisor


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_accepting(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def _port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _llamacpp_service(port: int, alias: str = "a", **extra) -> dict:
    cfg = {
        "template_type": "llamacpp",
        "alias": alias,
        "port": port,
        "model_path": "/models/a.gguf",
        "api_key": "key-test",
        "params": {},
    }
    cfg.update(extra)
    return cfg


def _write_services(tmp_path, services):
    (tmp_path / "services.json").write_text(json.dumps(services))


@pytest.fixture
def env(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n")
    sup = ProxySupervisor(
        compose_path=str(compose), db_path=str(tmp_path / "inspector.db")
    )
    yield sup, tmp_path
    sup.stop_all()


class TestSync:
    def test_starts_proxy_per_inspected_service(self, env):
        sup, tmp_path = env
        port = _free_port()
        _write_services(tmp_path, {"svc-a": _llamacpp_service(port, inspect=True, inspect_upstream_port=34000)})

        sup.sync()

        rows = sup.status()
        assert len(rows) == 1
        assert rows[0]["service"] == "svc-a"
        assert rows[0]["listen_port"] == port
        assert rows[0]["upstream_port"] == 34000
        assert rows[0]["running"] is True
        assert rows[0]["error"] is None
        assert _port_accepting(port)

    def test_no_proxy_without_inspect_and_no_db_file(self, env):
        sup, tmp_path = env
        _write_services(tmp_path, {"svc-a": _llamacpp_service(_free_port())})

        sup.sync()

        assert sup.status() == []
        assert not (tmp_path / "inspector.db").exists()

    def test_sync_is_idempotent(self, env):
        sup, tmp_path = env
        port = _free_port()
        _write_services(tmp_path, {"svc-a": _llamacpp_service(port, inspect=True, inspect_upstream_port=34000)})

        sup.sync()
        first = sup._proxies["svc-a"]
        sup.sync()

        assert sup._proxies["svc-a"] is first
        assert len(sup.status()) == 1
        assert sup.status()[0]["running"] is True

    def test_stops_proxy_when_inspect_removed(self, env):
        sup, tmp_path = env
        port = _free_port()
        cfg = _llamacpp_service(port, inspect=True, inspect_upstream_port=34000)
        _write_services(tmp_path, {"svc-a": cfg})
        sup.sync()
        assert _port_accepting(port)

        cfg["inspect"] = False
        _write_services(tmp_path, {"svc-a": cfg})
        sup.sync()

        assert sup.status() == []
        assert _port_free(port)

    def test_stops_proxy_when_service_deleted(self, env):
        sup, tmp_path = env
        port = _free_port()
        _write_services(tmp_path, {"svc-a": _llamacpp_service(port, inspect=True, inspect_upstream_port=34000)})
        sup.sync()
        assert _port_accepting(port)

        _write_services(tmp_path, {})
        sup.sync()

        assert sup.status() == []
        assert _port_free(port)

    def test_rebinds_on_port_change(self, env):
        sup, tmp_path = env
        old_port = _free_port()
        new_port = _free_port()
        _write_services(tmp_path, {"svc-a": _llamacpp_service(old_port, inspect=True, inspect_upstream_port=34000)})
        sup.sync()
        assert _port_accepting(old_port)

        _write_services(tmp_path, {"svc-a": _llamacpp_service(new_port, inspect=True, inspect_upstream_port=34001)})
        sup.sync()

        rows = sup.status()
        assert len(rows) == 1
        assert rows[0]["listen_port"] == new_port
        assert rows[0]["upstream_port"] == 34001
        assert rows[0]["running"] is True
        assert _port_accepting(new_port)
        assert _port_free(old_port)

    def test_retries_bind_after_failure(self, env):
        sup, tmp_path = env
        port = _free_port()
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", port))
        _write_services(tmp_path, {"svc-a": _llamacpp_service(port, inspect=True, inspect_upstream_port=34000)})
        sup.sync()
        assert sup.status()[0]["running"] is False
        assert sup.status()[0]["error"]

        blocker.close()
        sup.sync()

        assert sup.status()[0]["running"] is True
        assert _port_accepting(port)

    def test_three_inspected_services_at_once(self, env):
        sup, tmp_path = env
        ports = [_free_port() for _ in range(3)]
        _write_services(
            tmp_path,
            {
                f"svc-{i}": _llamacpp_service(ports[i], alias=f"a{i}", inspect=True, inspect_upstream_port=34000 + i)
                for i in range(3)
            },
        )

        sup.sync()

        rows = sup.status()
        assert len(rows) == 3
        assert {row["listen_port"] for row in rows} == set(ports)
        assert {row["upstream_port"] for row in rows} == {34000, 34001, 34002}
        assert all(row["running"] for row in rows)
        for port in ports:
            assert _port_accepting(port)

    def test_inspect_without_upstream_port_is_skipped_not_started(self, env):
        sup, tmp_path = env
        port = _free_port()
        _write_services(tmp_path, {"svc-a": _llamacpp_service(port, inspect=True)})

        sup.sync()

        assert sup.status() == []
        assert _port_free(port)


class TestStopAllAndRename:
    def test_stop_all_releases_every_port(self, env):
        sup, tmp_path = env
        ports = [_free_port() for _ in range(2)]
        _write_services(
            tmp_path,
            {
                "svc-a": _llamacpp_service(ports[0], inspect=True, inspect_upstream_port=34000),
                "svc-b": _llamacpp_service(ports[1], alias="b", inspect=True, inspect_upstream_port=34001),
            },
        )
        sup.sync()
        assert len(sup.status()) == 2

        sup.stop_all()

        assert sup.status() == []
        for port in ports:
            assert _port_free(port)

    def test_rename_service_moves_captures(self, env):
        from inspector.db import InspectorDB
        from inspector.models import Capture

        sup, tmp_path = env
        port = _free_port()
        _write_services(tmp_path, {"svc-a": _llamacpp_service(port, inspect=True, inspect_upstream_port=34000)})
        sup.sync()

        db = InspectorDB(str(tmp_path / "inspector.db"))
        db.insert_capture(
            Capture(id=str(uuid.uuid4()), service_name="svc-a", method="POST", path="/v1/chat/completions")
        )
        moved = sup.rename_service("svc-a", "svc-b")

        assert moved == 1
        assert db.services_with_captures() == ["svc-b"]
        assert db.list_captures(service="svc-a")[1] == 0

    def test_rename_without_inspect_never_creates_db(self, env):
        sup, tmp_path = env
        _write_services(tmp_path, {"svc-a": _llamacpp_service(_free_port())})
        sup.sync()

        assert sup.rename_service("svc-a", "svc-b") == 0
        assert not (tmp_path / "inspector.db").exists()

    def test_rename_then_sync_leaves_one_proxy_on_new_name(self, env):
        sup, tmp_path = env
        port = _free_port()
        _write_services(tmp_path, {"svc-a": _llamacpp_service(port, inspect=True, inspect_upstream_port=34000)})
        sup.sync()
        assert len(sup.status()) == 1

        _write_services(tmp_path, {"svc-b": _llamacpp_service(port, alias="b", inspect=True, inspect_upstream_port=34000)})
        sup.sync()

        rows = sup.status()
        assert len(rows) == 1
        assert rows[0]["service"] == "svc-b"
        assert rows[0]["running"] is True
        assert _port_accepting(port)
