"""Services package: Docker event management and SSE streaming."""

from config import COMPOSE_PROJECT
from services.event_manager import DockerEventManager

# Module-level singleton for Docker event management
event_manager = DockerEventManager(project_name=COMPOSE_PROJECT)
