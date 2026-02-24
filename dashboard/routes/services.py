import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request

from auth import require_auth
from config import COMPOSE_FILE, GLOBAL_API_KEY
from compose_manager import ComposeManager
from docker_utils import get_docker_services, get_service_container, control_service
from model_discovery import ModelDiscovery
from service_templates import generate_api_key
from flag_metadata import (
    generate_service_name as gen_service_name,
    validate_service_config,
    get_flag_metadata,
    MANDATORY_FIELDS,
)
from openwebui_integration import (
    add_service_to_openwebui,
    remove_service_from_openwebui,
    is_service_registered_in_openwebui,
)

logger = logging.getLogger(__name__)

services_bp = Blueprint("services", __name__)

# Container-path → host-path prefixes for model file resolution
_CONTAINER_PATH_MAP = [
    ("/hf-cache/", os.path.expanduser("~/.cache/huggingface/")),
    ("/local-models/", os.path.expanduser("~/.cache/models/")),
]


def _resolve_host_path(container_path: str) -> str | None:
    """Translate a container model path to the corresponding host path."""
    for prefix, host_prefix in _CONTAINER_PATH_MAP:
        if container_path.startswith(prefix):
            return host_prefix + container_path[len(prefix):]
    return None


def _compute_model_size(data: dict) -> None:
    """Compute model directory size and store in data dict. Fails silently."""
    try:
        target = None

        model_path = data.get("model_path")
        if model_path:
            host_path = _resolve_host_path(model_path)
            if not host_path:
                return
            p = Path(host_path)
            target = p.parent if p.is_file() or p.is_symlink() else p

        # vLLM: model_name is an HF identifier like "org/model"
        model_name = data.get("model_name")
        if not target and model_name and "/" in model_name:
            cache_dir = Path(os.path.expanduser("~/.cache/huggingface/hub"))
            target = cache_dir / ("models--" + model_name.replace("/", "--"))

        if not target or not target.exists():
            return

        # Sum file sizes following symlinks (HF cache uses symlinks to blobs)
        size = sum(
            f.stat().st_size for f in target.rglob("*") if f.is_file()
        )
        discovery = ModelDiscovery(Path.home())
        data["model_size"] = size
        data["model_size_str"] = discovery.format_size(size)
    except Exception as e:
        logger.debug(f"Could not compute model size: {e}")


