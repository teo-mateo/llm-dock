"""Host-side model presence, which is what the services list warns on.

inspect_model owns the verdict and compute_model_size is a read of its size
pair, so a caller cannot conclude "missing" from "no size" — an unmapped path
has no size either and is not missing.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import docker_utils
import model_discovery as md

_HF = "/hf-cache/"


@pytest.fixture
def host_models(tmp_path, monkeypatch):
    """Map /hf-cache/ onto a tmp tree so the check stats real files."""
    monkeypatch.setattr(md, "_CONTAINER_PATH_MAP", [(_HF, str(tmp_path) + "/")])
    return tmp_path


def _snapshot_dir(host_models, repo="unsloth--Foo-GGUF", sha="abc123"):
    d = host_models / "hub" / f"models--{repo}" / "snapshots" / sha
    d.mkdir(parents=True)
    return d


def test_present_model_file_is_reported_with_its_size(host_models):
    d = _snapshot_dir(host_models)
    f = d / "foo-Q4_K_M.gguf"
    f.write_bytes(b"x" * 2048)

    info = md.inspect_model(_HF + str(f.relative_to(host_models)), None)

    assert info["model_present"] is True
    assert info["model_size"] == 2048
    assert info["model_size_str"] == "2.00 KB"
    assert info["model_host_path"] == str(f)


def test_deleted_model_file_is_reported_missing(host_models):
    d = _snapshot_dir(host_models)
    path = _HF + str((d / "foo-Q4_K_M.gguf").relative_to(host_models))
    info = md.inspect_model(path, None)

    assert info["model_present"] is False
    assert info["model_size"] is None
    assert info["model_host_path"] == str(d / "foo-Q4_K_M.gguf")


def test_a_model_directory_is_inspected_as_a_directory(host_models):
    d = _snapshot_dir(host_models)
    (d / "config.json").write_bytes(b'{"quant_method": "exl3"}')

    info = md.inspect_model(_HF + str(d.relative_to(host_models)), None)

    assert info["model_present"] is True
    assert info["model_size"] == 24


def test_an_empty_cache_directory_is_reported_missing(host_models):
    d = _snapshot_dir(host_models)

    assert md.inspect_model(_HF + str(d.relative_to(host_models)), None)["model_present"] is False


def test_a_path_outside_the_container_map_is_never_reported_missing(monkeypatch):
    monkeypatch.setattr(md, "_CONTAINER_PATH_MAP", [(_HF, "/nonexistent-host-root/")])

    info = md.inspect_model("/somewhere/else/model.gguf", None)

    assert info["model_present"] is True
    assert info["model_host_path"] is None


def test_dangling_symlink_is_reported_missing(host_models):
    d = _snapshot_dir(host_models)
    link = d / "foo.gguf"
    link.symlink_to(d / "gone.gguf")

    assert md.inspect_model(_HF + str(link.relative_to(host_models)), None)["model_present"] is False


def test_vllm_hf_repo_absent_from_cache_is_reported_missing(tmp_path, monkeypatch):
    real_expanduser = os.path.expanduser

    def fake_expanduser(path):
        if path == "~/.cache/huggingface/hub":
            return str(tmp_path / "hub")
        return real_expanduser(path)

    monkeypatch.setattr(md.os.path, "expanduser", fake_expanduser)

    info = md.inspect_model(None, "Qwen/Qwen3.8-27B")

    assert info["model_present"] is False
    assert info["model_host_path"] == str(tmp_path / "hub" / "models--Qwen--Qwen3.8-27B")


def test_vllm_hf_repo_in_cache_is_reported_present(tmp_path, monkeypatch):
    real_expanduser = os.path.expanduser

    def fake_expanduser(path):
        if path == "~/.cache/huggingface/hub":
            return str(tmp_path / "hub")
        return real_expanduser(path)

    monkeypatch.setattr(md.os.path, "expanduser", fake_expanduser)
    cached = tmp_path / "hub" / "models--Qwen--Qwen3.8-27B" / "snapshots" / "abc"
    cached.mkdir(parents=True)
    (cached / "model-00001-of-00002.safetensors").write_bytes(b"y" * 1024)

    info = md.inspect_model(None, "Qwen/Qwen3.8-27B")

    assert info["model_present"] is True
    assert info["model_size"] == 1024


def test_compute_model_size_is_the_size_pair_of_the_same_inspection(host_models):
    d = _snapshot_dir(host_models)
    (d / "foo.gguf").write_bytes(b"z" * 4096)
    path = _HF + str((d / "foo.gguf").relative_to(host_models))

    assert md.compute_model_size(path, None) == (4096, "4.00 KB")


class _FakeComposeMgr:
    def __init__(self, entries):
        self._entries = entries

    def get_service_from_db(self, name):
        return self._entries.get(name)


class _FakeContainer:
    def __init__(self, service_name):
        self.labels = {"com.docker.compose.service": service_name}
        self.status = "running"
        self.id = "deadbeefcafe"
        self.attrs = {"Created": "2026-01-01T00:00:00Z", "State": {"ExitCode": 0}, "Config": {"Image": "llm-dock-test"}}
        self.ports = {"8080/tcp": [{"HostPort": "3301"}]}


class _FakeContainerList:
    def __init__(self, containers):
        self._containers = containers

    def list(self, **kwargs):
        return list(self._containers)


class _FakeClient:
    def __init__(self, containers):
        self.containers = _FakeContainerList(containers)


def _payload_for(monkeypatch, entries, names, running):
    import docker

    monkeypatch.setattr(docker, "from_env", lambda: _FakeClient([_FakeContainer(n) for n in running]))
    monkeypatch.setattr(docker_utils, "get_compose_services", lambda: names)
    monkeypatch.setattr(docker_utils, "get_compose_service_ports",
                        lambda: {n: 3300 + i for i, n in enumerate(names)})
    monkeypatch.setattr(docker_utils, "get_openwebui_registered_urls", lambda: [])
    monkeypatch.setattr(docker_utils, "ComposeManager", lambda *a, **k: _FakeComposeMgr(entries))
    return {s["name"]: s for s in docker_utils.get_docker_services()}


def test_missing_model_is_exposed_on_both_payload_branches(host_models, monkeypatch):
    """Both branches feed GET /api/services and the SSE snapshot alike."""
    d = _snapshot_dir(host_models, repo="Present--Foo")
    (d / "foo.gguf").write_bytes(b"w" * 512)
    entries = {
        "llamacpp-gone": {
            "api_key": "k", "template_type": "llamacpp",
            "model_path": _HF + str((d.parent.parent / "nope" / "gone.gguf").relative_to(host_models)),
        },
        "llamacpp-here": {
            "api_key": "k", "template_type": "llamacpp",
            "model_path": _HF + str((d / "foo.gguf").relative_to(host_models)),
        },
    }

    services = _payload_for(monkeypatch, entries, ["llamacpp-gone", "llamacpp-here"], ["llamacpp-gone"])

    gone, here = services["llamacpp-gone"], services["llamacpp-here"]
    assert gone["status"] == "running"
    assert here["status"] == "not-created"
    for svc in (gone, here):
        assert svc["model_missing"] is (svc["name"] == "llamacpp-gone")
    assert here["model_size_str"] == "512.00 B"
    assert gone["model_host_path"].endswith("gone.gguf")


def test_a_service_without_model_coordinates_is_not_flagged(monkeypatch):
    services = _payload_for(
        monkeypatch, {"open-webui": {"api_key": "k"}}, ["open-webui"], ["open-webui"]
    )

    assert services["open-webui"]["model_missing"] is False
