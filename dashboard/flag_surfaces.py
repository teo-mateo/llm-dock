"""Recorded per-engine flag surfaces, and the unknown-param check for service writes.

The JSON snapshots in flag_surfaces/ are recorded from each engine's own image by
scripts/record-flag-surfaces.py. tests/test_flag_surface_guard.py guards the curated
metadata against them; unknown_service_params() applies the same surface to
operator-typed params at service create/update, which is where the typo trap lives
(render_cli_flag passes any dash-prefixed string through to the container verbatim).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flag_surfaces")

# template type -> snapshot engine (ik_llamacpp shares the llama.cpp server surface:
# get_flag_metadata serves the same dict for both)
TEMPLATE_TYPE_TO_ENGINE = {
    "llamacpp": "llamacpp_server",
    "ik_llamacpp": "llamacpp_server",
    "llamacpp_bench": "llamacpp_bench",
    "vllm": "vllm",
    "ds4": "ds4",
    "tabbyapi": "tabbyapi",
    "ninfer": "ninfer",
}


def known_flags(template_type: str) -> set:
    engine = TEMPLATE_TYPE_TO_ENGINE.get(template_type)
    if engine is None:
        return set()
    path = os.path.join(SNAP_DIR, f"{engine}.json")
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return set(json.load(f)["flags"])


def unknown_service_params(template_type: str, params: dict) -> list:
    """Dash-prefixed param names the engine's recorded surface does not know.

    Advisory only: the flag still ships to the container verbatim and fails there,
    so a flag the engine accepts but the snapshot has not recorded (upstream just
    added it) must not be treated as an error. An unmapped engine or a missing
    snapshot returns [] rather than blocking the write.
    """
    surface = known_flags(template_type)
    if not surface:
        return []
    return sorted(
        flag
        for flag in (params or {})
        if str(flag).startswith("-") and flag not in surface
    )
