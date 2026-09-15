import glob
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flag_metadata import get_flag_metadata

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(DASHBOARD_DIR)
SNAP_DIR = os.path.join(DASHBOARD_DIR, "flag_surfaces")

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

# Entries the guard found to be absent from the engine's recorded surface
# (2026-09-15, measured; full evidence on #207). The test asserts each of them is
# STILL absent below, so this list can only shrink, and only when the entry is
# fixed (rename/delete) in flag_metadata.py and dropped here in the same change.
STALE = {}


def load_surface(engine):
    path = os.path.join(SNAP_DIR, f"{engine}.json")
    assert os.path.exists(path), f"missing snapshot {path} - run scripts/record-flag-surfaces.py"
    with open(path) as f:
        return json.load(f)


@pytest.mark.parametrize("template_type", sorted(TEMPLATE_TYPE_TO_ENGINE))
def test_metadata_cli_in_recorded_surface(template_type):
    """Every curated cli the panel can click into a container must exist in the
    engine's parser. A typo'd name and an upstream-removed name both land here."""
    engine = TEMPLATE_TYPE_TO_ENGINE[template_type]
    surface = set(load_surface(engine)["flags"])
    stale = STALE.get(engine, set())
    missing = sorted(
        meta["cli"]
        for meta in get_flag_metadata(template_type).values()
        if str(meta.get("cli", "")).startswith("-")
        and meta["cli"] not in surface
        and meta["cli"] not in stale
    )
    assert missing == [], (
        f"{template_type}: {missing} not in {engine}'s recorded surface - typo or "
        f"removed upstream; fix the entry (or, if the surface moved, regenerate with "
        f"scripts/record-flag-surfaces.py)"
    )


@pytest.mark.parametrize(
    "engine,cli",
    sorted((e, c) for e, s in STALE.items() for c in s),
)
def test_stale_entries_still_absent(engine, cli):
    """Pin the #207 findings as still-broken. If the flag comes back in the surface
    (pin moved, engine re-added it) this fails so the entry gets re-verified and
    the STALE list entry dropped - the list must never outlive its reason."""
    assert cli not in set(load_surface(engine)["flags"]), (
        f"{cli} is present in {engine}'s surface again: re-probe the engine, fix the "
        f"metadata entry if needed, and drop it from STALE"
    )


# Engines whose Dockerfile pins the build the snapshot was recorded from. When the
# pin moves, the checked-in surface is a lie unless regenerated - fail loudly rather
# than let it drift silently.
PIN_SOURCES = {
    "vllm": ("vllm/Dockerfile", "VLLM_BASE"),
    "ds4": ("ds4/Dockerfile", "DS4_COMMIT"),
    "ninfer": ("ninfer/Dockerfile", "NINFER_COMMIT"),
    "tabbyapi": ("tabbyapi/Dockerfile", "TABBYAPI_REF"),
}


@pytest.mark.parametrize("engine", sorted(PIN_SOURCES))
def test_recorded_pin_matches_dockerfile_pin(engine):
    rel, arg = PIN_SOURCES[engine]
    with open(os.path.join(REPO_ROOT, rel)) as f:
        m = re.search(rf"^ARG {arg}=(\S+)", f.read(), re.M)
    assert m, f"ARG {arg} not found in {rel}"
    recorded = load_surface(engine)["build_identity"]["pin"]
    assert recorded == m.group(1), (
        f"{rel} now pins {m.group(1)} but the {engine} snapshot was recorded from "
        f"{recorded}: rebuild the image and run "
        f"scripts/record-flag-surfaces.py --engine {engine}"
    )


def test_unpinned_llamacpp_image_id_still_current():
    """The llama.cpp image tracks upstream main, so there is no pin to diff: the
    recorded image_id is the staleness signal. Checked only when docker is usable
    AND the image is local - a fresh worktree without either falls back to the
    checked-in snapshot, which is the best available truth there."""
    if shutil.which("docker") is None:
        pytest.skip("docker not available; the checked-in snapshot is the authority")
    out = subprocess.run(
        ["docker", "images", "--format", "{{.ID}}", "llm-dock-llamacpp:latest"],
        capture_output=True, text=True,
    )
    local = out.stdout.strip()
    if not local:
        pytest.skip("llm-dock-llamacpp:latest not local; the checked-in snapshot is the authority")
    for engine in ("llamacpp_server", "llamacpp_bench"):
        recorded = load_surface(engine)["build_identity"]["image_id"]
        assert recorded == local, (
            f"local llm-dock-llamacpp:latest is {local} but the {engine} snapshot was "
            f"recorded from {recorded}: the image was rebuilt - run "
            f"scripts/record-flag-surfaces.py --engine {engine} (and llamacpp_bench)"
        )


def test_snapshots_are_well_formed():
    engines = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(SNAP_DIR, "*.json"))}
    assert engines == set(TEMPLATE_TYPE_TO_ENGINE.values()), engines
    for engine in engines:
        snap = load_surface(engine)
        assert snap["flags"] == sorted(set(snap["flags"])), f"{engine}: flags not sorted-unique"
        assert all(f.startswith("-") for f in snap["flags"]), f"{engine}: non-flag token in surface"
        assert snap["build_identity"]["image_id"], f"{engine}: no image identity"
        assert snap["source_command"].startswith("docker"), f"{engine}: source is not a docker command"
