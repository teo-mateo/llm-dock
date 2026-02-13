import json
import os
import uuid
from unittest.mock import patch, MagicMock
import pytest

from benchmarking.db import BenchmarkDB
from benchmarking.executor import BenchmarkExecutor, LLAMA_BENCH_PATH, LLAMACPP_IMAGE


@pytest.fixture
def executor(db):
    return BenchmarkExecutor(db, compose_file="../docker-compose.yml")


class TestBuildDockerCmd:
    def test_basic_command_fallback(self, executor):
        """When no compose config found, uses fallback defaults"""
        cmd = executor._build_docker_cmd("llamacpp-test", "/models/test.gguf", {"-p": "512", "-n": "128"})

        assert cmd[0] == "docker"
        assert cmd[1] == "run"
        assert "--rm" in cmd
        assert "--gpus" in cmd
        assert "all" in cmd
        assert LLAMACPP_IMAGE in cmd
        assert LLAMA_BENCH_PATH in cmd

        m_idx = cmd.index("-m")
        assert cmd[m_idx + 1] == "/models/test.gguf"

        o_idx = cmd.index("-o")
        assert cmd[o_idx + 1] == "json"

        p_idx = cmd.index("-p")
        assert cmd[p_idx + 1] == "512"

        n_idx = cmd.index("-n")
        assert cmd[n_idx + 1] == "128"

    def test_boolean_flag(self, executor):
        cmd = executor._build_docker_cmd("llamacpp-test", "/models/test.gguf", {"-fa": ""})
        assert "-fa" in cmd
        fa_idx = cmd.index("-fa")
        # Next element should not be an empty string
        assert fa_idx == len(cmd) - 1 or cmd[fa_idx + 1] != ""

    def test_reserved_flags_excluded(self, executor):
        cmd = executor._build_docker_cmd(
            "llamacpp-test",
            "/models/test.gguf",
            {"-m": "/evil/path", "-o": "csv", "-p": "256"},
        )
        # -m should appear only once (the one we pass, not the user's)
        m_count = cmd.count("-m")
        assert m_count == 1

        o_count = cmd.count("-o")
        assert o_count == 1

        m_idx = cmd.index("-m")
        assert cmd[m_idx + 1] == "/models/test.gguf"

        o_idx = cmd.index("-o")
        assert cmd[o_idx + 1] == "json"

    def test_volume_mounts_fallback(self, executor):
        """When no compose config found, uses default volume mounts"""
        cmd = executor._build_docker_cmd("llamacpp-test", "/models/test.gguf", {})
        v_indices = [i for i, x in enumerate(cmd) if x == "-v"]
        assert len(v_indices) == 2

        home = os.environ.get("HOME", os.path.expanduser("~"))
        volume_args = [cmd[i + 1] for i in v_indices]
        assert any("/hf-cache" in v for v in volume_args)
        assert any("/local-models" in v for v in volume_args)

    def test_reads_volumes_from_compose(self, executor, tmp_path):
        """When compose config exists, reads volumes from it"""
        compose_content = {
            "services": {
                "llamacpp-test": {
                    "volumes": [
                        "/custom/path:/hf-cache",
                        "/other/path:/local-models:ro",
                        "/extra:/extra-mount",
                    ],
                    "deploy": {
                        "resources": {
                            "reservations": {
                                "devices": [{"driver": "nvidia", "count": "all", "capabilities": ["gpu"]}]
                            }
                        }
                    },
                    "ipc": "host",
                }
            }
        }
        compose_file = tmp_path / "docker-compose.yml"
        import yaml
        with open(compose_file, "w") as f:
            yaml.dump(compose_content, f)

        executor.compose_file = str(compose_file)
        cmd = executor._build_docker_cmd("llamacpp-test", "/models/test.gguf", {})

        v_indices = [i for i, x in enumerate(cmd) if x == "-v"]
        assert len(v_indices) == 3
        volume_args = [cmd[i + 1] for i in v_indices]
        assert "/custom/path:/hf-cache" in volume_args
        assert "/other/path:/local-models:ro" in volume_args
        assert "/extra:/extra-mount" in volume_args

    def test_reads_gpu_config_from_compose(self, executor, tmp_path):
        """Reads GPU count from compose deploy config"""
        compose_content = {
            "services": {
                "llamacpp-test": {
                    "volumes": ["/data:/data"],
                    "deploy": {
                        "resources": {
                            "reservations": {
                                "devices": [{"driver": "nvidia", "count": 1, "capabilities": ["gpu"]}]
                            }
                        }
                    },
                }
            }
        }
        compose_file = tmp_path / "docker-compose.yml"
        import yaml
        with open(compose_file, "w") as f:
            yaml.dump(compose_content, f)

        executor.compose_file = str(compose_file)
        cmd = executor._build_docker_cmd("llamacpp-test", "/models/test.gguf", {})

        gpus_idx = cmd.index("--gpus")
        assert cmd[gpus_idx + 1] == "1"


