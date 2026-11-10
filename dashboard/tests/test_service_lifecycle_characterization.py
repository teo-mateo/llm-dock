"""Pins what rename and delete do today: status codes, bodies, the ORDER of
their side effects and which steps are best-effort. The seams are faked and
append to one log; nothing here may change when the operations move out of the
route module."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.services as services_route
import tabby_keys
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor

TOKEN = "test-token-lifecycle"


def _svc(**extra):
    config = {
        "template_type": "llamacpp", "alias": "a", "port": 3345, "api_key": "key-1",
        "model_path": "/m.gguf", "params": {},
    }
    config.update(extra)
    return config


class Container:
    def __init__(self, status):
        self.status = status


class Seams:
    def __init__(self):
        self.log = []
        self.fail = {}
        self.container = None
        self.registered = False
        self.rename_error = None
        self.emitted = []

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        failure = self.fail.get(name)
        if failure:
            raise failure
        return result


@pytest.fixture
def seams(tmp_path, monkeypatch):
    import benchmarking.routes as bench_routes
    from services import event_manager

    seams = Seams()
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n")
    (tmp_path / "services.json").write_text(json.dumps({
        "svc-a": _svc(),
        "no-engine": {"alias": "n", "port": 3350, "api_key": "k"},
    }))
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose))

    monkeypatch.setattr(services_route, "get_service_container", lambda name: seams.container)
    monkeypatch.setattr(
        services_route, "is_service_registered_in_openwebui",
        lambda name, engine: seams.step("owu_check", name, engine, result=seams.registered),
    )
    monkeypatch.setattr(
        services_route, "remove_service_from_openwebui",
        lambda name, engine: seams.step("owu_unregister", name, engine),
    )
    monkeypatch.setattr(
        services_route, "add_service_to_openwebui",
        lambda name, port, key, engine: seams.step("owu_register", name, port, key, engine),
    )

    def fake_run(command, *args, **kwargs):
        seams.step(f"compose_{command[4]}", command[-1])

    monkeypatch.setattr(services_route.subprocess, "run", fake_run)

    def rename(self, old, new):
        seams.step("db_rename", old, new)
        if seams.rename_error:
            raise seams.rename_error

    monkeypatch.setattr(ComposeManager, "rename_service", rename)
    monkeypatch.setattr(ComposeManager, "remove_service_from_db", lambda self, name: seams.step("db_remove", name))
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: seams.step("rebuild"))
    monkeypatch.setattr(proxy_supervisor, "rename_service", lambda old, new: seams.step("proxy_rename", old, new))
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: seams.step("proxy_sync"))
    monkeypatch.setattr(bench_routes, "rename_service", lambda old, new: seams.step("bench_rename", old, new, result=2))
    monkeypatch.setattr(tabby_keys, "remove", lambda name: seams.step("tabby_remove", name))
    monkeypatch.setattr(event_manager, "emit", lambda event: seams.emitted.append(event))

    from app import create_app

    seams.client = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN}).test_client()
    seams.log.clear()
    return seams


def _post(seams, name, body):
    return seams.client.post(
        f"/api/services/{name}/rename", json=body, headers={"Authorization": f"Bearer {TOKEN}"}
    )


def _delete(seams, name):
    return seams.client.delete(f"/api/services/{name}", headers={"Authorization": f"Bearer {TOKEN}"})


def _names(seams):
    return [entry[0] for entry in seams.log]


class TestRename:
    def test_a_missing_new_name_is_a_400(self, seams):
        response = _post(seams, "svc-a", {})

        assert (response.status_code, response.get_json()) == (400, {"error": "new_name is required"})
        assert seams.log == []

    def test_a_blank_new_name_is_a_400(self, seams):
        assert _post(seams, "svc-a", {"new_name": ""}).status_code == 400

    def test_an_unknown_service_is_a_404(self, seams):
        response = _post(seams, "ghost", {"new_name": "x"})

        assert (response.status_code, response.get_json()) == (404, {"error": 'Service "ghost" not found'})
        assert seams.log == []

    def test_a_running_service_is_a_409_and_nothing_runs(self, seams):
        seams.container = Container("running")

        response = _post(seams, "svc-a", {"new_name": "x"})

        assert (response.status_code, response.get_json()) == (409, {"error": "Service must be stopped before renaming"})
        assert seams.log == []

    def test_success_runs_every_step_in_order_when_registered_and_a_container_exists(self, seams):
        seams.container = Container("exited")
        seams.registered = True

        response = _post(seams, "svc-a", {"new_name": "  svc-b  "})

        assert response.status_code == 200
        assert response.get_json() == {
            "success": True, "old_name": "svc-a", "new_name": "svc-b",
            "message": 'Service renamed from "svc-a" to "svc-b"',
        }
        assert seams.log == [
            ("owu_check", "svc-a", "llamacpp"),
            ("owu_unregister", "svc-a", "llamacpp"),
            ("compose_rm", "svc-a"),
            ("db_rename", "svc-a", "svc-b"),
            ("proxy_rename", "svc-a", "svc-b"),
            ("proxy_sync",),
            ("bench_rename", "svc-a", "svc-b"),
            ("owu_register", "svc-b", 3345, "key-1", "llamacpp"),
        ]
        assert seams.emitted == []

    def test_an_unregistered_service_without_a_container_skips_those_steps(self, seams):
        _post(seams, "svc-a", {"new_name": "svc-b"})

        assert _names(seams) == ["owu_check", "db_rename", "proxy_rename", "proxy_sync", "bench_rename"]

    def test_a_service_with_no_engine_never_touches_open_webui(self, seams):
        seams.registered = True

        response = _post(seams, "no-engine", {"new_name": "x"})

        assert response.status_code == 200
        assert _names(seams) == ["db_rename", "proxy_rename", "proxy_sync", "bench_rename"]

    @pytest.mark.parametrize(
        "failing,expected_after",
        [
            ("owu_unregister", ["owu_check", "owu_unregister", "compose_rm", "db_rename", "proxy_rename", "proxy_sync", "bench_rename", "owu_register"]),
            ("compose_rm", ["owu_check", "owu_unregister", "compose_rm", "db_rename", "proxy_rename", "proxy_sync", "bench_rename", "owu_register"]),
            ("bench_rename", ["owu_check", "owu_unregister", "compose_rm", "db_rename", "proxy_rename", "proxy_sync", "bench_rename", "owu_register"]),
            ("owu_register", ["owu_check", "owu_unregister", "compose_rm", "db_rename", "proxy_rename", "proxy_sync", "bench_rename", "owu_register"]),
        ],
    )
    def test_a_best_effort_step_failing_does_not_stop_the_rename(self, seams, failing, expected_after):
        seams.container = Container("exited")
        seams.registered = True
        seams.fail[failing] = RuntimeError("boom")

        response = _post(seams, "svc-a", {"new_name": "svc-b"})

        assert response.status_code == 200
        assert _names(seams) == expected_after

    def test_a_failing_registration_check_means_no_re_registration(self, seams):
        seams.registered = True
        seams.fail["owu_check"] = RuntimeError("owu down")

        response = _post(seams, "svc-a", {"new_name": "svc-b"})

        assert response.status_code == 200
        assert "owu_register" not in _names(seams)

    def test_a_value_error_from_the_rename_is_a_400_with_its_text(self, seams):
        seams.rename_error = ValueError("Service 'svc-b' already exists")

        response = _post(seams, "svc-a", {"new_name": "svc-b"})

        assert (response.status_code, response.get_json()) == (400, {"error": "Service 'svc-b' already exists"})
        assert _names(seams) == ["owu_check", "db_rename"]

    def test_any_other_failure_of_the_rename_is_a_500(self, seams):
        seams.rename_error = RuntimeError("disk full")

        response = _post(seams, "svc-a", {"new_name": "svc-b"})

        assert (response.status_code, response.get_json()) == (500, {"error": "disk full"})

    def test_a_failing_inspector_rename_is_fatal_and_leaves_later_steps_unrun(self, seams):
        seams.fail["proxy_rename"] = RuntimeError("inspector down")

        response = _post(seams, "svc-a", {"new_name": "svc-b"})

        assert (response.status_code, response.get_json()) == (500, {"error": "inspector down"})
        assert _names(seams) == ["owu_check", "db_rename", "proxy_rename"]


class TestDelete:
    def test_an_unknown_service_is_a_404(self, seams):
        response = _delete(seams, "ghost")

        assert (response.status_code, response.get_json()) == (404, {"error": 'Service "ghost" not found'})
        assert seams.log == []

    def test_success_runs_every_step_in_order_and_announces_the_deletion(self, seams):
        response = _delete(seams, "svc-a")

        assert response.status_code == 200
        assert response.get_json() == {"success": True, "message": 'Service "svc-a" deleted successfully'}
        assert seams.log == [
            ("compose_stop", "svc-a"),
            ("compose_rm", "svc-a"),
            ("db_remove", "svc-a"),
            ("rebuild",),
            ("proxy_sync",),
            ("tabby_remove", "svc-a"),
        ]
        (event,) = seams.emitted
        assert {k: v for k, v in event.items() if k != "timestamp"} == {
            "service_name": "svc-a", "action": "service-deleted", "status": "deleted", "container_id": "",
        }
        assert isinstance(event["timestamp"], float)

    def test_a_failing_stop_skips_the_container_removal_but_not_the_delete(self, seams):
        seams.fail["compose_stop"] = RuntimeError("docker down")

        response = _delete(seams, "svc-a")

        assert response.status_code == 200
        assert _names(seams) == ["compose_stop", "db_remove", "rebuild", "proxy_sync", "tabby_remove"]
        assert len(seams.emitted) == 1

    def test_a_failing_container_removal_does_not_stop_the_delete(self, seams):
        seams.fail["compose_rm"] = RuntimeError("docker down")

        assert _delete(seams, "svc-a").status_code == 200
        assert _names(seams)[-3:] == ["rebuild", "proxy_sync", "tabby_remove"]

    def test_a_failing_key_removal_is_logged_not_raised_and_the_event_still_goes_out(self, seams):
        seams.fail["tabby_remove"] = OSError("read-only")

        response = _delete(seams, "svc-a")

        assert response.status_code == 200
        assert len(seams.emitted) == 1

    def test_a_failing_db_removal_is_a_500_and_announces_nothing(self, seams):
        seams.fail["db_remove"] = RuntimeError("db locked")

        response = _delete(seams, "svc-a")

        assert (response.status_code, response.get_json()) == (500, {"error": "db locked"})
        assert _names(seams) == ["compose_stop", "compose_rm", "db_remove"]
        assert seams.emitted == []

    def test_a_failing_proxy_sync_is_a_500_and_leaves_the_key_file_and_event(self, seams):
        seams.fail["proxy_sync"] = RuntimeError("inspector down")

        response = _delete(seams, "svc-a")

        assert (response.status_code, response.get_json()) == (500, {"error": "inspector down"})
        assert "tabby_remove" not in _names(seams)
        assert seams.emitted == []
