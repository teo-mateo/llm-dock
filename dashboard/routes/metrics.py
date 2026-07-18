import logging
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify

from auth import require_auth

logger = logging.getLogger(__name__)

metrics_bp = Blueprint("metrics", __name__)

VLLM_CURATED_METRICS = {
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "vllm:num_preemptions_total",
    "vllm:engine_sleep_state",
    "vllm:kv_cache_usage_perc",
    "vllm:prefix_cache_queries_total",
    "vllm:prefix_cache_hits_total",
    "vllm:prompt_tokens_total",
    "vllm:prompt_tokens_cached_total",
    "vllm:prompt_tokens_recomputed_total",
    "vllm:generation_tokens_total",
    "vllm:spec_decode_num_drafts_total",
    "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_per_pos_total",
    "vllm:estimated_flops_per_gpu_total",
    "vllm:estimated_read_bytes_per_gpu_total",
    "vllm:estimated_write_bytes_per_gpu_total",
}

LLAMACPP_CURATED_METRICS = {
    "llamacpp:prompt_tokens_total",
    "llamacpp:prompt_seconds_total",
    "llamacpp:tokens_predicted_total",
    "llamacpp:tokens_predicted_seconds_total",
    "llamacpp:n_decode_total",
    "llamacpp:n_tokens_max",
    "llamacpp:prompt_tokens_seconds",
    "llamacpp:predicted_tokens_seconds",
    "llamacpp:requests_processing",
    "llamacpp:requests_deferred",
    "llamacpp:n_busy_slots_per_decode",
}


def _get_service_config(service_name: str):
    from config import COMPOSE_FILE
    from compose_manager import ComposeManager

    mgr = ComposeManager(COMPOSE_FILE)
    return mgr.get_service_from_db(service_name)


def _parse_metrics(text: str, engine: str) -> dict:
    from prometheus_client.parser import text_string_to_metric_families

    curated = VLLM_CURATED_METRICS if engine == "vllm" else LLAMACPP_CURATED_METRICS
    result = {}
    try:
        families = text_string_to_metric_families(text)
    except Exception:
        return result

    for family in families:
        parsed_name = family.name
        canonical = None
        if parsed_name in curated:
            canonical = parsed_name
        elif f"{parsed_name}_total" in curated:
            canonical = f"{parsed_name}_total"
        if canonical is None:
            continue

        if engine == "vllm" and canonical == "vllm:spec_decode_num_accepted_tokens_per_pos_total":
            metric_data = {}
            for sample in family.samples:
                pos = sample.labels.get("position")
                if pos is not None:
                    metric_data[f"position_{pos}"] = sample.value
            result[canonical] = metric_data
        else:
            metric_data = {}
            for sample in family.samples:
                if sample.labels:
                    key = ";".join(f"{k}={v}" for k, v in sorted(sample.labels.items()))
                else:
                    key = "{}"
                metric_data[key] = sample.value
            result[canonical] = metric_data

    return result


def _fetch_metrics(host_port: int, engine: str, api_key: str = "") -> dict:
    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.get(
            f"http://127.0.0.1:{host_port}/metrics", timeout=2, headers=headers
        )
        if resp.status_code != 200:
            logger.debug(f"Metrics endpoint returned {resp.status_code}")
            return {}
        return _parse_metrics(resp.text, engine)
    except (requests.ConnectionError, requests.Timeout, requests.RequestException) as e:
        logger.debug(f"Failed to fetch metrics: {e}")
        return {}


def _fetch_slots(host_port: int, api_key: str = ""):
    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.get(
            f"http://127.0.0.1:{host_port}/slots", timeout=2, headers=headers
        )
        if resp.status_code != 200:
            logger.debug(f"Slots endpoint returned {resp.status_code}")
            return None
        return resp.json()
    except (requests.ConnectionError, requests.Timeout, requests.RequestException, ValueError) as e:
        logger.debug(f"Failed to fetch slots: {e}")
        return None


def _slim_slots(slots: list) -> list:
    slim = []
    for slot in slots:
        next_token = (slot.get("next_token") or [{}])[0]
        slim.append({
            "id": slot.get("id"),
            "is_processing": bool(slot.get("is_processing")),
            "id_task": slot.get("id_task"),
            "n_decoded": next_token.get("n_decoded", 0),
            "n_prompt_tokens": slot.get("n_prompt_tokens", 0),
            "n_prompt_tokens_processed": slot.get("n_prompt_tokens_processed", 0),
        })
    return slim


@metrics_bp.route("/api/services/<service_name>/metrics", methods=["GET"])
@require_auth
def get_service_metrics(service_name):
    """Fetch curated Prometheus metrics for a model service."""
    config = _get_service_config(service_name)
    if not config:
        return jsonify({"error": f"Service '{service_name}' not found"}), 404

    template_type = config.get("template_type")
    if template_type not in ("vllm", "llamacpp"):
        return jsonify({
            "metrics": {},
            "engine": template_type,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

    engine = "vllm" if template_type == "vllm" else "llamacpp"

    host_port = config.get("port")
    if not host_port:
        return jsonify({
            "metrics": {},
            "engine": engine,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

    api_key = config.get("api_key", "")
    metrics = _fetch_metrics(host_port, engine, api_key)

    return jsonify({
        "metrics": metrics,
        "engine": engine,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    })


@metrics_bp.route("/api/services/<service_name>/slots", methods=["GET"])
@require_auth
def get_service_slots(service_name):
    """Fetch live per-slot generation state for a llama.cpp service."""
    config = _get_service_config(service_name)
    if not config:
        return jsonify({"error": f"Service '{service_name}' not found"}), 404

    if config.get("template_type") != "llamacpp":
        return jsonify({"error": "Slots endpoint is only available for llamacpp services"}), 400

    host_port = config.get("port")
    if not host_port:
        return jsonify({
            "slots": [],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

    api_key = config.get("api_key", "")
    slots = _fetch_slots(host_port, api_key)
    if slots is None:
        return jsonify({
            "slots": None,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

    return jsonify({
        "slots": _slim_slots(slots),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    })
