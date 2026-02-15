import logging
import subprocess
import yaml
import docker

from config import COMPOSE_FILE, COMPOSE_PROJECT
from compose_manager import ComposeManager
from openwebui_integration import get_openwebui_registered_urls

logger = logging.getLogger(__name__)


def check_nvidia_smi():
    """Check if nvidia-smi is available"""
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, check=True, timeout=5)
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False


def get_image_build_metadata(image_name: str) -> dict:
    """Get build metadata labels from a Docker image"""
    try:
        client = docker.from_env()
        image = client.images.get(image_name)
        labels = image.labels or {}

        return {
            "build_date": labels.get("org.llm-dock.build.date"),
            "build_commit": labels.get("org.llm-dock.build.commit"),
            "exists": True,
        }
    except docker.errors.ImageNotFound:
        return {"build_date": None, "build_commit": None, "exists": False}
    except Exception as e:
        logger.warning(f"Failed to get metadata for image {image_name}: {e}")
        return {
            "build_date": None,
            "build_commit": None,
            "exists": False,
            "error": str(e),
        }


def get_compose_services():
    """Load service names from docker-compose.yml"""
    try:
        with open(COMPOSE_FILE) as f:
            config = yaml.safe_load(f)
            return set(config.get("services", {}).keys())
    except Exception as e:
        logger.error(f"Failed to read compose file: {e}")
        return set()


def get_compose_service_ports():
    """Load service port mappings from docker-compose.yml"""
    try:
        with open(COMPOSE_FILE) as f:
            config = yaml.safe_load(f)
            services = config.get("services", {})

            port_map = {}
            for service_name, service_config in services.items():
                ports = service_config.get("ports", [])
                if ports:
                    # Parse "3300:8080" format to get host port
                    first_port = str(ports[0])
                    if ":" in first_port:
                        host_port = int(first_port.split(":")[0])
                        port_map[service_name] = host_port
                    else:
                        port_map[service_name] = int(first_port)
                else:
                    port_map[service_name] = 9999  # No port = sort to end

            return port_map
    except Exception as e:
        logger.error(f"Failed to read compose ports: {e}")
        return {}


def check_docker():
    """Check if Docker is available"""
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def get_docker_services():
    """Get status of compose services from Docker"""
    client = docker.from_env()
    allowed_services = get_compose_services()
    port_map = get_compose_service_ports()

    # Get API keys and template types from services.json
    compose_mgr = ComposeManager(COMPOSE_FILE)
    api_key_map = {}
    template_type_map = {}
    for service_name in allowed_services:
        config = compose_mgr.get_service_from_db(service_name)
        if config:
            api_key_map[service_name] = config.get("api_key", "")
            template_type_map[service_name] = config.get("template_type", "")

    # Get Open WebUI registered URLs (one query for all services)
    openwebui_urls = get_openwebui_registered_urls()

    def is_registered_in_openwebui(svc_name: str) -> bool:
        """Check if service URL is in the registered URLs list"""
        engine = template_type_map.get(svc_name, "")
        if not engine:
            return False
        internal_port = 8080 if engine == "llamacpp" else 8000
        expected_url = f"http://{svc_name}:{internal_port}/v1"
        return expected_url in openwebui_urls

    # Get existing containers
    containers = client.containers.list(
        all=True, filters={"label": f"com.docker.compose.project={COMPOSE_PROJECT}"}
    )

    # Create a map of service_name -> container info
    container_map = {}
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name in allowed_services:
            # Get exit code for crashed containers
            exit_code = container.attrs.get("State", {}).get("ExitCode", 0)
            container_map[service_name] = {
                "name": service_name,
                "status": container.status,
                "exit_code": exit_code if container.status == "exited" else None,
                "container_id": container.id[:12],
                "created": container.attrs["Created"],
                "ports": container.ports,
                "host_port": port_map.get(service_name, 9999),
                "api_key": api_key_map.get(service_name, ""),
                "openwebui_registered": is_registered_in_openwebui(service_name),
            }

    # Build complete services list from compose file
    services = []
    for service_name in allowed_services:
        if service_name in container_map:
            # Container exists
            services.append(container_map[service_name])
        else:
            # Service defined but no container yet
            services.append(
                {
                    "name": service_name,
                    "status": "not-created",
                    "container_id": None,
                    "created": None,
                    "ports": {},
                    "host_port": port_map.get(service_name, 9999),
                    "api_key": api_key_map.get(service_name, ""),
                    "openwebui_registered": is_registered_in_openwebui(service_name),
                }
            )

    # Sort by port number (ascending)
    services.sort(key=lambda s: s["host_port"])

    return services


