import json
import logging
import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .db import BenchmarkDB
from .models import BenchmarkRun

logger = logging.getLogger(__name__)

BENCHMARK_TIMEOUT = 600  # 10 minutes
LLAMA_BENCH_PATH = "/llama.cpp/build/bin/llama-bench"
LLAMACPP_IMAGE = "llm-dock-llamacpp"


class BenchmarkExecutor:
    def __init__(self, db: BenchmarkDB, compose_file: str):
        self.db = db
        self.compose_file = compose_file
        self._lock = threading.Lock()
        self._active_processes: Dict[str, subprocess.Popen] = {}

    def start_benchmark(
        self, service_name: str, model_path: str, params: Dict[str, str]
    ) -> BenchmarkRun:
        run_id = str(uuid.uuid4())
        run = BenchmarkRun(
            id=run_id,
            service_name=service_name,
            model_path=model_path,
            status="pending",
            params_json=params,
        )
        run = self.db.create_run(run)

        thread = threading.Thread(
            target=self._execute, args=(run_id, service_name, model_path, params),
            daemon=True,
        )
        thread.start()
        return run

    def cancel_benchmark(self, run_id: str) -> bool:
        with self._lock:
            proc = self._active_processes.get(run_id)
            if proc is not None:
                try:
                    proc.kill()
                except OSError:
                    pass
                del self._active_processes[run_id]

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.db.update_status(run_id, "cancelled", completed_at=now)
        return True

    def is_running_for_service(self, service_name: str) -> bool:
        return self.db.has_running_benchmark(service_name)

    def _get_service_compose_config(self, service_name: str) -> Optional[Dict]:
        """Read the service's config from docker-compose.yml"""
        try:
            with open(self.compose_file, "r") as f:
                compose = yaml.safe_load(f) or {}
            return compose.get("services", {}).get(service_name)
        except Exception as e:
            logger.warning(f"Failed to read compose config for {service_name}: {e}")
            return None

    def _extract_volumes(self, service_config: Dict) -> List[str]:
        """Extract volume mounts from a service's compose config"""
        volumes = service_config.get("volumes", [])
        result = []
        home = os.environ.get("HOME", os.path.expanduser("~"))
        for vol in volumes:
            # Expand ${HOME} in volume paths
            expanded = str(vol).replace("${HOME}", home)
            result.append(expanded)
        return result

    def _extract_gpu_args(self, service_config: Dict) -> List[str]:
        """Extract GPU arguments from a service's compose deploy config"""
        deploy = service_config.get("deploy", {})
        resources = deploy.get("resources", {})
        reservations = resources.get("reservations", {})
        devices = reservations.get("devices", [])

        for device in devices:
            if "gpu" in device.get("capabilities", []):
                count = device.get("count", "all")
                return ["--gpus", str(count)]

        return ["--gpus", "all"]

    def _extract_ipc(self, service_config: Dict) -> List[str]:
        """Extract IPC mode from a service's compose config"""
        ipc = service_config.get("ipc")
        if ipc:
            return ["--ipc", str(ipc)]
        return []

    def _build_docker_cmd(
        self, service_name: str, model_path: str, params: Dict[str, str]
    ) -> list:
        service_config = self._get_service_compose_config(service_name)

        cmd = ["docker", "run", "--rm"]

        if service_config:
            cmd.extend(self._extract_gpu_args(service_config))
            cmd.extend(self._extract_ipc(service_config))
            for vol in self._extract_volumes(service_config):
                cmd.extend(["-v", vol])
        else:
            # Fallback if compose config unavailable
            logger.warning(
                f"No compose config found for {service_name}, using default mounts"
            )
            home = os.environ.get("HOME", os.path.expanduser("~"))
            cmd.extend(["--gpus", "all", "--ipc", "host"])
            cmd.extend(["-v", f"{home}/.cache/huggingface:/hf-cache"])
            cmd.extend(["-v", f"{home}/.cache/models:/local-models:ro"])

        cmd.extend([
            LLAMACPP_IMAGE,
            LLAMA_BENCH_PATH,
            "-m", model_path,
            "-o", "json",
        ])

        for flag, value in params.items():
            if flag in ("-m", "-o"):
                continue
            cmd.append(flag)
            if value:
                # Strip surrounding quotes — users may type them out of habit
                # but Popen passes args directly without shell interpretation
                stripped = value.strip()
                if (stripped.startswith('"') and stripped.endswith('"')) or \
                   (stripped.startswith("'") and stripped.endswith("'")):
                    stripped = stripped[1:-1]
                cmd.append(stripped)

        return cmd

    def _execute(
        self, run_id: str, service_name: str, model_path: str, params: Dict[str, str]
    ):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.db.update_status(run_id, "running", started_at=now)

        cmd = self._build_docker_cmd(service_name, model_path, params)
        logger.info(f"Benchmark {run_id}: executing {' '.join(cmd)}")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            with self._lock:
                self._active_processes[run_id] = proc

            try:
                stdout, stderr = proc.communicate(timeout=BENCHMARK_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                self._finish_failed(
                    run_id, f"Benchmark timed out after {BENCHMARK_TIMEOUT} seconds"
                )
                return
            finally:
                with self._lock:
                    self._active_processes.pop(run_id, None)

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            logger.info(f"Benchmark {run_id}: returncode={proc.returncode}, stdout={len(stdout_text)} bytes, stderr={len(stderr_text)} bytes")
            if stdout_text:
                logger.debug(f"Benchmark {run_id} stdout (first 500 chars): {stdout_text[:500]!r}")
            if stderr_text:
                logger.debug(f"Benchmark {run_id} stderr (first 500 chars): {stderr_text[:500]!r}")

            if proc.returncode != 0:
                error_msg = stderr_text.strip() or f"llama-bench exited with code {proc.returncode}"
                self._finish_failed(run_id, error_msg, raw_output=stdout_text)
                return

            self._parse_and_store_results(run_id, stdout_text, stderr_text)

        except Exception as e:
            logger.exception(f"Benchmark {run_id}: unexpected error")
            self._finish_failed(run_id, str(e))

    def _finish_failed(
        self, run_id: str, error_message: str, raw_output: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.db.update_status(
            run_id, "failed", completed_at=now, error_message=error_message
        )
        if raw_output:
            self.db.update_results(run_id, raw_output=raw_output)
        logger.error(f"Benchmark {run_id} failed: {error_message}")

    def _extract_json_array(self, text: str) -> Optional[list]:
        """Find and parse a JSON array from text that may contain non-JSON preamble."""
        json_start = text.find("[")
        if json_start < 0:
            return None
        try:
            return json.loads(text[json_start:])
        except json.JSONDecodeError:
            return None

    def _parse_and_store_results(
        self, run_id: str, stdout_text: str, stderr_text: str
    ):
        # llama-bench may output JSON to stdout or stderr, and may prefix it
        # with non-JSON lines (e.g. CUDA init messages). Try both streams.
        results = self._extract_json_array(stdout_text)
        if results is None:
            logger.info(f"Benchmark {run_id}: no JSON in stdout, trying stderr")
            results = self._extract_json_array(stderr_text)
        if results is None:
            combined = f"stdout:\n{stdout_text}\n\nstderr:\n{stderr_text}"
            self._finish_failed(
                run_id,
                f"Failed to parse llama-bench JSON output from stdout or stderr",
                raw_output=combined,
            )
            return

        if not isinstance(results, list) or len(results) == 0:
            self._finish_failed(
                run_id,
                "llama-bench returned empty or invalid results",
                raw_output=stdout_text,
            )
            return

        pp_avg = None
        pp_stddev = None
        tg_avg = None
        tg_stddev = None
        build_commit = None
        model_type = None
        model_size = None
        model_n_params = None
        gpu_info = None
        cpu_info = None

        for entry in results:
            avg_ts = entry.get("avg_ts")
            stddev_ts = entry.get("stddev_ts")

            n_prompt = entry.get("n_prompt", 0)
            n_gen = entry.get("n_gen", 0)

            if n_prompt and not n_gen:
                pp_avg = avg_ts
                pp_stddev = stddev_ts
            elif n_gen and not n_prompt:
                tg_avg = avg_ts
                tg_stddev = stddev_ts

            if build_commit is None:
                build_commit = entry.get("build_commit")
            if model_type is None:
                model_type = entry.get("model_type")
            if model_size is None:
                model_size = entry.get("model_size")
            if model_n_params is None:
                model_n_params = entry.get("model_n_params")
            if gpu_info is None:
                gpu_info = entry.get("gpu_info")
            if cpu_info is None:
                cpu_info = entry.get("cpu_info")

        self.db.update_results(
            run_id,
            pp_avg_ts=pp_avg,
            pp_stddev_ts=pp_stddev,
            tg_avg_ts=tg_avg,
            tg_stddev_ts=tg_stddev,
            raw_output=stdout_text,
            build_commit=build_commit,
            model_type=model_type,
            model_size=model_size,
            model_n_params=model_n_params,
            gpu_info=gpu_info,
            cpu_info=cpu_info,
        )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.db.update_status(run_id, "completed", completed_at=now)
        logger.info(
            f"Benchmark {run_id} completed: pp={pp_avg} t/s, tg={tg_avg} t/s"
        )
