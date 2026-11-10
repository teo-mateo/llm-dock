import ast
import subprocess
import sys
from pathlib import Path

SERVICE_OPS = Path(__file__).resolve().parent.parent / "service_ops"
ROOT = SERVICE_OPS.parent


def test_importing_service_ops_pulls_in_neither_flask_nor_routes():
    code = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "import service_ops, service_ops.hooks, service_ops.deps, service_ops.subsystems\n"
        "bad = [m for m in sys.modules if m == 'flask' or m.startswith('flask.') or m == 'routes' or m.startswith('routes.')]\n"
        "assert not bad, bad\n"
    )

    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_no_service_ops_module_imports_flask_or_routes_itself():
    offenders = []
    for path in sorted(SERVICE_OPS.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            offenders += [
                f"{path.name}: {name}" for name in names if name.split(".")[0] in {"flask", "routes"}
            ]

    assert offenders == []


def test_only_the_wiring_module_imports_the_real_singletons():
    singletons = {"docker_utils", "openwebui_integration", "inspector", "tabby_keys", "compose_manager"}
    offenders = []
    for path in sorted(SERVICE_OPS.glob("*.py")):
        if path.name == "wiring.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] in singletons]

    assert offenders == []


def test_the_shared_deps_module_holds_only_infra_and_the_protocols():
    tree = ast.parse((SERVICE_OPS / "deps.py").read_text())

    assert [node.name for node in tree.body if isinstance(node, ast.ClassDef)] == [
        "Container", "ComposeStore", "Infra",
    ]
    assert not (SERVICE_OPS / "outcomes.py").exists()


def test_every_error_kind_has_an_http_status_in_the_route():
    sys.path.insert(0, str(ROOT))
    import routes.services as services_route
    from service_ops.errors import ErrorKind

    assert set(services_route._OP_ERROR_STATUS) == set(ErrorKind)
    assert services_route._OP_ERROR_STATUS == {
        ErrorKind.NOT_FOUND: 404, ErrorKind.CONFLICT: 409, ErrorKind.INVALID: 400,
    }