class TestExecuteBenchmark:
    @patch("benchmarking.executor.subprocess.Popen")
    def test_successful_execution(self, mock_popen, executor, db):
        mock_results = json.dumps([
            {
                "test": "pp512",
                "avg_ts": 1200.5,
                "stddev_ts": 10.2,
                "build_commit": "abc123",
                "model_type": "7B",
                "model_size": 4500000000,
                "model_n_params": 7000000000,
                "gpu_info": "RTX 4090",
                "cpu_info": "AMD Ryzen",
            },
            {
                "test": "tg128",
                "avg_ts": 85.3,
                "stddev_ts": 2.1,
            },
        ])

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (mock_results.encode(), b"")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        # Run the execution directly (synchronous for testing)
        run_id = str(uuid.uuid4())
        from benchmarking.models import BenchmarkRun
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
            params_json={"-p": "512"},
        )
        db.create_run(run)

        executor._execute(run_id, "llamacpp-test", "/models/test.gguf", {"-p": "512"})

        result = db.get_run(run_id)
        assert result.status == "completed"
        assert result.pp_avg_ts == 1200.5
        assert result.tg_avg_ts == 85.3
        assert result.build_commit == "abc123"

    @patch("benchmarking.executor.subprocess.Popen")
    def test_failed_execution(self, mock_popen, executor, db):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"Error: model not found")
        mock_proc.returncode = 1
        mock_popen.return_value = mock_proc

        run_id = str(uuid.uuid4())
        from benchmarking.models import BenchmarkRun
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)

        executor._execute(run_id, "llamacpp-test", "/models/test.gguf", {})

        result = db.get_run(run_id)
        assert result.status == "failed"
        assert "model not found" in result.error_message

    @patch("benchmarking.executor.subprocess.Popen")
    def test_timeout_execution(self, mock_popen, executor, db):
        import subprocess as real_subprocess

        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = real_subprocess.TimeoutExpired(cmd="docker", timeout=600)
        mock_proc.kill = MagicMock()
        mock_popen.return_value = mock_proc

        run_id = str(uuid.uuid4())
        from benchmarking.models import BenchmarkRun
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)

        executor._execute(run_id, "llamacpp-test", "/models/test.gguf", {})

        result = db.get_run(run_id)
        assert result.status == "failed"
        assert "timed out" in result.error_message.lower()
        mock_proc.kill.assert_called_once()

    @patch("benchmarking.executor.subprocess.Popen")
    def test_invalid_json_output(self, mock_popen, executor, db):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"not json output", b"")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        run_id = str(uuid.uuid4())
        from benchmarking.models import BenchmarkRun
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)

        executor._execute(run_id, "llamacpp-test", "/models/test.gguf", {})

        result = db.get_run(run_id)
        assert result.status == "failed"
        assert "JSON" in result.error_message


class TestCancelBenchmark:
    @patch("benchmarking.executor.subprocess.Popen")
    def test_cancel_running(self, mock_popen, executor, db):
        run_id = str(uuid.uuid4())
        from benchmarking.models import BenchmarkRun
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)
        db.update_status(run_id, "running")

        mock_proc = MagicMock()
        with executor._lock:
            executor._active_processes[run_id] = mock_proc

        result = executor.cancel_benchmark(run_id)
        assert result is True
        mock_proc.kill.assert_called_once()

        updated = db.get_run(run_id)
        assert updated.status == "cancelled"
