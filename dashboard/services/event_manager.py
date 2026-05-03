"""Docker Event Manager - Background thread for consuming and dispatching Docker events."""

import threading
import logging
import time
from typing import Callable

import docker

from services.docker_events import DockerEventConsumer

logger = logging.getLogger(__name__)


class DockerEventManager:
    """Background thread manager for Docker events.

    Wraps DockerEventConsumer in a daemon thread with automatic reconnect.
    Registered callbacks are invoked for every parsed event.
    """

    def __init__(self, docker_client=None, project_name: str | None = None):
        """Initialize the manager.

        Args:
            docker_client: A docker.DockerClient instance. If None, creates one via docker.from_env().
            project_name: Docker Compose project name to filter events by.
        """
        self._docker_client = docker_client
        self._project_name = project_name
        self._callbacks: list[Callable[[dict], None]] = []
        self._callbacks_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register_callback(self, callback: Callable[[dict], None]):
        """Register a callback to receive parsed event dicts.

        Callbacks are called synchronously in the event thread, so they
        should return quickly. Registering a callback multiple times is
        allowed — it will be called each time.

        Args:
            callback: Callable that takes a single dict argument.
        """
        with self._callbacks_lock:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[dict], None]):
        """Unregister a previously registered callback.

        Args:
            callback: The callable to remove.
        """
        with self._callbacks_lock:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                logger.debug("Callback not registered, skipping")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        """Start the background event thread.

        Calling start() while already running is a no-op.
        """
        if self.is_running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("DockerEventManager started")

    def stop(self):
        """Stop the background event thread.

        Blocks until the thread exits (up to 5 seconds).
        """
        if not self.is_running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("DockerEventManager stopped")

    def _create_consumer(self) -> DockerEventConsumer:
        consumer_client = self._docker_client or docker.from_env()
        return DockerEventConsumer(docker_client=consumer_client, project_name=self._project_name)

    def _run(self):
        """Main loop: consume events, dispatch to callbacks, reconnect on failure."""
        while not self._stop_event.is_set():
            consumer = self._create_consumer()

            try:
                for event in consumer.list_events():
                    if self._stop_event.is_set():
                        return
                    self._dispatch(event)
            except Exception as e:
                if self._stop_event.is_set():
                    return
                logger.warning("Docker events stream died, reconnecting: %s", e)

                # Reconnect: recreate the docker client so we get a fresh connection
                self._docker_client = None
                logger.info("Reconnecting Docker client for event stream")
                time.sleep(1)

    def _dispatch(self, event: dict):
        """Invoke all registered callbacks with the event dict.

        Uses a snapshot of the callback list to avoid concurrency issues.
        Silently catches exceptions from individual callbacks so one
        bad callback doesn't break the dispatch loop.
        """
        with self._callbacks_lock:
            callbacks = list(self._callbacks)

        for cb in callbacks:
            try:
                cb(event)
            except Exception as e:
                cb_name = getattr(cb, "__qualname__", getattr(cb, "__name__", str(cb)))
                logger.error("Callback error in %s: %s", cb_name, e)

    def get_services_snapshot(self) -> list[dict]:
        """Return the current state of all services from Docker.

        Wraps docker_utils.get_docker_services() for use by the SSE endpoint
        to send an initial snapshot to new clients.
        """
        from docker_utils import get_docker_services
        return get_docker_services()
