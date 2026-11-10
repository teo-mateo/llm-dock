"""HTTP surface for the curated OpenRouter model list and the live OpenRouter catalog."""

import logging

from flask import jsonify, request

from auth import require_auth
from reasoning_levels import parse_levels

from . import openrouter, openrouter_catalog, settings_store
from .blueprint import chat_bp

logger = logging.getLogger(__name__)


# -- Settings: curated OpenRouter model list --

def _catalog_reasoning_meta():
    """Model id to upstream reasoning metadata, from the cached catalogue.

    ``None`` means the catalogue could not be read, which the caller must distinguish
    from "the model has no reasoning capability": the first is worth another try at
    refresh, the second is the answer. Never raises -- a ladder is a network fact, and
    losing one costs a model its control, not the user their save.
    """
    try:
        payload = openrouter_catalog.fetch()
    except openrouter_catalog.CatalogUnavailable:
        logger.warning("openrouter: catalogue unavailable; storing models without ladders")
        return None
    return {
        entry["id"]: entry.get("reasoning_meta")
        for entry in payload.get("models", [])
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }


def _derive_ladders(models, known_ids):
    """``(ladders, status)`` for the ids in ``models`` that have no stored ladder yet.

    Derivation belongs here rather than in the store because only this layer can see the
    catalogue, and it belongs to the write path because the field is server-owned: a
    request body cannot set a ladder, so the server has to supply it at the moment a
    model first appears.
    """
    meta_by_id = _catalog_reasoning_meta()
    ladders, status = {}, {}
    for entry in models:
        model = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(model, str) or not model.strip() or model.strip() in known_ids:
            continue
        model = model.strip()
        if meta_by_id is None:
            status[model] = "unavailable"
            continue
        ladders[model] = openrouter.ladder_from_reasoning(meta_by_id.get(model))
        status[model] = "derived" if ladders[model] else "none"
    return ladders, status


def _openrouter_models_payload() -> list:
    """The curated list as a projection, with every ladder parsed.

    Deliberately not the stored string: this is the shape a local service's
    ``reasoning_levels`` already has on ``GET /api/services``, so the composer offers one
    shape for both providers instead of branching on where a model is hosted.
    """
    records = []
    for entry in settings_store.get_openrouter_models():
        levels = parse_levels(entry.get("reasoning_levels"))
        record = {"id": entry["id"], "label": entry.get("label") or entry["id"]}
        if levels:
            record["reasoning_levels"] = levels
        records.append(record)
    return records


def _openrouter_settings_payload() -> dict:
    """Shape returned by every openrouter-models settings endpoint.

    ``configured`` tells the frontend whether OPENROUTER_API_KEY is set —
    the chat picker hides the OpenRouter group when it isn't, while the
    Settings-page picker stays usable and just shows a banner.
    """
    return {
        "configured": openrouter.is_configured(),
        "current": _openrouter_models_payload(),
        "builtin": openrouter.DEFAULT_MODELS,
        "customized": settings_store.is_openrouter_models_customized(),
    }


@chat_bp.route("/api/chat/settings/openrouter-models", methods=["GET"])
@require_auth
def get_openrouter_models_setting():
    return jsonify(_openrouter_settings_payload())