def _recreate_if_running(service_name):
    """Recreate the container if it was running. Returns restart status dict."""
    container = get_service_container(service_name)
    if not container or container.status != "running":
        return {"restarted": False}

    result = subprocess.run(
        [
            "docker", "compose", "-f", COMPOSE_FILE,
            "up", "-d", "--force-recreate", service_name,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        logger.warning(f"Failed to restart {service_name}: {result.stderr}")
        return {"restarted": False, "error": result.stderr}
    logger.info(f"Restarted service: {service_name}")
    return {"restarted": True}


def _rebuild_and_restart(compose_mgr, service_name):
    """Rebuild docker-compose.yml and recreate the container if it was running."""
    compose_mgr.rebuild_compose_file()
    return _recreate_if_running(service_name)


# ============================================
# Service listing & status
# ============================================


@services_bp.route("/api/services", methods=["GET"])
@require_auth
def list_services():
    """List all Docker Compose services with live status"""
    try:
        services = get_docker_services()
        return jsonify(
            {
                "services": services,
                "total": len(services),
                "running": sum(1 for s in services if s["status"] == "running"),
                "stopped": sum(1 for s in services if s["status"] != "running"),
            }
        )
    except Exception as e:
        logger.error(f"Failed to get services: {e}")
        return jsonify({"error": "Failed to retrieve service information"}), 500


@services_bp.route("/api/services/<service_name>", methods=["GET"])
@require_auth
def get_service(service_name):
    """Get service configuration from database"""
    try:
        compose_mgr = ComposeManager(COMPOSE_FILE)
        config = compose_mgr.get_service_from_db(service_name)

        if not config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        return jsonify({"service_name": service_name, "config": config}), 200

    except Exception as e:
        logger.error(f"Failed to get service: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# Service control (start/stop)
# ============================================


@services_bp.route("/api/services/<service_name>/start", methods=["POST"])
@require_auth
def start_service(service_name):
    """Start a Docker Compose service"""
    result = control_service(service_name, "start")

    if result["success"]:
        logger.info(f"Started service: {service_name}")
        return jsonify(result)
    else:
        logger.warning(f"Failed to start service {service_name}: {result.get('error')}")
        return jsonify(result), 400


@services_bp.route("/api/services/<service_name>/stop", methods=["POST"])
@require_auth
def stop_service(service_name):
    """Stop a Docker Compose service"""
    result = control_service(service_name, "stop")

    if result["success"]:
        logger.info(f"Stopped service: {service_name}")
        return jsonify(result)
    else:
        logger.warning(f"Failed to stop service {service_name}: {result.get('error')}")
        return jsonify(result), 400


# ============================================
# Service preview & logs
# ============================================


@services_bp.route("/api/services/<service_name>/preview", methods=["GET"])
@require_auth
def preview_service(service_name):
    """Get the rendered YAML for a service"""
    try:
        manager = ComposeManager(COMPOSE_FILE)
        yaml_content = manager.preview_service(service_name)

        if yaml_content is None:
            return jsonify({"error": f"Service {service_name} not found in database"}), 404

        return jsonify({"service_name": service_name, "yaml": yaml_content})

    except Exception as e:
        logger.error(f"Failed to preview service {service_name}: {e}")
        return jsonify({"error": str(e)}), 500


@services_bp.route("/api/services/<service_name>/logs", methods=["GET"])
@require_auth
def get_service_logs(service_name):
    """Get logs from a Docker Compose service"""
    try:
        container = get_service_container(service_name)

        if not container:
            return jsonify({"error": "Service has not been created yet"}), 404

        # Get tail parameter (default 100 lines)
        tail = request.args.get("tail", default=100, type=int)
        tail = min(tail, 1000)  # Max 1000 lines

        logs = container.logs(tail=tail, timestamps=True).decode("utf-8")

        return jsonify(
            {
                "service": service_name,
                "logs": logs,
                "lines": len(logs.split("\n")) if logs else 0,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        )

    except Exception as e:
        logger.error(f"Failed to get logs for service {service_name}: {e}")
        return jsonify({"error": f"Failed to retrieve logs: {str(e)}"}), 500


# ============================================
# Service creation
# ============================================


@services_bp.route("/api/services", methods=["POST"])
@require_auth
def create_service():
    """
    Create a new service in services database and rebuild compose file.

    Request body:
    {
        "template_type": "llamacpp" | "vllm",
        "port": 3305,
        "model_path": "/path/to/model.gguf",  // for llamacpp
        "model_name": "org/model",             // for vllm
        "alias": "my-model",
        "api_key": "key-xxx" (optional, auto-generated if not provided),
        "params": {
            "-c": "32000",
            "-ngl": "40"
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        template_type = data.get("template_type")
        if not template_type:
            return jsonify({"error": "template_type is required"}), 400
        if template_type not in ["llamacpp", "vllm"]:
            return jsonify({"error": 'template_type must be "llamacpp" or "vllm"'}), 400

        # Auto-generate API key if not provided
        if not data.get("api_key"):
            data["api_key"] = generate_api_key()

        # Validate configuration
        valid, errors = validate_service_config(template_type, data)
        if not valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        # Generate service name from alias
        service_name = gen_service_name(template_type, data.get("alias"))

        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service already exists
        if compose_mgr.get_service_from_db(service_name):
            return jsonify({"error": f'Service "{service_name}" already exists'}), 409

        # Check port availability
        port = int(data["port"])
        if port in compose_mgr.get_used_ports():
            return jsonify({"error": f"Port {port} is already in use"}), 409

        # Compute model size before persisting
        _compute_model_size(data)

        # Add to database and rebuild
        compose_mgr.add_service_to_db(service_name, data)
        compose_mgr.rebuild_compose_file()

        logger.info(f"Service created: {service_name} on port {port}")

        return jsonify(
            {
                "success": True,
                "service_name": service_name,
                "port": port,
                "api_key": data["api_key"],
                "message": f'Service "{service_name}" created successfully',
            }
        ), 201

    except Exception as e:
        logger.error(f"Failed to create service: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================
# Service update & delete
# ============================================


@services_bp.route("/api/services/<service_name>", methods=["PUT"])
@require_auth
def update_service(service_name):
    """
    Update service configuration and rebuild compose file.

    Note: template_type cannot be changed.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "Request body is required"}), 400

        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service exists
        existing = compose_mgr.get_service_from_db(service_name)
        if not existing:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        # Prevent template_type change
        if (
            "template_type" in data
            and data["template_type"] != existing["template_type"]
        ):
            return jsonify(
                {"error": "Cannot change template_type of existing service"}
            ), 400

        # Use existing template_type
        template_type = existing["template_type"]
        data["template_type"] = template_type

        # Validate updated configuration
        valid, errors = validate_service_config(template_type, data)
        if not valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        # Check port if changed
        if "port" in data and int(data["port"]) != int(existing.get("port", 0)):
            used_ports = compose_mgr.get_used_ports()
            new_port = int(data["port"])
            if new_port in used_ports:
                return jsonify({"error": f"Port {new_port} is already in use"}), 409

        # Update in database
        compose_mgr.update_service_in_db(service_name, data)

        # Rebuild compose file
        compose_mgr.rebuild_compose_file()

        logger.info(f"Service updated: {service_name}")

        return jsonify(
            {
                "success": True,
                "service_name": service_name,
                "message": f'Service "{service_name}" updated successfully',
            }
        ), 200

    except Exception as e:
        logger.error(f"Failed to update service: {e}")
        return jsonify({"error": str(e)}), 500


@services_bp.route("/api/services/<service_name>", methods=["DELETE"])
@require_auth
def delete_service(service_name):
    """Delete service from database and rebuild compose file"""
    try:
        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service exists
        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        # Stop and remove container if running
        try:
            subprocess.run(
                ["docker", "compose", "-f", COMPOSE_FILE, "stop", service_name],
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                ["docker", "compose", "-f", COMPOSE_FILE, "rm", "-f", service_name],
                capture_output=True,
                timeout=10,
            )
            logger.info(f"Stopped and removed container for: {service_name}")
        except Exception as e:
            logger.warning(f"Error stopping container (may not be running): {e}")

        # Remove from database
        compose_mgr.remove_service_from_db(service_name)

        # Rebuild compose file
        compose_mgr.rebuild_compose_file()

        logger.info(f"Service deleted: {service_name}")

        return jsonify(
            {
                "success": True,
                "message": f'Service "{service_name}" deleted successfully',
            }
        ), 200

    except Exception as e:
        logger.error(f"Failed to delete service: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# Service rename
# ============================================


@services_bp.route("/api/services/<service_name>/rename", methods=["POST"])
@require_auth
def rename_service(service_name):
    """
    Rename a service. Service must be stopped.

    Request body: {"new_name": "my-new-name"}
    """
    try:
        data = request.get_json()
        if not data or not data.get("new_name"):
            return jsonify({"error": "new_name is required"}), 400

        new_name = data["new_name"].strip()

        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check service exists
        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        # Check service is not running
        container = get_service_container(service_name)
        if container and container.status == "running":
            return jsonify(
                {"error": "Service must be stopped before renaming"}
            ), 409

        # Handle Open WebUI: unregister old name (best-effort)
        engine = service_config.get("template_type", "")
        owu_was_registered = False
        if engine:
            try:
                if is_service_registered_in_openwebui(service_name, engine):
                    owu_was_registered = True
                    remove_service_from_openwebui(service_name, engine)
            except Exception as e:
                logger.warning(f"Failed to unregister old name from Open WebUI: {e}")

        # Remove old container if it exists (stopped/exited)
        if container:
            try:
                subprocess.run(
                    ["docker", "compose", "-f", COMPOSE_FILE, "rm", "-f", service_name],
                    capture_output=True,
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"Failed to remove old container: {e}")

        # Rename in services DB and rebuild compose
        compose_mgr.rename_service(service_name, new_name)

        # Rename in benchmark DB
        from benchmarking.routes import rename_service as bench_rename

        try:
            updated = bench_rename(service_name, new_name)
            logger.info(
                f"Updated {updated} benchmark records from '{service_name}' to '{new_name}'"
            )
        except Exception as e:
            logger.warning(f"Failed to rename benchmarks (non-fatal): {e}")

        # Re-register with Open WebUI under new name (best-effort)
        if owu_was_registered and engine:
            try:
                port = service_config.get("port", 0)
                api_key = service_config.get("api_key", "")
                add_service_to_openwebui(new_name, port, api_key, engine)
            except Exception as e:
                logger.warning(f"Failed to re-register new name with Open WebUI: {e}")

        logger.info(f"Service renamed: {service_name} -> {new_name}")

        return jsonify(
            {
                "success": True,
                "old_name": service_name,
                "new_name": new_name,
                "message": f'Service renamed from "{service_name}" to "{new_name}"',
            }
        ), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to rename service: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================
# Flag metadata
# ============================================


@services_bp.route("/api/flag-metadata/<template_type>", methods=["GET"])
@require_auth
def get_flags_metadata(template_type):
    """Get flag metadata for a template type"""
    try:
        if template_type not in ["llamacpp", "llamacpp_bench", "vllm"]:
            return jsonify({"error": 'template_type must be "llamacpp", "llamacpp_bench", or "vllm"'}), 400

        metadata = get_flag_metadata(template_type)
        mandatory = MANDATORY_FIELDS.get(template_type, [])

        return jsonify(
            {
                "template_type": template_type,
                "mandatory_fields": mandatory,
                "optional_flags": metadata,
            }
        ), 200

    except Exception as e:
        logger.error(f"Failed to get flag metadata: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# Port management
# ============================================


@services_bp.route("/api/services/<service_name>/set-public-port", methods=["POST"])
@require_auth
def set_public_port(service_name):
    """
    Set service to use the public port (3301).
    If another service is using 3301, reassign it to a random 33XX port.
    """
    try:
        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service exists
        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        # Check if service is already on 3301
        current_port = service_config.get("port")
        if current_port == 3301:
            return jsonify(
                {
                    "success": True,
                    "message": f'Service "{service_name}" is already on port 3301',
                    "no_change": True,
                }
            ), 200

        # Find service currently using port 3301
        all_services = compose_mgr.list_services_in_db()
        conflicting_service = None
        conflicting_service_name = None

        for svc_name, svc_config in all_services.items():
            if svc_config.get("port") == 3301:
                conflicting_service = svc_config
                conflicting_service_name = svc_name
                break

        # Prepare updates
        updates_made = []

        if conflicting_service:
            # Reassign conflicting service to random 33XX port
            new_port = compose_mgr.get_next_available_port(
                start_port=3300, end_port=3399
            )
            conflicting_service["port"] = new_port
            compose_mgr.update_service_in_db(
                conflicting_service_name, conflicting_service
            )

            updates_made.append(
                {
                    "service": conflicting_service_name,
                    "old_port": 3301,
                    "new_port": new_port,
                }
            )

        # Set requested service to 3301
        service_config["port"] = 3301
        compose_mgr.update_service_in_db(service_name, service_config)

        updates_made.append(
            {"service": service_name, "old_port": current_port, "new_port": 3301}
        )

        # Rebuild compose file and restart affected services
        compose_mgr.rebuild_compose_file()

        services_to_restart = [service_name]
        if conflicting_service_name:
            services_to_restart.append(conflicting_service_name)

        restart_results = []
        for svc in services_to_restart:
            try:
                restart_results.append({"service": svc, **_recreate_if_running(svc)})
            except Exception as e:
                restart_results.append(
                    {"service": svc, "restarted": False, "error": str(e)}
                )

        return jsonify(
            {
                "success": True,
                "message": f'Service "{service_name}" now on port 3301',
                "updates": updates_made,
                "restarts": restart_results,
            }
        ), 200

    except Exception as e:
        logger.error(f"Failed to set public port: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================
# API key management
# ============================================


@services_bp.route("/api/global-api-key", methods=["GET"])
@require_auth
def get_global_api_key():
    """Return the global API key (authentication required)"""
    try:
        if not GLOBAL_API_KEY:
            return jsonify(
                {"api_key": None, "message": "Global API key not configured"}
            ), 200

        return jsonify(
            {"api_key": GLOBAL_API_KEY, "message": "Global API key is configured"}
        ), 200

    except Exception as e:
        logger.error(f"Failed to get global API key: {e}")
        return jsonify(
            {"api_key": None, "error": "Failed to retrieve global API key"}
        ), 500


@services_bp.route("/api/services/<service_name>/set-global-api-key", methods=["PUT"])
@require_auth
def set_service_global_api_key(service_name):
    """
    Update a service's API key with the global API key from environment.
    The global API key is read from .env file, not received in the request.
    """
    try:
        if not GLOBAL_API_KEY:
            return jsonify(
                {
                    "success": False,
                    "error": "Global API key not configured. Please set LLM_DOCK_API_KEY in .env file.",
                }
            ), 400

        compose_mgr = ComposeManager(COMPOSE_FILE)

        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        old_api_key = service_config.get("api_key", "")
        service_config["api_key"] = GLOBAL_API_KEY
        compose_mgr.update_service_in_db(service_name, service_config)

        _rebuild_and_restart(compose_mgr, service_name)

        logger.info(f"Service '{service_name}' API key updated to global API key")

        return jsonify(
            {
                "success": True,
                "service_name": service_name,
                "old_api_key": old_api_key[:10] + "..." if old_api_key else None,
                "new_api_key": GLOBAL_API_KEY[:10] + "...",
                "message": f'Service "{service_name}" API key updated successfully',
            }
        ), 200

    except Exception as e:
        logger.error(f"Failed to set global API key: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
