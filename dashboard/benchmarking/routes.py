import logging
import os
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from .db import BenchmarkDB
from .executor import BenchmarkExecutor
from .validators import validate_params, validate_service_name, BENCHMARK_ONLY_FLAGS

logger = logging.getLogger(__name__)

benchmarks_bp = Blueprint("benchmarks", __name__)

# These are initialized by init_benchmarking() called from app.py
_db: BenchmarkDB = None
_executor: BenchmarkExecutor = None
_compose_file: str = None


def rename_service(old_name: str, new_name: str) -> int:
    """Rename a service in the benchmark database. Returns the number of updated records."""
    if _db is None:
        return 0
    return _db.rename_service(old_name, new_name)


def init_benchmarking(compose_file: str, db_path: str = None):
    global _db, _executor, _compose_file
    _compose_file = compose_file
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "benchmarks.db")
    _db = BenchmarkDB(db_path)
    _executor = BenchmarkExecutor(_db, compose_file)
    _db.recover_stale_runs()
    logger.info("Benchmarking subsystem initialized")


def _get_compose_manager():
    from compose_manager import ComposeManager
    return ComposeManager(_compose_file)


def _get_service_config(service_name: str):
    mgr = _get_compose_manager()
    return mgr.get_service_from_db(service_name)


def _require_auth(f):
    """Import require_auth from auth module at call time to avoid circular imports."""
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        from auth import require_auth as auth_require_auth
        decorated = auth_require_auth(f)
        return decorated(*args, **kwargs)
    return wrapper


@benchmarks_bp.route("/api/benchmarks", methods=["POST"])
@_require_auth
def start_benchmark():
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "INVALID_REQUEST", "message": "Request body is required"}}), 400

    service_name = data.get("service_name")
    valid, err = validate_service_name(service_name)
    if not valid:
        return jsonify({"error": {"code": "INVALID_REQUEST", "message": err}}), 400

    service_config = _get_service_config(service_name)
    if not service_config:
        return jsonify({"error": {"code": "SERVICE_NOT_FOUND", "message": f"Service '{service_name}' not found"}}), 404

    template_type = service_config.get("template_type", "")
    if template_type != "llamacpp":
        return jsonify({"error": {"code": "INVALID_SERVICE", "message": "Benchmarking is only supported for llama.cpp services"}}), 400

    if _executor.is_running_for_service(service_name):
        return jsonify({"error": {"code": "ALREADY_RUNNING", "message": f"Benchmark already running for {service_name}"}}), 409

    params = data.get("params", {})
    valid, err = validate_params(params)
    if not valid:
        return jsonify({"error": {"code": "INVALID_PARAMS", "message": err}}), 400

    model_path = service_config.get("model_path", "")
    if not model_path:
        return jsonify({"error": {"code": "NO_MODEL_PATH", "message": "Service has no model_path configured"}}), 400

    run = _executor.start_benchmark(service_name, model_path, params)
    return jsonify({
        "id": run.id,
        "service_name": run.service_name,
        "status": run.status,
        "message": "Benchmark queued",
    }), 202


@benchmarks_bp.route("/api/benchmarks", methods=["GET"])
@_require_auth
def list_benchmarks():
    service_name = request.args.get("service_name")
    status = request.args.get("status")
    limit = request.args.get("limit", default=20, type=int)
    offset = request.args.get("offset", default=0, type=int)
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    runs, total = _db.list_runs(
        service_name=service_name, status=status, limit=limit, offset=offset
    )
    return jsonify({
        "runs": [r.to_summary_dict() for r in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }), 200


@benchmarks_bp.route("/api/benchmarks/<run_id>", methods=["GET"])
@_require_auth
def get_benchmark(run_id):
    run = _db.get_run(run_id)
    if not run:
        return jsonify({"error": {"code": "NOT_FOUND", "message": f"Benchmark run {run_id} not found"}}), 404
    return jsonify(run.to_dict()), 200


@benchmarks_bp.route("/api/benchmarks/<run_id>", methods=["DELETE"])
@_require_auth
def delete_benchmark(run_id):
    run = _db.get_run(run_id)
    if not run:
        return jsonify({"error": {"code": "NOT_FOUND", "message": f"Benchmark run {run_id} not found"}}), 404

    if run.status in ("pending", "running"):
        _executor.cancel_benchmark(run_id)
        return jsonify({"success": True, "message": f"Benchmark {run_id} cancelled"}), 200

    _db.delete_run(run_id)
    return jsonify({"success": True, "message": f"Benchmark {run_id} deleted"}), 200


@benchmarks_bp.route("/api/benchmarks/<run_id>/apply", methods=["PUT"])
@_require_auth
def apply_benchmark(run_id):
    run = _db.get_run(run_id)
    if not run:
        return jsonify({"error": {"code": "NOT_FOUND", "message": f"Benchmark run {run_id} not found"}}), 404

    if run.status != "completed":
        return jsonify({"error": {"code": "INVALID_STATUS", "message": "Can only apply completed benchmark runs"}}), 400

    service_config = _get_service_config(run.service_name)
    if not service_config:
        return jsonify({"error": {"code": "SERVICE_NOT_FOUND", "message": f"Service '{run.service_name}' not found"}}), 404

    applied_params = {}
    skipped_flags = []

    for flag, value in run.params_json.items():
        if flag in BENCHMARK_ONLY_FLAGS:
            skipped_flags.append(flag)
            continue

        params = service_config.setdefault("params", {})
        params[flag] = value
        applied_params[flag] = value

    if not applied_params:
        return jsonify({"error": {"code": "NO_APPLICABLE_PARAMS", "message": "No applicable parameters found to apply"}}), 400

    mgr = _get_compose_manager()
    mgr.update_service_in_db(run.service_name, service_config)
    mgr.rebuild_compose_file()

    return jsonify({
        "success": True,
        "message": f"Configuration applied to {run.service_name}. Restart the service for changes to take effect.",
        "applied_params": applied_params,
        "skipped_flags": skipped_flags,
    }), 200


@benchmarks_bp.route("/api/benchmarks/service-defaults/<service_name>", methods=["GET"])
@_require_auth
def get_service_defaults(service_name):
    service_config = _get_service_config(service_name)
    if not service_config:
        return jsonify({"error": {"code": "SERVICE_NOT_FOUND", "message": f"Service '{service_name}' not found"}}), 404

    if service_config.get("template_type") != "llamacpp":
        return jsonify({"error": {"code": "INVALID_SERVICE", "message": "Only llama.cpp services are supported"}}), 400

    params = {
        "-p": "512",
        "-n": "128",
        "-r": "5",
    }

    svc_params = service_config.get("params", {})
    for flag, value in svc_params.items():
        params[flag] = value

    return jsonify({
        "service_name": service_name,
        "model_path": service_config.get("model_path", ""),
        "params": params,
    }), 200
