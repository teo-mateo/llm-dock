import re
from pathlib import Path

from flag_metadata import ENGINE_IMAGES, FLAG_METADATA_BY_TYPE, SERVICE_NAME_PREFIXES

SPA_SOURCES = Path(__file__).resolve().parent.parent / "frontend" / "src"

# Per-engine RENDERING behaviour, not engine lists: the engine list comes from
# GET /api/engines. A new engine needs no entry here unless it needs bespoke
# rendering in one of these files.
ALLOWED = {
    "components/commandPreview.js": "bespoke launch-command shapes; an engine without a branch gets the generic model-path-plus-params preview",
    "hooks/useServiceMetrics.js": "per-engine metric-name normalisation (RENAMES); a new metrics engine needs a RENAMES entry or its raw fields render as-is",
    "components/MetricsPanel.jsx": "the SGLang-only details panel",
    "components/EngineBadge.jsx": "engine badge colour tokens (theme: Tailwind needs literal class names); an unknown engine gets a neutral badge labelled from the catalogue or its type",
}

ENGINE_NAMES = sorted(set(ENGINE_IMAGES) | set(FLAG_METADATA_BY_TYPE))
NAMES = "|".join(map(re.escape, ENGINE_NAMES))
PREFIXES = "|".join(map(re.escape, sorted({SERVICE_NAME_PREFIXES.get(name, name) for name in ENGINE_IMAGES})))
# A quoted whole token ('vllm'), an unquoted object key ({ vllm: ... }), or a
# quoted service-name prefix ('vllm-', startsWith('ik-')).
LITERAL = re.compile(
    r"""(['"`])(%s)\1|(?<![\w'"`.\-:])(%s)\s*:(?!:)|(['"`])((?:%s)-)\4""" % (NAMES, NAMES, PREFIXES)
)


def _spa_files():
    for path in sorted(SPA_SOURCES.rglob("*")):
        if path.suffix in {".js", ".jsx"} and ".test." not in path.name and "test" not in path.parts:
            yield path


def _literals(path: Path):
    for number, line in enumerate(path.read_text().splitlines(), 1):
        for match in LITERAL.finditer(line):
            yield number, match.group(2) or match.group(3) or match.group(5)


def test_the_spa_holds_no_engine_name_outside_the_named_exceptions():
    offenders = [
        f"{path.relative_to(SPA_SOURCES)}:{number}: {name}"
        for path in _spa_files()
        if str(path.relative_to(SPA_SOURCES)) not in ALLOWED
        for number, name in _literals(path)
    ]

    assert offenders == [], "engine lists belong in GET /api/engines:\n" + "\n".join(offenders)


def test_every_allowed_file_still_needs_its_exception():
    stale = [
        name for name in ALLOWED
        if not list(_literals(SPA_SOURCES / name))
    ]

    assert stale == [], f"remove from ALLOWED, they no longer name an engine: {stale}"


def test_the_detector_finds_the_spellings_the_spa_uses(tmp_path):
    sample = tmp_path / "a.js"
    sample.write_text(
        "const a = 'vllm'\nconst b = \"maya\"\nconst c = `ds4`\nconst d = 'vllm-x'\n"
        "const e = { sglang: 1, maya : 2 }\nconst f = 'vllm:num_requests'\nconst g = x ? vllm : y\n"
        "if (n.startsWith('ik-')) {}\nconst h = name.startsWith(\"exl3-\")\nconst i = 'open-webui'\nconst j = 'pi-session'\n"
    )

    assert [name for _, name in _literals(sample)] == [
        "vllm", "maya", "ds4", "sglang", "maya", "vllm", "ik-", "exl3-",
    ]
