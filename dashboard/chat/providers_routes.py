"""HTTP surface for model providers, registered onto chat_bp from chat/routes.py."""

import logging

from flask import jsonify, request

from auth import require_auth
from . import providers
from .blueprint import chat_bp

logger = logging.getLogger(__name__)


def _settings_payload() -> dict:
    return {"providers": providers.list_providers(), "presets": providers.PRESETS}


@chat_bp.route("/api/chat/settings/providers", methods=["GET"])
@require_auth
def list_model_providers():
    return jsonify(_settings_payload())


@chat_bp.route("/api/chat/settings/providers/<provider_id>", methods=["PUT"])
@require_auth
def put_model_provider(provider_id):
    body = request.get_json(silent=True)
    try:
        entry = providers.upsert_provider(provider_id, body)
    except providers.ProviderError as e:
        return jsonify({"error": str(e)}), 400
    logger.info("provider '%s' saved (key source: %s)", provider_id, entry["key_source"])
    return jsonify(_settings_payload())


@chat_bp.route("/api/chat/settings/providers/<provider_id>", methods=["DELETE"])
@require_auth
def delete_model_provider(provider_id):
    if not providers.delete_provider(provider_id):
        return jsonify({"error": f"provider '{provider_id}' not found"}), 404
    logger.info("provider '%s' deleted", provider_id)
    return jsonify(_settings_payload())


@chat_bp.route("/api/chat/settings/providers/<provider_id>/test", methods=["POST"])
@require_auth
def test_model_provider(provider_id):
    entry = providers.get_provider(provider_id)
    if entry is None:
        return jsonify({"error": f"provider '{provider_id}' not found"}), 404
    try:
        models, _ = providers.fetch_models(provider_id, entry, force=True, serve_stale=False)
    except providers.ProviderUnavailable as e:
        return jsonify({"ok": False, "error": str(e), "model_count": 0})
    return jsonify({"ok": True, "error": None, "model_count": len(models)})


@chat_bp.route("/api/chat/providers/models", methods=["GET"])
@require_auth
def list_provider_models():
    force = request.args.get("refresh") in ("1", "true")
    return jsonify({"providers": providers.models_payload(force=force)})
