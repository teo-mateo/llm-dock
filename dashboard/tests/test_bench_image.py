import json
import os
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.executor import LLAMA_BENCH_PATH, BenchmarkExecutor
from benchmarking.models import BenchmarkRun
from flag_metadata import ENGINE_IMAGES

TOKEN = "test-token-bench-image"
DEFAULT = ENGINE_IMAGES["llamacpp"]


def _service(**extra):
    config = {
        "template_type": "llamacpp", "alias": "svc", "port": 3345, "api_key": "k",
        "model_path": "/models/m.gguf", "params": {},
    }
    config.update(extra)
    return config


@pytest.fixture
def stored(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n")

    def write(services):
        (tmp_path / "services.json").write_text(json.dumps(services))
        return str(compose)

    return write


def _image_in(cmd):
    return cmd[cmd.index(LLAMA_BENCH_PATH) - 1]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    from app import create_app

    return create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN}).test_client()


def test_image_metadata_lists_every_engine_with_its_own_image(api, monkeypatch):
    import routes.system as system

    monkeypatch.setattr(system, "get_image_info", lambda image: {"name": image})

    body = api.get("/api/images/metadata", headers={"Authorization": f"Bearer {TOKEN}"}).get_json()

    assert {k: v for k, v in body.items() if k != "timestamp"} == {
        engine: {"name": image} for engine, image in ENGINE_IMAGES.items()
    }
    assert body["timestamp"].endswith("Z")
    assert "ik_llamacpp" in body


@pytest.mark.parametrize(
    "services,expected",
    [
        ({"svc": _service(image="my-build:1")}, "my-build:1"),
        ({"svc": _service()}, DEFAULT),
        ({"svc": _service(image="")}, DEFAULT),
    ],
    ids=["override", "no-override", "empty-override"],
)
def test_the_benchmark_runs_on_the_services_effective_image(db, stored, services, expected):
    executor = BenchmarkExecutor(db, compose_file=stored(services))

    assert executor._image_for("svc") == expected
    assert _image_in(executor._build_docker_cmd("svc", "/models/m.gguf", {}, expected)) == expected


@pytest.mark.parametrize(
    "services,reason",
    [
        ({"other": _service()}, "not found"),
        ({"svc": _service(template_type="vllm")}, "supports llamacpp services, not 'vllm'"),
        ({"svc": {"alias": "x"}}, "not 'None'"),
    ],
    ids=["unknown-service", "wrong-engine", "no-template-type"],
)
def test_an_unresolvable_service_fails_the_run_instead_of_using_another_image(db, stored, services, reason):
    executor = BenchmarkExecutor(db, compose_file=stored(services))

    with patch("benchmarking.executor.subprocess.Popen") as popen:
        result = _run(db, executor, 0, b"")

    assert result.status == "failed"
    assert result.error_message.startswith("Cannot resolve image for service 'svc': ")
    assert reason in result.error_message
    popen.assert_not_called()


def test_an_unreadable_services_file_fails_the_run(db, tmp_path):
    executor = BenchmarkExecutor(db, compose_file=str(tmp_path / "missing" / "docker-compose.yml"))

    with patch("benchmarking.executor.subprocess.Popen") as popen:
        result = _run(db, executor, 0, b"")

    assert result.status == "failed" and "Cannot resolve image" in result.error_message
    popen.assert_not_called()


def test_a_corrupt_services_file_fails_the_run(db, stored, tmp_path):
    compose = stored({"svc": _service()})
    (tmp_path / "services.json").write_text("{not json")
    executor = BenchmarkExecutor(db, compose_file=compose)

    with patch("benchmarking.executor.subprocess.Popen") as popen:
        result = _run(db, executor, 0, b"")

    assert result.status == "failed" and "Cannot resolve image" in result.error_message
    popen.assert_not_called()


def _run(db, executor, returncode, stderr):
    run_id = str(uuid.uuid4())
    db.create_run(BenchmarkRun(id=run_id, service_name="svc", model_path="/models/m.gguf"))
    proc = MagicMock()
    proc.communicate.return_value = (b"", stderr)
    proc.returncode = returncode
    with patch("benchmarking.executor.subprocess.Popen", return_value=proc):
        executor._execute(run_id, "svc", "/models/m.gguf", {})
    return db.get_run(run_id)


def test_a_failed_run_names_the_image_the_binary_and_the_exit_code(db, stored):
    executor = BenchmarkExecutor(db, compose_file=stored({"svc": _service(image="my-build:1")}))

    result = _run(db, executor, 127, b'exec: "/llama.cpp/build/bin/llama-bench": no such file or directory')

    assert result.status == "failed"
    assert "my-build:1" in result.error_message
    assert LLAMA_BENCH_PATH in result.error_message
    assert "exit code 127" in result.error_message
    assert "no such file or directory" in result.error_message


def test_a_failed_run_with_no_output_still_names_the_image(db, stored):
    executor = BenchmarkExecutor(db, compose_file=stored({"svc": _service()}))

    result = _run(db, executor, 1, b"")

    assert DEFAULT in result.error_message and "no output" in result.error_message
