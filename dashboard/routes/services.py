import json
import logging
import threading
import time
import subprocess
from datetime import datetime
from typing import Generator
from flask import Blueprint, jsonify, request, Response, stream_with_context, current_app

from auth import require_auth
from db_lock import SERVICES_DB_LOCK, serialize_db
import config
from config import COMPOSE_FILE
from compose_manager import ComposeManager
from docker_utils import get_docker_services, get_service_container, control_service
from model_discovery import compute_model_size
from service_templates import generate_api_key
from key_rotation import rotate_keys_in_db
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

# Shared across all blueprints — see db_lock.py. Aliased to preserve the
# existing private-looking names used throughout this module.
_SERVICES_DB_LOCK = SERVICES_DB_LOCK
_serialize_db = serialize_db
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

        # Compute model size on-the-fly
        size, size_str = compute_model_size(
            config.get("model_path"), config.get("model_name")
        )
        config["model_size"] = size
        config["model_size_str"] = size_str

        return jsonify({"service_name": service_name, "config": config}), 200

    except Exception as e:
        logger.error(f"Failed to get service: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# Service control (start/stop)
# ============================================


@services_bp.route("/api/services/<service_name>/start", methods=["POST"])
@require_auth
@_serialize_db
def start_service(service_name):
    """Start a Docker Compose service.

    Serialized on the shared lock so a start can't `docker compose up` with
    the pre-rotation compose file mid-rotation and bring a container up on
    the just-revoked key (rotation only stops the containers it snapshotted
    as running, so such a container would otherwise be missed).
    """
    result = control_service(service_name, "start")

    if result["success"]:
        logger.info(f"Started service: {service_name}")
        return jsonify(result)
    else:
        logger.warning(f"Failed to start service {service_name}: {result.get('error')}")
        return jsonify(result), 400


@services_bp.route("/api/services/<service_name>/stop", methods=["POST"])
@require_auth
@_serialize_db
def stop_service(service_name):
    """Stop a Docker Compose service (serialized on the shared lock for
    symmetry with start/rotation)."""
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
@_serialize_db
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
        if template_type not in ["llamacpp", "vllm", "ds4"]:
            return jsonify({"error": 'template_type must be "llamacpp", "vllm", or "ds4"'}), 400

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
@_serialize_db
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
@_serialize_db
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

        from services import event_manager
        event_manager.emit({
            "service_name": service_name,
            "action": "service-deleted",
            "status": "deleted",
            "container_id": "",
            "timestamp": time.time(),
        })

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
@_serialize_db
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
        if template_type not in ["llamacpp", "llamacpp_bench", "vllm", "ds4"]:
            return jsonify({"error": 'template_type must be "llamacpp", "llamacpp_bench", "vllm", or "ds4"'}), 400

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
@_serialize_db
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


@services_bp.route("/api/services/<service_name>/favorite", methods=["POST"])
@require_auth
@_serialize_db
def set_favorite(service_name):
    """Set or unset the favorite flag for a service."""
    try:
        if service_name == "open-webui":
            return jsonify({"error": "Cannot favorite infrastructure services"}), 400

        data = request.get_json(silent=True) or {}
        favorite = bool(data.get("favorite", True))

        compose_mgr = ComposeManager(COMPOSE_FILE)
        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        service_config["favorite"] = favorite
        compose_mgr.update_service_in_db(service_name, service_config)

        from services import event_manager
        event_manager.emit({
            "service_name": service_name,
            "action": "metadata-changed",
            "status": None,
            "container_id": None,
            "metadata": {"favorite": favorite},
            "timestamp": time.time(),
        })

        logger.info(f"Service favorite updated: {service_name} -> {favorite}")
        return jsonify({"success": True, "favorite": favorite}), 200

    except Exception as e:
        logger.error(f"Failed to update favorite: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================
# SSE helpers
# ============================================

def _sse_data(payload: dict) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ============================================
# SSE Stream Endpoint
# ============================================

# Event type constants for SSE messages
SSE_SNAPSHOT = "snapshot"
SSE_DELTA = "delta"
SSE_ERROR = "error"


@services_bp.route("/api/services/stream", methods=["GET"])
@require_auth
def services_stream():
    """Stream service status updates over Server-Sent Events.

    Yields an initial snapshot of all services on connect,
    then streams delta updates as Docker events occur.
    """
    from services import event_manager

    def generate() -> Generator[str, None, None]:
        callback = None
        try:
            logger.info("SSE client connected to /api/services/stream")

            snapshot = event_manager.get_services_snapshot()
            payload = {
                "type": SSE_SNAPSHOT,
                "data": {
                    "services": snapshot,
                    "total": len(snapshot),
                    "running": sum(1 for s in snapshot if s["status"] == "running"),
                    "stopped": sum(1 for s in snapshot if s["status"] != "running"),
                },
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            yield "data: " + json.dumps(payload) + "\n\n"

            events_queue = []

            def on_event(event):
                """Callback that queues events for the SSE stream."""
                events_queue.append(event)

            callback = on_event
            event_manager.register_callback(callback)

            while True:
                if events_queue:
                    event = events_queue.pop(0)
                    payload = {
                        "type": SSE_DELTA,
                        "service_name": event["service_name"],
                        "status": event["status"],
                        "action": event["action"],
                        "container_id": event["container_id"],
                        "timestamp": datetime.fromtimestamp(event["timestamp"]).isoformat() + "Z",
                    }
                    yield "data: " + json.dumps(payload) + "\n\n"
                else:
                    yield ": keepalive\n\n"
                    time.sleep(5)

        except GeneratorExit:
            logger.info("SSE client disconnected")
        except Exception as e:
            current_app.logger.error("SSE stream error: %s", e)
            error_payload = {"type": SSE_ERROR, "message": str(e)}
            yield "data: " + json.dumps(error_payload) + "\n\n"
        finally:
            if callback:
                event_manager.unregister_callback(callback)
                logger.debug("SSE callback unregistered")

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================
# Service Logs SSE Endpoint
# ============================================


@services_bp.route("/api/services/<service_name>/logs/stream", methods=["GET"])
@require_auth
def stream_service_logs(service_name):
    """Stream container logs over SSE.

    Sends an initial tail snapshot followed by live appended lines.
    Keepalives are sent every ~5 s when the container is quiet.
    The existing JSON endpoint /api/services/<name>/logs is unchanged.
    """
    from services.log_stream import iter_log_events

    container = get_service_container(service_name)
    if not container:
        return jsonify({"error": "Service has not been created yet"}), 404

    tail = request.args.get("tail", default=200, type=int)
    tail = min(max(tail, 1), 1000)

    def generate():
        stop = threading.Event()
        try:
            yield _sse_data({"type": "snapshot_start", "service": service_name, "timestamp": _now()})
            for event_type, data in iter_log_events(container, tail, stop):
                if event_type == "log":
                    yield _sse_data({"type": "log", "service": service_name, "line": data})
                elif event_type == "snapshot_end":
                    yield _sse_data({"type": "snapshot_end", "service": service_name, "timestamp": _now()})
                elif event_type == "stream_end":
                    yield _sse_data({"type": "stream_end", "service": service_name, "timestamp": _now()})
                elif event_type == "error":
                    yield _sse_data({"type": "error", "service": service_name, "message": data})
                elif event_type == "keepalive":
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            stop.set()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


# ============================================
# API key management
# ============================================


@services_bp.route("/api/global-api-key", methods=["GET"])
@require_auth
def get_global_api_key():
    """Return the global API key (authentication required)"""
    try:
        if not config.GLOBAL_API_KEY:
            return jsonify(
                {"api_key": None, "message": "Global API key not configured"}
            ), 200

        return jsonify(
            {"api_key": config.GLOBAL_API_KEY, "message": "Global API key is configured"}
        ), 200

    except Exception as e:
        logger.error(f"Failed to get global API key: {e}")
        return jsonify(
            {"api_key": None, "error": "Failed to retrieve global API key"}
        ), 500


@services_bp.route("/api/services/<service_name>/set-global-api-key", methods=["PUT"])
@require_auth
@_serialize_db
def set_service_global_api_key(service_name):
    """
    Update a service's API key with the global API key from environment.
    The global API key is read from .env file, not received in the request.
    """
    try:
        if not config.GLOBAL_API_KEY:
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
        service_config["api_key"] = config.GLOBAL_API_KEY
        compose_mgr.update_service_in_db(service_name, service_config)

        _rebuild_and_restart(compose_mgr, service_name)

        logger.info(f"Service '{service_name}' API key updated to global API key")

        return jsonify(
            {
                "success": True,
                "service_name": service_name,
                "old_api_key": old_api_key[:10] + "..." if old_api_key else None,
                "new_api_key": config.GLOBAL_API_KEY[:10] + "...",
                "message": f'Service "{service_name}" API key updated successfully',
            }
        ), 200

    except Exception as e:
        logger.error(f"Failed to set global API key: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


def _affected_services_state():
    """Return (db_service_names, running, openwebui_registered) for rotation.

    Only services present in services.json are affected by a rotation; infra
    containers like open-webui are never in services.json so they're excluded
    naturally.
    """
    compose_mgr = ComposeManager(COMPOSE_FILE)
    db_services = set(compose_mgr.list_services_in_db().keys())

    running = []
    openwebui_registered = []
    for svc in get_docker_services():
        name = svc["name"]
        if name not in db_services:
            continue
        if svc.get("status") == "running":
            running.append(name)
        if svc.get("openwebui_registered"):
            openwebui_registered.append(name)

    return sorted(db_services), sorted(running), sorted(openwebui_registered)


@services_bp.route("/api/default-api-key/rotation-preview", methods=["GET"])
@require_auth
def default_api_key_rotation_preview():
    """Describe the impact of rotating the default API key without changing anything."""
    try:
        db_services, running, openwebui_registered = _affected_services_state()
        return jsonify(
            {
                "total_services": len(db_services),
                "running": running,
                "openwebui_registered": openwebui_registered,
            }
        ), 200
    except Exception as e:
        logger.error(f"Failed to build rotation preview: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@services_bp.route("/api/default-api-key/rotate", methods=["POST"])
@require_auth
def rotate_default_api_key():
    """Rotate the default API key.

    Generates a new key, persists it to .env (LLM_DOCK_API_KEY), rewrites every
    service's api_key in services.json, regenerates docker-compose.yml, and
    stops every running affected container (they keep the revoked key in memory
    until restarted). Open WebUI's stored copies are NOT touched — registered
    services are reported back so the user can re-enter the key manually.
    """
    try:
        with _SERVICES_DB_LOCK:
            db_services, running, openwebui_registered = _affected_services_state()

            new_key = generate_api_key()
            compose_mgr = ComposeManager(COMPOSE_FILE)

            # Snapshot before any mutation so a late failure can fully roll back.
            services_before = compose_mgr.list_services_in_db()

            # Commit the riskiest, validated work (services.json + compose)
            # FIRST. rotate_keys_in_db self-rolls-back services.json/compose
            # on failure, so if this raises nothing has been changed and .env
            # is untouched.
            result = rotate_keys_in_db(compose_mgr, new_key)

            # Only now commit .env / in-process key. If this fails, undo the
            # services.json + compose changes so we never advertise a new key
            # while files still hold the old one (or vice versa).
            try:
                config.set_global_api_key(new_key)
            except Exception:
                compose_mgr.save_services_db(services_before)
                compose_mgr.rebuild_compose_file()
                raise

            stopped = []
            stop_errors = {}
            for name in running:
                res = control_service(name, "stop")
                if res.get("success"):
                    stopped.append(name)
                else:
                    stop_errors[name] = res.get("error", "unknown error")

        # A failed stop is a partial failure: the key is rotated in
        # services.json/.env, but that container keeps accepting the OLD key
        # in memory until stopped. Don't report unqualified success — callers
        # that key off `success`/HTTP status must not treat the old key as
        # revoked when it isn't.
        ok = not stop_errors

        logger.info(
            "Default API key rotated: %d services updated, %d stopped, %d stop failures",
            len(result["updated"]),
            len(stopped),
            len(stop_errors),
        )

        if ok:
            message = (
                f"Default API key rotated across {len(result['updated'])} "
                f"service(s); {len(stopped)} running container(s) stopped."
            )
        else:
            message = (
                f"Default API key rotated across {len(result['updated'])} "
                f"service(s), but {len(stop_errors)} running container(s) "
                f"could NOT be stopped and still accept the OLD key — stop "
                f"them manually: {', '.join(sorted(stop_errors))}."
            )

        return jsonify(
            {
                "success": ok,
                "partial": not ok,
                "new_api_key": new_key,
                "services_updated": len(result["updated"]),
                "total_services": len(db_services),
                "stopped": stopped,
                "stop_errors": stop_errors,
                "openwebui_registered": openwebui_registered,
                "message": message,
            }
        ), (200 if ok else 207)

    except Exception as e:
        logger.error(f"Failed to rotate default API key: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
