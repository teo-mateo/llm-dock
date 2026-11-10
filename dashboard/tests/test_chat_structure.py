import ast
import importlib
import sys
from pathlib import Path

import pytest

CHAT_DIR = Path(__file__).resolve().parent.parent / "chat"
MAX_ENDPOINT_LINES = 250
SHIM = "routes.py"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text())


def _imported_modules(tree: ast.AST) -> list[tuple[str, list[str]]]:
    """(resolved module, imported names) for every import in a chat/ module."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, []) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                module = "chat" + (f".{node.module}" if node.module else "")
            else:
                module = node.module or ""
            found.append((module, [alias.name for alias in node.names]))
    return found


def _imports_routes(source: str) -> bool:
    for module, names in _imported_modules(ast.parse(source)):
        if module == "chat.routes" or module.startswith("chat.routes."):
            return True
        if module == "chat" and "routes" in names:
            return True
    return False


def _registers_routes(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                call = decorator.func if isinstance(decorator, ast.Call) else decorator
                if (
                    isinstance(call, ast.Attribute)
                    and call.attr == "route"
                    and isinstance(call.value, ast.Name)
                    and call.value.id == "chat_bp"
                ):
                    return True
    return False


ENDPOINT_MODULES = sorted(
    path for path in CHAT_DIR.glob("*.py") if path.name != SHIM and _registers_routes(_tree(path))
)


@pytest.mark.parametrize(
    "source,expected",
    [
        ("from chat.routes import chat_bp", True),
        ("from .routes import chat_bp", True),
        ("from . import routes", True),
        ("from . import (\n    alpha,\n    routes,\n)", True),
        ("from chat import routes", True),
        ("import chat.routes", True),
        ("import chat.routes as r", True),
        ("from . import project_routes", False),
        ("from .blueprint import chat_bp", False),
        ("from chat.project_routes import x", False),
        ("import chat.blueprint", False),
    ],
)
def test_the_routes_import_detector_catches_every_spelling(source, expected):
    assert _imports_routes(source) is expected


def test_the_detector_finds_the_endpoint_modules_by_their_route_decorators(tmp_path):
    decorated = ast.parse('@chat_bp.route("/x")\ndef f():\n    pass\n')
    plain = ast.parse("def f():\n    pass\n")
    other_blueprint = ast.parse('@other_bp.route("/x")\ndef f():\n    pass\n')

    assert _registers_routes(decorated)
    assert not _registers_routes(plain)
    assert not _registers_routes(other_blueprint)


def test_the_endpoint_modules_are_found_by_behaviour_not_by_name():
    names = {path.stem for path in ENDPOINT_MODULES}

    assert {"conversation_routes", "message_routes", "ephemeral_routes", "mcp_admin_routes"} <= names
    assert "routes" not in names and "blueprint" not in names


def test_no_chat_module_imports_routes_except_through_the_shim():
    offenders = [
        path.name
        for path in CHAT_DIR.glob("*.py")
        if path.name != SHIM and _imports_routes(path.read_text())
    ]

    assert offenders == []


def test_endpoint_modules_stay_small():
    sizes = {path.name: len(path.read_text().splitlines()) for path in ENDPOINT_MODULES}

    assert {name: size for name, size in sizes.items() if size > MAX_ENDPOINT_LINES} == {}


def _is_chat_module(name: str) -> bool:
    return name == "chat" or name.startswith("chat.")


def test_importing_the_shim_registers_every_endpoint_module():
    saved = {name: module for name, module in sys.modules.items() if _is_chat_module(name)}
    for name in saved:
        del sys.modules[name]
    try:
        importlib.import_module("chat.routes")
        missing = [path.stem for path in ENDPOINT_MODULES if f"chat.{path.stem}" not in sys.modules]
    finally:
        for name in [n for n in sys.modules if _is_chat_module(n)]:
            del sys.modules[name]
        sys.modules.update(saved)

    assert missing == []


def test_routes_py_is_only_a_registration_shim():
    path = CHAT_DIR / SHIM
    tree = _tree(path)

    assert not _registers_routes(tree)
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    assert len(path.read_text().splitlines()) < 40


def test_only_app_deps_touches_flask_current_app_in_chat():
    offenders = [
        path.name
        for path in CHAT_DIR.glob("*.py")
        if "current_app" in path.read_text() and path.name != "app_deps.py"
    ]

    assert offenders == []


def test_deps_py_has_no_flask_import():
    modules = [module for module, _ in _imported_modules(_tree(CHAT_DIR / "deps.py"))]

    assert not [m for m in modules if m == "flask" or m.startswith("flask.")]
