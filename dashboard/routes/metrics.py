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

# Emitted by the ninfer-metrics.patch engine route (12 unlabeled families rendered
# from the engine's published RuntimeStats snapshot plus the startup-resolved KV
# capacity). Spec-acceptance and preemption families are deliberately absent: NInfer
# has no service-level aggregate for either, so the panel renders those as "—" (see
# docs/plans/ninfer-metrics.md).
NINFER_CURATED_METRICS = {
    "ninfer:prompt_tokens_total",
    "ninfer:generation_tokens_total",
    "ninfer:decode_rounds_total",
    "ninfer:num_requests_running",
    "ninfer:num_requests_waiting",
    "ninfer:num_requests_prefilling",
    "ninfer:kv_cache_usage_perc",
    "ninfer:kv_occupied_pages",
    "ninfer:kv_capacity_page_groups",
    "ninfer:prefix_cache_queries_total",
    "ninfer:prefix_cache_hits_total",
    "ninfer:host_kv_occupied_bytes",
}

# Curated set per engine: the whitelist keeps uninteresting families out.
CURATED_METRICS = {
    "vllm": VLLM_CURATED_METRICS,
    "llamacpp": LLAMACPP_CURATED_METRICS,
    "ninfer": NINFER_CURATED_METRICS,
}


def _get_service_config(service_name: str):
    from config import COMPOSE_FILE
    from compose_manager import ComposeManager

    mgr = ComposeManager(COMPOSE_FILE)
    return mgr.get_service_from_db(service_name)


def _parse_metrics(text: str, engine: str) -> dict:
    from prometheus_client.parser import text_string_to_metric_families

    curated = CURATED_METRICS.get(engine)
    if curated is None:
        return {}
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


def _fetch_metrics(host_port: int, engine: str, api_key: str = "") -> tuple:
    """Scrape the engine. Returns (metrics, error); error is None on a usable scrape."""
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(f"http://127.0.0.1:{host_port}/metrics", timeout=2, headers=headers)
    except requests.Timeout:
        return {}, "engine scrape timed out"
    except requests.RequestException as e:
        return {}, f"engine scrape failed: {e}"
    if resp.status_code != 200:
        return {}, f"engine returned {resp.status_code}"
    return _parse_metrics(resp.text, engine), None


# Only the first failure in a streak is logged as a warning: the panel polls several times a
# second, so an engine that is busy or down would otherwise bury the log, while a silent debug
# line leaves the panel's empty state undiagnosable.
_scrape_failure_streaks = {}


def _log_scrape_failure(service_name: str, reason: str) -> None:
    streak = _scrape_failure_streaks.get(service_name, 0) + 1
    _scrape_failure_streaks[service_name] = streak
    if streak == 1:
        logger.warning(f"Metrics scrape failed for '{service_name}': {reason}")
    else:
        logger.debug(
            f"Metrics scrape failed for '{service_name}' ({streak} consecutive): {reason}"
        )


def _log_scrape_success(service_name: str) -> None:
    _scrape_failure_streaks.pop(service_name, None)


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
    engine = {"vllm": "vllm", "llamacpp": "llamacpp", "ninfer": "ninfer"}.get(template_type)
    if engine is None:
        return jsonify({
            "metrics": {},
            "engine": template_type,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "scrape_error": None,
        })

    host_port = config.get("port")
    if not host_port:
        return jsonify({
            "metrics": {},
            "engine": engine,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "scrape_error": "service has no host port",
        })

    api_key = config.get("api_key", "")
    metrics, scrape_error = _fetch_metrics(host_port, engine, api_key)
    if scrape_error:
        _log_scrape_failure(service_name, scrape_error)
    else:
        _log_scrape_success(service_name)

    return jsonify({
        "metrics": metrics,
        "engine": engine,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "scrape_error": scrape_error,
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
