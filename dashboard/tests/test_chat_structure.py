import re
from pathlib import Path

CHAT_DIR = Path(__file__).resolve().parent.parent / "chat"
ENDPOINT_MODULES = sorted(p for p in CHAT_DIR.glob("*_routes.py"))
MAX_ENDPOINT_LINES = 250


def _source(path: Path) -> str:
    return path.read_text()


def test_only_app_deps_touches_flask_current_app_in_chat():
    offenders = [p.name for p in CHAT_DIR.glob("*.py") if "current_app" in _source(p) and p.name != "app_deps.py"]

    assert offenders == []


def test_deps_py_has_no_flask_import():
    assert not re.search(r"^\s*(from|import)\s+flask", _source(CHAT_DIR / "deps.py"), re.M)


def test_no_endpoint_module_imports_from_routes():
    offenders = [
        p.name for p in ENDPOINT_MODULES if re.search(r"^\s*from\s+\.routes\s+import|from \. import .*\broutes\b", _source(p), re.M)
    ]

    assert offenders == []


def test_endpoint_modules_stay_small():
    assert [(p.name, len(_source(p).splitlines())) for p in ENDPOINT_MODULES if len(_source(p).splitlines()) > MAX_ENDPOINT_LINES] == []


def test_routes_py_is_only_a_registration_shim():
    shim = _source(CHAT_DIR / "routes.py")

    assert "@chat_bp.route" not in shim and "def " not in shim
    assert len(shim.splitlines()) < 40


def test_every_endpoint_module_is_registered_by_the_shim():
    shim = _source(CHAT_DIR / "routes.py")

    assert [p.stem for p in ENDPOINT_MODULES if p.stem not in shim] == []
