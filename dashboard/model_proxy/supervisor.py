import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, Optional

import config

from .proxy import PortProxy

logger = logging.getLogger(__name__)

DEFAULT_LISTEN_PORT = 3388
DEFAULT_LISTEN_BIND = "0.0.0.0"


class ModelProxySupervisor:
    def __init__(self) -> None:
        self._services_path: Optional[str] = None
        self._proxy: Optional[PortProxy] = None
        self._lock = threading.RLock()
        self._cache: Optional[tuple] = None

    def configure(self, services_path: Optional[str] = None) -> None:
        with self._lock:
            self._services_path = services_path
            self._cache = None

    def _services_path_resolved(self) -> str:
        with self._lock:
            if self._services_path is not None:
                return self._services_path
        return str(Path(config.COMPOSE_FILE).parent / "services.json")

    def allowed_ports(self) -> Dict[int, str]:
        path = self._services_path_resolved()
        try:
            stat = os.stat(path)
        except OSError:
            return {}
        key = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if self._cache is not None and self._cache[0] == key:
                return self._cache[1]
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        ports: Dict[int, str] = {}
        if isinstance(data, dict):
            for name, cfg in data.items():
                port = cfg.get("port") if isinstance(cfg, dict) else None
                if isinstance(port, int) and 1 <= port <= 65535:
                    ports[port] = str(cfg.get("alias") or name)
        with self._lock:
            self._cache = (key, ports)
        return ports

    def start(self) -> None:
        with self._lock:
            if self._proxy is not None and self._proxy.running:
                return
            listen_port = int(
                os.environ.get("LLM_DOCK_MODEL_PROXY_PORT", DEFAULT_LISTEN_PORT)
            )
            listen_bind = os.environ.get(
                "LLM_DOCK_MODEL_PROXY_BIND", DEFAULT_LISTEN_BIND
            )
            owner = self.allowed_ports().get(listen_port)
            if owner is not None:
                logger.warning(
                    "Model proxy port %d collides with service '%s'; start it on a "
                    "different port to use the model proxy",
                    listen_port, owner,
                )
            proxy = PortProxy(self.allowed_ports, listen_host=listen_bind,
                              listen_port=listen_port)
            proxy.start()
            if proxy.running:
                logger.info("Model proxy listening on %s:%d", listen_bind, proxy.listen_port)
            self._proxy = proxy

    def stop_all(self) -> None:
        with self._lock:
            proxy, self._proxy = self._proxy, None
        if proxy is not None:
            proxy.stop()

    def status(self) -> Dict[str, object]:
        with self._lock:
            proxy = self._proxy
        if proxy is None:
            return {"running": False, "listen_port": None, "bind_error": None}
        return {
            "running": proxy.running,
            "listen_port": proxy.listen_port,
            "bind_error": proxy.bind_error,
        }

    def sync(self) -> None:
        self.start()


model_proxy_supervisor = ModelProxySupervisor()
