import os

import logging
from typing import Iterator

import docker

logger = logging.getLogger(__name__)


ACTION_TO_STATUS = {
    "start": "running",
    "die": "exited",
    "stop": "exited",
    "kill": "exited",
    "restart": "running",
    "remove": "removed",
    "destroy": "removed",
}

LIFECYCLE_ACTIONS = {"create", "start", "stop", "die", "restart", "pause", "unpause"}


class DockerEventConsumer:
    """Consumes Docker engine events and yields parsed service status changes.

    Maps raw Docker events (start, die, stop, kill, remove, destroy) to
    structured dicts containing the service name (from services.json),
    new status, docker action, and event metadata.
    """

    def __init__(self, docker_client=None, project_name: str | None = None):
        """Initialize with a docker client and optional project name filter.

        Args:
            docker_client: A docker.DockerClient instance. If None, creates one via docker.from_env().
            project_name: Docker Compose project name to filter events by.
                         Defaults to COMPOSE_PROJECT_NAME env var.
        """
        self._client = docker_client or docker.from_env()
        self._project_name = project_name or os.environ.get("COMPOSE_PROJECT_NAME", "llm-dock")

    def _map_docker_action_to_status(self, action: str) -> str:
        """Map a Docker event action to our internal status string.

        Args:
            action: The Docker event 'Action' field (e.g. 'start', 'die', 'stop', 'kill', 'remove', 'destroy')

        Returns:
            Internal status string: one of 'running', 'exited', 'removed', 'unknown'
        """
        return ACTION_TO_STATUS.get(action, "unknown")

    def _extract_service_name(self, event: dict) -> str | None:
        """Extract the service name from a Docker event dict.

        Looks at the container's labels to find the compose service name.
        Returns None if the container doesn't belong to our project.
        """
        if event.get("Type") != "container":
            return None

        attributes = event.get("Actor", {}).get("Attributes", {})
        project = attributes.get("com.docker.compose.project", "")

        if project != self._project_name:
            return None

        return attributes.get("com.docker.compose.service") or None

    def _parse_event(self, raw_event: dict) -> dict | None:
        """Parse a raw Docker event dict into a structured event.

        Args:
            raw_event: A decoded Docker event dict as returned by client.events(decode=True).

        Returns:
            A dict like:
            {
                "service_name": str,
                "status": str,
                "action": str,
                "container_id": str,
                "timestamp": int,
            }
            Returns None if the event is not relevant to our project services.
        """
        service_name = self._extract_service_name(raw_event)
        if service_name is None:
            return None

        action = raw_event.get("Action", "")
        if action not in LIFECYCLE_ACTIONS:
            return None

        status = self._map_docker_action_to_status(action)

        return {
            "service_name": service_name,
            "status": status,
            "action": action,
            "container_id": raw_event.get("id", "")[:12] if raw_event.get("id") else "",
            "timestamp": raw_event.get("time", 0),
        }

    def list_events(
        self, since: str | None = None, until: str | None = None
    ) -> Iterator[dict]:
        """Iterate over Docker events, yielding only relevant parsed events.

        A blocking generator that consumes client.events() and yields structured
        dicts for events matching our project services.

        Args:
            since: Only return events after this timestamp (ISO 8601 format).
            until: Stop returning events after this timestamp.

        Yields:
            Parsed event dicts from _parse_event(). Skips None results.
        """
        filters = {
            "type": ["container"],
            "label": [f"com.docker.compose.project={self._project_name}"],
        }

        try:
            for raw_event in self._client.events(
                since=since,
                until=until,
                filters=filters,
                decode=True,
            ):
                parsed = self._parse_event(raw_event)
                if parsed is not None:
                    yield parsed
        except GeneratorExit:
            return
