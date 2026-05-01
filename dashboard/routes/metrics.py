import logging
import re
import requests
from flask import Blueprint, jsonify
from prometheus_client.parser import text_string_to_metric_families


def _preprocess_prometheus_text(raw_text: str) -> str:
    """Quote unquoted label values so prometheus_client v0.25+ can parse them.

    Prometheus spec requires quoted values. vLLM outputs unquoted strings with
    hyphens/dots (e.g. `model_name=qwen3.6-35b-a3b`) that the strict parser
    rejects. This normalizes them without altering metrics data.
    """
    def _quote_labels_block(block: str) -> str:
        """Quote unquoted label values inside a {labels} block."""
        parts = []
        depth = 0
        current = ""
        for ch in block:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += ch
        if current.strip():
            parts.append(current.strip())

        result = []
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                k = k.strip()
                v = v.strip()
                if not (v.startswith('"') and v.endswith('"')):
                    v = f'"{v}"'
                result.append(f"{k}={v}")
            else:
                result.append(part)
        return ",".join(result)

    return re.sub(r"\{([^}]*)\}", lambda m: "{" + _quote_labels_block(m.group(1)) + "}", raw_text)

from auth import require_auth
from config import COMPOSE_FILE
from compose_manager import ComposeManager

logger = logging.getLogger(__name__)

metrics_bp = Blueprint("metrics", __name__)

# Curated subset of vLLM Prometheus metrics to surface in the dashboard.
# Key = metric family name (without "vllm:" prefix as reported by parser).
CURATED_METRICS = {
    # Load
    "num_requests_running",
    "num_requests_waiting",
    "num_preemptions_total",
    "engine_sleep_state",
    # KV & prefix cache
    "kv_cache_usage_perc",
    "prefix_cache_queries_total",
    "prefix_cache_hits_total",
    # Token throughput
    "prompt_tokens_total",
    "prompt_tokens_cached_total",
    "prompt_tokens_recomputed_total",
    "generation_tokens_total",
    # Spec decode
    "spec_decode_num_drafts_total",
    "spec_decode_num_draft_tokens_total",
    "spec_decode_num_accepted_tokens_total",
    "spec_decode_num_accepted_tokens_per_pos",
    # MFU inputs
    "estimated_flops_per_gpu_total",
    "estimated_read_bytes_per_gpu_total",
    "estimated_write_bytes_per_gpu_total",
}


def _pre_aggregate(metric_name, samples):
    """Aggregate metric samples into a pre-computed dict for the frontend.

    Most metrics have a single value (possibly differentiated by `model_name`).
    The per-position spec-decode metric has two label dims (pos, accepted) and
    gets collapsed to {pos: acceptance_pct}.
    """
    if metric_name == "spec_decode_num_accepted_tokens_per_pos":
        # labels: pos, accepted  →  {pos_str: sum_of_values_as_pct}
        buckets = {}
        for s in samples:
            pos = s.labels.get("pos", "0")
            value = s.value
            buckets[str(pos)] = buckets.get(str(pos), 0.0) + value
        total = sum(buckets.values())
        if total > 0:
            return {k: round(v / total * 100, 1) for k, v in buckets.items()}
        return buckets

    # Default: group by `model_name` label (or bare value if absent).
    result = {}
    for s in samples:
        model = s.labels.get("model_name", "default")
        if model != "default" and model in result:
            # Handle duplicate model_name — key is actually the metric prefix
            model = model
        result[model] = s.value
    return result


@metrics_bp.route("/api/services/<service_name>/metrics", methods=["GET"])
@require_auth
def get_service_metrics(service_name):
    try:
        compose_mgr = ComposeManager(COMPOSE_FILE)
        config = compose_mgr.get_service_from_db(service_name)

        if not config:
            return jsonify({"error": f'Service "{service_name}" not found'}), 404

        if config.get("template_type") != "vllm":
            return jsonify({})

        port = config.get("port")
        if not port:
            return jsonify({})

        resp = requests.get(
            f"http://localhost:{port}/metrics",
            timeout=2,
        )

        if resp.status_code != 200:
            return jsonify({})

        raw_text = resp.text
        families = text_string_to_metric_families(_preprocess_prometheus_text(raw_text))

        result = {}
        for family in families:
            name = family.name

            # Handle nested names like "vllm:avg_prompt_throughput"
            # Remove "vllm:" prefix if present
            if name.startswith("vllm:"):
                name = name[5:]
            elif name.startswith("vllm_"):
                name = name.replace("_", "-", 1)

            # prometheus_client strips trailing _total from counter family
            # names, so check the stripped variant (e.g. "num_preemptions" →
            # look up "num_preemptions_total" in the set)
            lookup = name
            if name not in CURATED_METRICS:
                if name.endswith("_counter"):
                    lookup = name[:-8]
                elif not name.endswith("_total") and f"{name}_total" in CURATED_METRICS:
                    lookup = f"{name}_total"
                else:
                    continue

            # Collect samples for this metric family
            samples = list(family.samples)

            # Apply pre-aggregation transformation
            aggregated = _pre_aggregate(lookup, samples)
            result[f"vllm:{lookup}"] = aggregated

        return jsonify(result)

    except Exception:
        logger.exception(f"Failed to fetch metrics for service '{service_name}'")
        return jsonify({}), 200
