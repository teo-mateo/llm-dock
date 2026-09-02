"""
Per-service auth key files for the TabbyAPI (ExLlamaV3) runner.

TabbyAPI authenticates against an `api_tokens.yml` in its working directory and,
unlike llama.cpp or vLLM, has no `--api-key` flag. If the file is missing it
generates its own keys and logs them, which silently diverges from the `api_key`
llm-dock keeps in services.json — chat and Open WebUI would then get 401s. So
the compose template bind-mounts this file at /app/api_tokens.yml.

Files are (re)written during compose rendering rather than at service-creation
time: every mutation that can change a name or a key (create, rename, default-key
rotation) rebuilds docker-compose.yml, so rendering is the one seam that covers
all of them.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).resolve().parent / "tabby_keys"


def keys_dir() -> Path:
    """Directory holding per-service key files (machine-local, gitignored)."""
    override = os.environ.get("LLM_DOCK_TABBY_KEYS_DIR")
    return Path(override) if override else _DEFAULT_DIR


def key_file_path(service_name: str) -> Path:
    return keys_dir() / f"{service_name}.yml"


def render_key_file(service_name: str, api_key: str) -> str:
    """
    Render the api_tokens.yml body for a service.

    The service's own key is used for both roles: llm-dock has no separate
    admin credential, and /v1/model/load-style calls are made by the dashboard
    operator only.
    """
    return yaml.safe_dump(
        {"api_key": api_key, "admin_key": api_key}, sort_keys=False
    )


def ensure(service_name: str, api_key: str) -> Path:
    """
    Write the service's key file unless it already holds this key.

    Idempotent on purpose — compose rebuilds happen on every service mutation.
    Returns the path written (or already present).
    """
    path = key_file_path(service_name)
    body = render_key_file(service_name, api_key)

    if path.is_file():
        try:
            if path.read_text() == body:
                return path
        except OSError:
            pass  # unreadable → rewrite it

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".yml")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        os.chmod(tmp, 0o600)  # keys are secrets; TabbyAPI reads it as root
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    logger.info(f"Wrote TabbyAPI key file for service '{service_name}'")
    return path


def remove(service_name: str) -> Optional[Path]:
    """Delete a service's key file. Returns the path removed, if any."""
    path = key_file_path(service_name)
    try:
        path.unlink()
        logger.info(f"Removed TabbyAPI key file for service '{service_name}'")
        return path
    except FileNotFoundError:
        return None
