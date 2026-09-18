import logging
import os
import threading
from typing import Dict, List, Optional

import config
from compose_manager import ComposeManager

from .db import InspectorDB
from .proxy import ServiceProxy

logger = logging.getLogger(__name__)


class ProxySupervisor:
    """Keeps one ServiceProxy per inspected service in step with services.json.

    sync() is the only reconciler — boot, the toggle endpoint and every other
    services.json write path call it after their mutation, and it never raises
    from a partially configured service.
    """

    def __init__(self, compose_path: Optional[str] = None, db_path: Optional[str] = None):
        self.compose_path = compose_path
        self.db_path = db_path
        self._proxies: Dict[str, ServiceProxy] = {}
        self._lock = threading.RLock()
        self._db: Optional[InspectorDB] = None

    def configure(self, compose_path: Optional[str] = None, db_path: Optional[str] = None) -> None:
        # A new db_path invalidates the open connection: holding the old
        # instance would keep writing into a stale (or deleted) file.
        with self._lock:
            if db_path is not None and db_path != self.db_path:
                self._db = None
            self.compose_path = compose_path
            self.db_path = db_path

    def _compose_path_resolved(self) -> str:
        return self.compose_path or config.COMPOSE_FILE

    def _db_path_resolved(self) -> str:
        return self.db_path or os.environ.get("LLM_DOCK_INSPECTOR_DB") or "inspector.db"

    def _ensure_db(self) -> InspectorDB:
        if self._db is None:
            self._db = InspectorDB(self._db_path_resolved())
        return self._db

    def sync(self) -> None:
        with self._lock:
            try:
                compose_mgr = ComposeManager(self._compose_path_resolved())
                services = compose_mgr.list_services_in_db()
            except FileNotFoundError:
                logger.debug("Inspector sync: compose file not found; nothing to reconcile")
                return

            desired: Dict[str, dict] = {}
            for name, cfg in services.items():
                if not cfg.get("inspect"):
                    continue
                port = cfg.get("port")
                upstream = cfg.get("inspect_upstream_port")
                if not port or not upstream:
                    logger.warning(
                        "Inspector: service '%s' has inspect enabled but no "
                        "port/inspect_upstream_port; its proxy is not started",
                        name,
                    )
                    continue
                desired[name] = {
                    "listen_port": int(port),
                    "upstream_port": int(upstream),
                    "template_type": cfg.get("template_type", ""),
                    "default_model": cfg.get("alias") or name,
                }

            # Release bindings before claiming new ones: on a port swap (the
            # set-public-port path) one service's new port is another
            # service's still-held port, and a bind-before-release would fail
            # with EADDRINUSE.
            for name in [n for n in self._proxies if n not in desired]:
                self._stop(name)
            for name, spec in desired.items():
                proxy = self._proxies.get(name)
                stale = proxy is None or not proxy.running or (
                    proxy.listen_port != spec["listen_port"]
                    or proxy.upstream_port != spec["upstream_port"]
                )
                if stale and proxy is not None:
                    self._stop(name)
            if not desired:
                return

            self._ensure_db()
            for name, spec in desired.items():
                if name not in self._proxies:
                    self._start(name, spec)

    def _start(self, name: str, spec: dict) -> ServiceProxy:
        proxy = ServiceProxy(
            name,
            listen_port=spec["listen_port"],
            upstream_port=spec["upstream_port"],
            db=self._db,
            template_type=spec["template_type"],
            default_model=spec["default_model"],
        )
        proxy.start()
        self._proxies[name] = proxy
        if proxy.running:
            logger.info(
                "Inspector proxy for '%s' listening on %d -> %d",
                name, spec["listen_port"], spec["upstream_port"],
            )
        else:
            logger.warning(
                "Inspector proxy for '%s' could not bind %d: %s",
                name, spec["listen_port"], proxy.bind_error,
            )
        return proxy

    def _stop(self, name: str) -> None:
        proxy = self._proxies.pop(name, None)
        if proxy is not None:
            proxy.stop()
            logger.info("Inspector proxy for '%s' stopped", name)

    def stop_all(self) -> None:
        with self._lock:
            for name in list(self._proxies):
                self._stop(name)

    def status(self) -> List[dict]:
        with self._lock:
            return [
                {
                    "service": name,
                    "listen_port": proxy.listen_port,
                    "upstream_port": proxy.upstream_port,
                    "running": proxy.running,
                    "error": proxy.bind_error,
                }
                for name, proxy in sorted(self._proxies.items())
            ]

    def rename_service(self, old_name: str, new_name: str) -> int:
        with self._lock:
            if self._db is None:
                return 0
            return self._db.rename_service(old_name, new_name)


proxy_supervisor = ProxySupervisor()
