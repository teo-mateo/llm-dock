"""Configure Flash-Next before Pennyroyal derives its persistent-cache identity."""

from pathlib import Path
import re


def patch_recipe(source):
    def replace(pattern, replacement, count=1):
        nonlocal source
        source, found = re.subn(pattern, lambda match: replacement, source, flags=re.MULTILINE)
        if found != count:
            raise ValueError(f"Pennyroyal recipe changed: {pattern!r} matched {found}, expected {count}")

    replace(r"^CONTEXT_LENGTH=524288$",
            'CONTEXT_LENGTH="${PENNY_CONTEXT_LENGTH:-524288}"', 1)
    replace(r"^PREFILL_CHUNK_SIZE=4096$",
            'PREFILL_CHUNK_SIZE="${PENNY_PREFILL_CHUNK_SIZE:-4096}"', 1)
    replace(r"--quantization modelopt_fp4", '--quantization "$LLM_DOCK_TARGET_QUANTIZATION"')
    replace(r"--mem-fraction-static 0\.981",
            '--mem-fraction-static "${PENNY_MEM_FRACTION_STATIC:-0.981}"')
    # These knobs may be absent from a given upstream build, so absence is
    # tolerated: plain str.replace no-ops here, unlike the raising replace().
    source = source.replace('--max-running-requests 4',
                            '--max-running-requests "${MAX_RUNNING_REQUESTS:-4}"')
    source = source.replace('--max-mamba-cache-size 24',
                            '--max-mamba-cache-size "${MAX_MAMBA_CACHE_SIZE:-24}"')
    source = source.replace('max_mamba_cache_size=24',
                            'max_mamba_cache_size=${MAX_MAMBA_CACHE_SIZE:-24}')
    source = source.replace('--hicache-size 32',
                            '--hicache-size "${PENNY_HICACHE_SIZE_GB:-32}"')
    # Patch inside the namespace field list itself so the values exist before
    # cache-identity derivation (see launcher.py), not overridden in argv later.
    replace(r'  --field "cuda_arch=12\.0"',
            '  --field "target_quantization=$LLM_DOCK_TARGET_QUANTIZATION" \\\n'
            '  --field "llm_dock_max_running_requests=${MAX_RUNNING_REQUESTS:-4}" \\\n'
            '  --field "cuda_arch=12.0"')
    return source


if __name__ == "__main__":
    for name in ("serve-flash-next.sh", "serve-flash-next-frspec.sh"):
        path = Path("/opt/pennyroyal/configs/pennyroyal") / name
        # Keep tracked upstream source clean for pennyroyal --check and its
        # git revision identity. Copies stay beside shared shell helpers.
        path.with_name("llm-dock-" + name).write_text(patch_recipe(path.read_text()))
