import logging
import subprocess
from flask import Blueprint, jsonify, request

from auth import require_auth
from config import COMPOSE_FILE
from compose_manager import ComposeManager
from openwebui_integration import (
    add_service_to_openwebui,
    remove_service_from_openwebui,
    is_service_registered_in_openwebui,
)

logger = logging.getLogger(__name__)

openwebui_bp = Blueprint("openwebui", __name__)


@openwebui_bp.route("/api/services/<service_name>/register-openwebui", methods=["POST"])
@require_auth
def register_service_openwebui(service_name):
    """Manually register a service with Open WebUI."""
    try:
        logger.info(f"=== MANUAL REGISTER OPENWEBUI REQUEST for {service_name} ===")
        compose_mgr = ComposeManager(COMPOSE_FILE)

        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        engine = service_config.get("template_type", "")
        port = service_config.get("port", 0)
        api_key = service_config.get("api_key", "")

        if not engine:
            return jsonify({"error": "Service has no template_type configured"}), 400

        if is_service_registered_in_openwebui(service_name, engine):
            return jsonify(
                {
                    "success": True,
                    "message": f'Service "{service_name}" is already registered with Open WebUI',
                    "already_registered": True,
                }
            ), 200

        success = add_service_to_openwebui(service_name, port, api_key, engine)

        if success:
            return jsonify(
                {
                    "success": True,
                    "message": f'Service "{service_name}" registered with Open WebUI',
                }
            ), 200
        else:
            return jsonify(
                {
                    "success": False,
                    "error": "Failed to register service with Open WebUI. Check dashboard logs.",
                }
            ), 500

    except Exception as e:
        logger.error(f"Failed to register service with Open WebUI: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@openwebui_bp.route("/api/services/<service_name>/unregister-openwebui", methods=["POST"])
@require_auth
def unregister_service_openwebui(service_name):
    """Manually unregister a service from Open WebUI."""
    try:
        logger.info(f"=== MANUAL UNREGISTER OPENWEBUI REQUEST for {service_name} ===")
        compose_mgr = ComposeManager(COMPOSE_FILE)

        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        engine = service_config.get("template_type", "")

        if not engine:
            return jsonify({"error": "Service has no template_type configured"}), 400

        if not is_service_registered_in_openwebui(service_name, engine):
            return jsonify(
                {
                    "success": True,
                    "message": f'Service "{service_name}" is not registered with Open WebUI',
                    "already_unregistered": True,
                }
            ), 200

        success = remove_service_from_openwebui(service_name, engine)

        if success:
            return jsonify(
                {
                    "success": True,
                    "message": f'Service "{service_name}" unregistered from Open WebUI',
                }
            ), 200
        else:
            return jsonify(
                {
                    "success": False,
                    "error": "Failed to unregister service from Open WebUI. Check dashboard logs.",
                }
            ), 500

    except Exception as e:
        logger.error(
            f"Failed to unregister service from Open WebUI: {e}", exc_info=True
        )
        return jsonify({"error": str(e)}), 500


@openwebui_bp.route("/api/openwebui/restart", methods=["POST"])
@require_auth
def restart_openwebui():
    """Restart the Open WebUI container to apply configuration changes."""
    try:
        logger.info("=== RESTARTING OPEN WEBUI CONTAINER ===")

        result = subprocess.run(
            ["docker", "restart", "open-webui"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            logger.error(f"Failed to restart Open WebUI: {result.stderr}")
            return jsonify(
                {"success": False, "error": f"Failed to restart: {result.stderr}"}
            ), 500

        logger.info("Open WebUI container restarted successfully")
        return jsonify(
            {"success": True, "message": "Open WebUI restarted successfully"}
        ), 200

    except subprocess.TimeoutExpired:
        logger.error("Timeout while restarting Open WebUI")
        return jsonify(
            {"success": False, "error": "Timeout while restarting Open WebUI"}
        ), 500
    except Exception as e:
        logger.error(f"Failed to restart Open WebUI: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
