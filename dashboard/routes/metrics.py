import logging
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify

from auth import require_auth

logger = logging.getLogger(__name__)

metrics_bp = Blueprint("metrics", __name__)

CURATED_METRICS = {
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


def _get_service_config(service_name: str):
    from config import COMPOSE_FILE
    from compose_manager import ComposeManager

    mgr = ComposeManager(COMPOSE_FILE)
    return mgr.get_service_from_db(service_name)


def _parse_metrics(text: str) -> dict:
    from prometheus_client.parser import text_string_to_metric_families

    result = {}
    try:
        families = text_string_to_metric_families(text)
    except Exception:
        return result

    for family in families:
        parsed_name = family.name
        # prometheus_client strips _total from counter names; match both forms
        canonical = None
        if parsed_name in CURATED_METRICS:
            canonical = parsed_name
        elif f"{parsed_name}_total" in CURATED_METRICS:
            canonical = f"{parsed_name}_total"
        if canonical is None:
            continue

        if canonical == "vllm:spec_decode_num_accepted_tokens_per_pos_total":
            # Flatten position labels to position_N keys
            metric_data = {}
            for sample in family.samples:
                pos = sample.labels.get("position")
                if pos is not None:
                    metric_data[f"position_{pos}"] = sample.value
            result[canonical] = metric_data
        else:
            metric_data = {}
            for sample in family.samples:
                # Use JSON-serializable label key
                if sample.labels:
                    key = tuple(sorted(sample.labels.items()))
                else:
                    key = "{}"
                metric_data[key] = sample.value
            result[canonical] = metric_data

    return result


def _fetch_metrics(host_port: int) -> dict:
    try:
        resp = requests.get(
            f"http://127.0.0.1:{host_port}/metrics", timeout=2
        )
        if resp.status_code != 200:
            logger.debug(f"Metrics endpoint returned {resp.status_code}")
            return {}
        return _parse_metrics(resp.text)
    except (requests.ConnectionError, requests.Timeout, requests.RequestException) as e:
        logger.debug(f"Failed to fetch metrics: {e}")
        return {}


@metrics_bp.route("/api/services/<service_name>/metrics", methods=["GET"])
@require_auth
def get_service_metrics(service_name):
    """Fetch curated Prometheus metrics for a vLLM service."""
    config = _get_service_config(service_name)
    if not config:
        return jsonify({"error": f"Service '{service_name}' not found"}), 404

    if config.get("template_type") != "vllm":
        return jsonify({"metrics": {}, "scraped_at": datetime.now(timezone.utc).isoformat()})

    host_port = config.get("port")
    if not host_port:
        return jsonify({"metrics": {}, "scraped_at": datetime.now(timezone.utc).isoformat()})

    metrics = _fetch_metrics(host_port)

    return jsonify({
        "metrics": metrics,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    })