@chat_bp.route("/api/chat/settings/openrouter-models", methods=["PUT"])
@require_auth
def put_openrouter_models_setting():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be {models: [{id, label?}]}"}), 400
    models = data.get("models")
    known_ids = {entry["id"] for entry in settings_store.get_openrouter_models()}
    ladders, status = _derive_ladders(models if isinstance(models, list) else [], known_ids)
    try:
        settings_store.set_openrouter_models(models, ladders)
    except (TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    logger.info(
        "openrouter model list updated (%d models, %d ladders derived)", len(models), len(ladders)
    )
    payload = _openrouter_settings_payload()
    payload["ladders"] = status
    return jsonify(payload)


@chat_bp.route("/api/chat/settings/openrouter-models/refresh", methods=["POST"])
@require_auth
def refresh_openrouter_ladders():
    """Re-derive the ladder for named shortlist models from the live catalogue.

    Derivation on the write path fires only for models appearing for the first time, and
    the merge preserves what a model already has, so without this route a shortlist
    saved before the feature could never gain a ladder, and a ladder could never follow
    upstream changing a model's efforts. Ids outside the shortlist are reported rather
    than added; the caller named models it believes it has.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("ids"), list):
        return jsonify({"error": "body must be {ids: [model-id, ...]}"}), 400

    stored = settings_store.get_openrouter_models()
    known_ids = {entry["id"] for entry in stored}
    meta_by_id = _catalog_reasoning_meta()
    ladders, status, missing = {}, {}, []
    for model in data["ids"]:
        if not isinstance(model, str) or not model.strip():
            continue
        model = model.strip()
        if model not in known_ids:
            missing.append(model)
            continue
        if meta_by_id is None:
            status[model] = "unavailable"
            continue
        ladders[model] = openrouter.ladder_from_reasoning(meta_by_id.get(model))
        status[model] = "derived" if ladders[model] else "none"

    if ladders:
        settings_store.set_openrouter_models(stored, ladders)
        logger.info("openrouter ladders refreshed for %d model(s)", len(ladders))
    payload = _openrouter_settings_payload()
    payload["ladders"] = status
    payload["missing"] = missing
    return jsonify(payload)


@chat_bp.route("/api/chat/settings/openrouter-models", methods=["DELETE"])
@require_auth
def delete_openrouter_models_setting():
    """Drop any customization, reverting the picker to the built-in list."""
    settings_store.reset_openrouter_models()
    logger.info("openrouter model list reset to built-in")
    return jsonify(_openrouter_settings_payload())


# -- Live OpenRouter catalog (backs the model picker) --

@chat_bp.route("/api/chat/settings/openrouter-catalog", methods=["GET"])
@require_auth
def get_openrouter_catalog():
    """Live OpenRouter catalog, proxied and TTL-cached server-side.

    ``?refresh=1`` bypasses the cache (the picker's Refresh button); ``?detail=1``
    adds each model's truncated description. ``configured`` rides along so one
    round-trip drives both the picker and the "key not set" banner. What upstream
    still offers is exactly the ids in ``models``, so nothing else rides along for
    it — a parallel id list would be the same 400-odd strings again. Not gated on
    the API key: upstream is public, so authoring the list works before the key
    exists.
    """
    force = request.args.get("refresh") in ("1", "true")
    detail = request.args.get("detail") in ("1", "true")
    try:
        payload = openrouter_catalog.fetch(force=force, detail=detail)
    except openrouter_catalog.CatalogUnavailable as exc:
        return jsonify({"error": f"OpenRouter catalog unavailable: {exc}", "models": [], "count": 0}), 502
    payload["configured"] = openrouter.is_configured()
    return jsonify(payload)


@chat_bp.route("/api/chat/settings/openrouter-catalog/endpoints", methods=["POST"])
@require_auth
def post_openrouter_catalog_endpoints():
    """Per-provider detail (price, quantization, context, uptime) for a batch of
    model ids.

    Provider names are not in the model list, so this fans out to
    ``/models/{id}/endpoints`` per id and caches per id. Only ids that are not
    already fresh are fetched, so a repeated page of rows costs nothing; a
    partially failing batch still returns whatever succeeded and names the rest
    in ``missing``. Ids are checked against :data:`MODEL_ID_RE` because each one
    becomes a request path — but an id that fails the check costs its own row, not
    the batch: it is reported in ``missing`` and the rest of the page is fetched.
    The picker only ever sends ids it read out of the catalog, so a rejection can
    mean one thing — upstream has started shipping a shape this check does not
    know — which is exactly when failing the whole batch would be wrong. Only a
    batch with nothing usable in it is a 400.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "body must be {ids: [...]}"}), 400
    raw_ids = body.get("ids")
    if not isinstance(raw_ids, list):
        return jsonify({"error": "ids must be a list of model ids"}), 400
    ids = []
    rejected = []
    for value in raw_ids:
        if not isinstance(value, str) or not value.strip():
            return jsonify({"error": "each id must be a non-empty string"}), 400
        model_id = value.strip()
        wanted = ids if openrouter_catalog.MODEL_ID_RE.fullmatch(model_id) else rejected
        if model_id not in wanted:
            wanted.append(model_id)
    if len(ids) > openrouter_catalog.MAX_PROVIDER_IDS:
        return jsonify({"error": f"too many ids (max {openrouter_catalog.MAX_PROVIDER_IDS})"}), 400
    if not ids:
        if rejected:
            return jsonify({"error": f"invalid model ids: {', '.join(rejected[:3])}"}), 400
        return jsonify({"models": {}, "missing": [], "stale": [], "fetched": 0, "cached": 0})
    payload = openrouter_catalog.summarize_endpoints(ids, force=bool(body.get("force")))
    if rejected:
        logger.warning("provider detail skipped %d malformed id(s): %s", len(rejected), rejected[:5])
        payload["missing"] += rejected
    return jsonify(payload)