def get_service_container(service_name):
    """Get container for a specific service"""
    client = docker.from_env()
    allowed_services = get_compose_services()

    if service_name not in allowed_services:
        return None

    containers = client.containers.list(
        all=True,
        filters={
            "label": [
                f"com.docker.compose.project={COMPOSE_PROJECT}",
                f"com.docker.compose.service={service_name}",
            ]
        },
    )

    return containers[0] if containers else None


def control_service(service_name, action):
    """Control a service (start/stop/restart)"""
    container = get_service_container(service_name)

    try:
        if action == "start":
            if container and container.status == "running":
                return {"success": False, "error": "Service is already running"}

            # Always use docker compose up -d to ensure container is recreated if config changed
            result = subprocess.run(
                ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", service_name],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                logger.error(f"Failed to start service {service_name}: {result.stderr}")
                return {
                    "success": False,
                    "error": f"Failed to start service: {result.stderr}",
                }

            message = (
                f"Service {service_name} created and started"
                if not container
                else f"Service {service_name} started"
            )
            return {"success": True, "message": message}

        elif action == "stop":
            if not container:
                return {"success": False, "error": "Service has not been created yet"}

            if container.status != "running":
                return {"success": False, "error": "Service is not running"}

            container.stop()
            return {"success": True, "message": f"Service {service_name} stopped"}

        elif action == "restart":
            if not container:
                return {
                    "success": False,
                    "error": "Service has not been created yet. Use Start instead.",
                }

            container.restart()
            return {"success": True, "message": f"Service {service_name} restarted"}

        else:
            return {"success": False, "error": "Invalid action"}

    except Exception as e:
        logger.error(f"Failed to {action} service {service_name}: {e}")
        return {"success": False, "error": str(e)}


def get_gpu_stats():
    """Get GPU statistics using nvidia-smi"""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free,temperature.gpu,"
                "utilization.gpu,utilization.memory,power.draw,power.limit,power.default_limit,"
                "power.min_limit,power.max_limit,enforced.power.limit,clocks.gr,clocks.mem,"
                "fan.speed,pstate",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )

        gpus = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 18:
                logger.warning(f"Incomplete nvidia-smi output: {line}")
                continue

            try:
                gpu_data = {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory": {
                        "total": int(parts[2]),
                        "used": int(parts[3]),
                        "free": int(parts[4]),
                        "unit": "MiB",
                        "utilization_percent": int(parts[7])
                        if parts[7] != "[N/A]"
                        else 0,
                    },
                    "temperature": {
                        "current": int(parts[5]) if parts[5] != "[N/A]" else 0,
                        "unit": "C",
                    },
                    "utilization": {
                        "gpu_percent": int(parts[6]) if parts[6] != "[N/A]" else 0,
                        "memory_percent": int(parts[7]) if parts[7] != "[N/A]" else 0,
                    },
                    "power": {
                        "draw": float(parts[8]) if parts[8] != "[N/A]" else 0.0,
                        "limit": {
                            "current": float(parts[9]) if parts[9] != "[N/A]" else 0.0,
                            "default": float(parts[10])
                            if parts[10] != "[N/A]"
                            else 0.0,
                            "min": float(parts[11]) if parts[11] != "[N/A]" else 0.0,
                            "max": float(parts[12]) if parts[12] != "[N/A]" else 0.0,
                            "enforced": float(parts[13])
                            if parts[13] != "[N/A]"
                            else 0.0,
                        },
                        "unit": "W",
                    },
                    "clocks": {
                        "graphics": int(parts[14]) if parts[14] != "[N/A]" else 0,
                        "memory": int(parts[15]) if parts[15] != "[N/A]" else 0,
                        "unit": "MHz",
                    },
                    "fan": {
                        "speed_percent": int(parts[16])
                        if parts[16] not in ["[N/A]", "[Not Supported]"]
                        else None
                    },
                    "performance_state": parts[17]
                    if parts[17] != "[N/A]"
                    else "Unknown",
                }
                gpus.append(gpu_data)
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing GPU data: {e}, line: {line}")
                continue

        return gpus

    except subprocess.CalledProcessError as e:
        logger.error(f"nvidia-smi command failed: {e}")
        raise
    except subprocess.TimeoutExpired:
        logger.error("nvidia-smi command timed out")
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting GPU stats: {e}")
        raise