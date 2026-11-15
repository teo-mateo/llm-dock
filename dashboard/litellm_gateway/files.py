import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chat import providers as chat_providers

from .routes import ProviderCreds, ProviderLookup, check_and_resolve, render_config, render_env

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "litellm"


def routes_dir() -> Path:
    override = os.environ.get("LLM_DOCK_LITELLM_DIR")
    return Path(override) if override else _DEFAULT_DIR


def service_dir(service_name: str) -> Path:
    return routes_dir() / service_name


def provider_lookup(provider_id: str) -> Optional[ProviderCreds]:
    entry = chat_providers.get_provider(provider_id)
    if entry is None:
        return None
    return ProviderCreds(entry.get("base_url"), chat_providers.api_key(entry) or "")


def route_warnings(config: Dict[str, Any], services_db: Dict[str, Any]) -> List[str]:
    return check_and_resolve(config.get("routes"), services_db, provider_lookup)[1]


def _atomic_write(path: Path, body: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ensure(
    service_name: str,
    config: Dict[str, Any],
    services_db: Dict[str, Any],
    lookup: ProviderLookup = provider_lookup,
) -> Tuple[Path, Path, List[str]]:
    resolved, warnings = check_and_resolve(config.get("routes"), services_db, lookup)
    directory = service_dir(service_name)
    _atomic_write(directory / "config.yaml", render_config(resolved), 0o644)
    # gateway.env holds the master key and every upstream key.
    _atomic_write(directory / "gateway.env", render_env(config["api_key"], resolved), 0o600)
    logger.info(
        f"Wrote LiteLLM gateway config for '{service_name}' "
        f"({len(resolved)} routes, {len(warnings)} skipped)"
    )
    return directory / "config.yaml", directory / "gateway.env", warnings


def compose_context(service_name: str, config: Dict[str, Any], services_db: Dict[str, Any]) -> Dict[str, Any]:
    gateway_config, gateway_env, warnings = ensure(service_name, config, services_db)
    for warning in warnings:
        logger.warning(f"litellm '{service_name}': {warning}")
    return {
        "alias": config["alias"],
        "api_key": config["api_key"],
        "gateway_config": str(gateway_config),
        "gateway_env": str(gateway_env),
    }


def remove(service_name: str) -> Optional[Path]:
    directory = service_dir(service_name)
    if not directory.is_dir():
        return None
    shutil.rmtree(directory)
    logger.info(f"Removed LiteLLM gateway config for '{service_name}'")
    return directory
