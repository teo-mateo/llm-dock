#!/usr/bin/env python3
import os
import logging
import json
import secrets
import subprocess
import yaml
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import docker
from model_discovery import discover_huggingface_models, discover_all_models, get_disk_usage
from service_templates import (
    get_llamacpp_template,
    get_vllm_template,
    generate_service_name,
    validate_model_compatibility,
    generate_api_key
)
from compose_manager import ComposeManager
from flag_metadata import (
    generate_service_name as gen_service_name,
    validate_service_config,
    get_flag_metadata,
    MANDATORY_FIELDS
)
from openwebui_integration import (
    add_service_to_openwebui,
    remove_service_from_openwebui,
    is_service_registered_in_openwebui,
    get_openwebui_registered_urls
)

load_dotenv()

app = Flask(__name__)
CORS(app)

DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', 3305))
DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '127.0.0.1')
DASHBOARD_TOKEN = os.getenv('DASHBOARD_TOKEN')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
COMPOSE_FILE = os.getenv('COMPOSE_FILE', '../docker-compose.yml')
COMPOSE_PROJECT = os.getenv('COMPOSE_PROJECT_NAME', 'dockerized-models')

if not DASHBOARD_TOKEN:
    raise ValueError("DASHBOARD_TOKEN environment variable is required")

# Configure logging with file and console handlers
log_level = getattr(logging, LOG_LEVEL)
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler
file_handler = logging.FileHandler('dashboard.log')
file_handler.setLevel(log_level)
file_handler.setFormatter(log_format)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(log_format)

# Root logger configuration
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Application logger
logger = logging.getLogger(__name__)
logger.setLevel(log_level)


def require_auth(f):
    """Decorator to require authentication for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            logger.warning(f"Missing Authorization header from {request.remote_addr}")
            return jsonify({
                'error': {
                    'code': 'MISSING_TOKEN',
                    'message': 'Authorization header is required'
                },
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }), 401

        if not auth_header.startswith('Bearer '):
            logger.warning(f"Invalid Authorization header format from {request.remote_addr}")
            return jsonify({
                'error': {
                    'code': 'INVALID_FORMAT',
                    'message': 'Authorization header must be: Bearer <token>'
                },
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }), 401

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(token, DASHBOARD_TOKEN):
            logger.warning(f"Invalid token attempt from {request.remote_addr}")
            return jsonify({
                'error': {
                    'code': 'INVALID_TOKEN',
                    'message': 'Authentication token is invalid'
                },
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }), 401

        logger.debug(f"Authenticated request to {request.path} from {request.remote_addr}")
        return f(*args, **kwargs)

    return decorated_function


def check_nvidia_smi():
    """Check if nvidia-smi is available"""
    try:
        subprocess.run(['nvidia-smi'], capture_output=True, check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_compose_services():
    """Load service names from docker-compose.yml"""
    try:
        with open(COMPOSE_FILE) as f:
            config = yaml.safe_load(f)
            return set(config.get('services', {}).keys())
    except Exception as e:
        logger.error(f"Failed to read compose file: {e}")
        return set()


def get_compose_service_ports():
    """Load service port mappings from docker-compose.yml"""
    try:
        with open(COMPOSE_FILE) as f:
            config = yaml.safe_load(f)
            services = config.get('services', {})

            port_map = {}
            for service_name, service_config in services.items():
                ports = service_config.get('ports', [])
                if ports:
                    # Parse "3300:8080" format to get host port
                    first_port = str(ports[0])
                    if ':' in first_port:
                        host_port = int(first_port.split(':')[0])
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
            api_key_map[service_name] = config.get('api_key', '')
            template_type_map[service_name] = config.get('template_type', '')

    # Get Open WebUI registered URLs (one query for all services)
    openwebui_urls = get_openwebui_registered_urls()

    def is_registered_in_openwebui(svc_name: str) -> bool:
        """Check if service URL is in the registered URLs list"""
        engine = template_type_map.get(svc_name, '')
        if not engine:
            return False
        internal_port = 8080 if engine == "llamacpp" else 8000
        expected_url = f"http://{svc_name}:{internal_port}/v1"
        return expected_url in openwebui_urls

    # Get existing containers
    containers = client.containers.list(
        all=True,
        filters={'label': f'com.docker.compose.project={COMPOSE_PROJECT}'}
    )

    # Create a map of service_name -> container info
    container_map = {}
    for container in containers:
        service_name = container.labels.get('com.docker.compose.service')
        if service_name in allowed_services:
            # Get exit code for crashed containers
            exit_code = container.attrs.get('State', {}).get('ExitCode', 0)
            container_map[service_name] = {
                'name': service_name,
                'status': container.status,
                'exit_code': exit_code if container.status == 'exited' else None,
                'container_id': container.id[:12],
                'created': container.attrs['Created'],
                'ports': container.ports,
                'host_port': port_map.get(service_name, 9999),
                'api_key': api_key_map.get(service_name, ''),
                'openwebui_registered': is_registered_in_openwebui(service_name)
            }

    # Build complete services list from compose file
    services = []
    for service_name in allowed_services:
        if service_name in container_map:
            # Container exists
            services.append(container_map[service_name])
        else:
            # Service defined but no container yet
            services.append({
                'name': service_name,
                'status': 'not-created',
                'container_id': None,
                'created': None,
                'ports': {},
                'host_port': port_map.get(service_name, 9999),
                'api_key': api_key_map.get(service_name, ''),
                'openwebui_registered': is_registered_in_openwebui(service_name)
            })

    # Sort by port number (ascending)
    services.sort(key=lambda s: s['host_port'])

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
            'label': [
                f'com.docker.compose.project={COMPOSE_PROJECT}',
                f'com.docker.compose.service={service_name}'
            ]
        }
    )

    return containers[0] if containers else None


def control_service(service_name, action):
    """Control a service (start/stop/restart)"""
    container = get_service_container(service_name)

    try:
        if action == 'start':
            if container and container.status == 'running':
                return {'success': False, 'error': 'Service is already running'}

            # Always use docker compose up -d to ensure container is recreated if config changed
            result = subprocess.run([
                'docker', 'compose', '-f', COMPOSE_FILE, 'up', '-d', service_name
            ], capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                logger.error(f"Failed to start service {service_name}: {result.stderr}")
                return {'success': False, 'error': f'Failed to start service: {result.stderr}'}

            message = f'Service {service_name} created and started' if not container else f'Service {service_name} started'
            return {'success': True, 'message': message}

        elif action == 'stop':
            if not container:
                return {'success': False, 'error': 'Service has not been created yet'}

            if container.status != 'running':
                return {'success': False, 'error': 'Service is not running'}

            container.stop()
            return {'success': True, 'message': f'Service {service_name} stopped'}

        elif action == 'restart':
            if not container:
                return {'success': False, 'error': 'Service has not been created yet. Use Start instead.'}

            container.restart()
            return {'success': True, 'message': f'Service {service_name} restarted'}

        else:
            return {'success': False, 'error': 'Invalid action'}

    except Exception as e:
        logger.error(f"Failed to {action} service {service_name}: {e}")
        return {'success': False, 'error': str(e)}


def get_gpu_stats():
    """Get GPU statistics using nvidia-smi"""
    try:
        result = subprocess.run([
            'nvidia-smi',
            '--query-gpu=index,name,memory.total,memory.used,memory.free,temperature.gpu,'
            'utilization.gpu,utilization.memory,power.draw,power.limit,power.default_limit,'
            'power.min_limit,power.max_limit,enforced.power.limit,clocks.gr,clocks.mem,'
            'fan.speed,pstate',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, check=True, timeout=5)

        gpus = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue

            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 18:
                logger.warning(f"Incomplete nvidia-smi output: {line}")
                continue

            try:
                gpu_data = {
                    'index': int(parts[0]),
                    'name': parts[1],
                    'memory': {
                        'total': int(parts[2]),
                        'used': int(parts[3]),
                        'free': int(parts[4]),
                        'unit': 'MiB',
                        'utilization_percent': int(parts[7]) if parts[7] != '[N/A]' else 0
                    },
                    'temperature': {
                        'current': int(parts[5]) if parts[5] != '[N/A]' else 0,
                        'unit': 'C'
                    },
                    'utilization': {
                        'gpu_percent': int(parts[6]) if parts[6] != '[N/A]' else 0,
                        'memory_percent': int(parts[7]) if parts[7] != '[N/A]' else 0
                    },
                    'power': {
                        'draw': float(parts[8]) if parts[8] != '[N/A]' else 0.0,
                        'limit': {
                            'current': float(parts[9]) if parts[9] != '[N/A]' else 0.0,
                            'default': float(parts[10]) if parts[10] != '[N/A]' else 0.0,
                            'min': float(parts[11]) if parts[11] != '[N/A]' else 0.0,
                            'max': float(parts[12]) if parts[12] != '[N/A]' else 0.0,
                            'enforced': float(parts[13]) if parts[13] != '[N/A]' else 0.0
                        },
                        'unit': 'W'
                    },
                    'clocks': {
                        'graphics': int(parts[14]) if parts[14] != '[N/A]' else 0,
                        'memory': int(parts[15]) if parts[15] != '[N/A]' else 0,
                        'unit': 'MHz'
                    },
                    'fan': {
                        'speed_percent': int(parts[16]) if parts[16] not in ['[N/A]', '[Not Supported]'] else None
                    },
                    'performance_state': parts[17] if parts[17] != '[N/A]' else 'Unknown'
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


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint - no authentication required"""
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'docker_available': check_docker(),
        'nvidia_available': check_nvidia_smi()
    })


@app.route('/api/auth/verify', methods=['POST'])
@require_auth
def verify_token():
    """Verify if the provided token is valid"""
    return jsonify({
        'valid': True,
        'message': 'Token is valid'
    })


@app.route('/api/gpu', methods=['GET'])
@require_auth
def gpu_stats():
    """Get GPU statistics"""
    try:
        gpus = get_gpu_stats()
        return jsonify({
            'gpus': gpus,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    except Exception as e:
        logger.error(f"Failed to get GPU stats: {e}")
        return jsonify({
            'error': {
                'code': 'NVIDIA_ERROR',
                'message': 'Failed to retrieve GPU information',
                'details': str(e)
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }), 500


@app.route('/api/services', methods=['GET'])
@require_auth
def list_services():
    """List all Docker Compose services"""
    try:
        services = get_docker_services()
        return jsonify({
            'services': services,
            'total': len(services),
            'running': sum(1 for s in services if s['status'] == 'running'),
            'stopped': sum(1 for s in services if s['status'] != 'running')
        })
    except Exception as e:
        logger.error(f"Failed to get services: {e}")
        return jsonify({
            'error': {
                'code': 'DOCKER_ERROR',
                'message': 'Failed to retrieve service information'
            }
        }), 500


@app.route('/api/services/<service_name>/start', methods=['POST'])
@require_auth
def start_service(service_name):
    """Start a Docker Compose service"""
    result = control_service(service_name, 'start')

    if result['success']:
        logger.info(f"Started service: {service_name}")
        return jsonify(result)
    else:
        logger.warning(f"Failed to start service {service_name}: {result.get('error')}")
        return jsonify(result), 400


@app.route('/api/services/<service_name>/stop', methods=['POST'])
@require_auth
def stop_service(service_name):
    """Stop a Docker Compose service"""
    result = control_service(service_name, 'stop')

    if result['success']:
        logger.info(f"Stopped service: {service_name}")
        return jsonify(result)
    else:
        logger.warning(f"Failed to stop service {service_name}: {result.get('error')}")
        return jsonify(result), 400


@app.route('/api/v2/services/<service_name>/preview', methods=['GET'])
@require_auth
def preview_service(service_name):
    """Get the rendered YAML for a service"""
    try:
        manager = ComposeManager(COMPOSE_FILE)
        services_db = manager._load_services_db()

        if service_name not in services_db:
            return jsonify({
                'error': {
                    'code': 'SERVICE_NOT_FOUND',
                    'message': f'Service {service_name} not found in database'
                }
            }), 404

        config = services_db[service_name]
        yaml_content = manager._render_service(service_name, config)

        return jsonify({
            'service_name': service_name,
            'yaml': yaml_content
        })

    except Exception as e:
        logger.error(f"Failed to preview service {service_name}: {e}")
        return jsonify({
            'error': {
                'code': 'PREVIEW_ERROR',
                'message': str(e)
            }
        }), 500


@app.route('/api/services/<service_name>/logs', methods=['GET'])
@require_auth
def get_service_logs(service_name):
    """Get logs from a Docker Compose service"""
    try:
        container = get_service_container(service_name)

        if not container:
            return jsonify({
                'error': {
                    'code': 'SERVICE_NOT_FOUND',
                    'message': 'Service has not been created yet'
                }
            }), 404

        # Get tail parameter (default 100 lines)
        tail = request.args.get('tail', default=100, type=int)
        tail = min(tail, 1000)  # Max 1000 lines

        # Get logs
        logs = container.logs(tail=tail, timestamps=True).decode('utf-8')

        return jsonify({
            'service': service_name,
            'logs': logs,
            'lines': len(logs.split('\n')) if logs else 0,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        logger.error(f"Failed to get logs for service {service_name}: {e}")
        return jsonify({
            'error': {
                'code': 'LOGS_ERROR',
                'message': f'Failed to retrieve logs: {str(e)}'
            }
        }), 500


@app.route('/api/system/info', methods=['GET'])
@require_auth
def get_system_info():
    """Get system information including models and disk usage"""
    try:
        # Get disk usage
        disk = get_disk_usage()

        # Get models from all sources
        models = discover_all_models()

        # Calculate total model size
        total_model_size = sum(m['size'] for m in models)

        return jsonify({
            'disk': disk,
            'models': models,
            'model_count': len(models),
            'total_model_size': total_model_size,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        return jsonify({
            'error': {
                'code': 'SYSTEM_INFO_ERROR',
                'message': f'Failed to retrieve system information: {str(e)}'
            }
        }), 500


@app.route('/api/services/create', methods=['POST'])
@require_auth
def create_service():
    """Create a new service in docker-compose.yml"""
    try:
        data = request.get_json()

        # Log incoming request
        logger.info(f"=== CREATE SERVICE REQUEST ===")
        logger.info(f"Request from: {request.remote_addr}")
        logger.info(f"Request data: {json.dumps(data, indent=2) if data else 'None'}")

        if not data:
            logger.error("Request body is empty")
            return jsonify({
                'error': {
                    'code': 'INVALID_REQUEST',
                    'message': 'Request body is required'
                }
            }), 400

        # Extract required fields
        engine = data.get('engine')
        model_data = data.get('model_data')
        options = data.get('options', {})

        logger.info(f"Engine: {engine}")
        logger.info(f"Model data: {json.dumps(model_data, indent=2) if model_data else 'None'}")
        logger.info(f"Options: {json.dumps(options, indent=2)}")

        # Validate required fields
        if not engine:
            logger.error("Engine not provided in request")
            return jsonify({
                'error': {
                    'code': 'MISSING_ENGINE',
                    'message': 'Engine type is required (llamacpp or vllm)'
                }
            }), 400

        if engine not in ['llamacpp', 'vllm']:
            logger.error(f"Invalid engine: {engine}")
            return jsonify({
                'error': {
                    'code': 'INVALID_ENGINE',
                    'message': f'Invalid engine: {engine}. Must be llamacpp or vllm'
                }
            }), 400

        if not model_data:
            logger.error("Model data not provided in request")
            return jsonify({
                'error': {
                    'code': 'MISSING_MODEL_DATA',
                    'message': 'Model data is required'
                }
            }), 400

        # Validate model compatibility with engine
        logger.info(f"Validating model compatibility: {model_data.get('name')} with {engine}")
        compatible, error_msg = validate_model_compatibility(model_data, engine)
        if not compatible:
            logger.error(f"Model compatibility check failed: {error_msg}")
            return jsonify({
                'error': {
                    'code': 'INCOMPATIBLE_MODEL',
                    'message': error_msg
                }
            }), 400

        logger.info(f"Model compatibility check passed")

        # Initialize compose manager
        logger.info("Initializing compose manager...")
        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Auto-generate service name if not provided
        service_name = options.get('service_name')
        if not service_name:
            logger.info(f"Auto-generating service name for {model_data['name']}")
            service_name = generate_service_name(
                model_data['name'],
                engine,
                model_data.get('quantization')
            )
            options['service_name'] = service_name
            logger.info(f"Generated service name: {service_name}")
        else:
            logger.info(f"Using provided service name: {service_name}")

        # Validate service name
        logger.info(f"Validating service name: {service_name}")
        valid, error_msg = compose_mgr.validate_service_name(service_name)
        if not valid:
            logger.error(f"Service name validation failed: {error_msg}")
            return jsonify({
                'error': {
                    'code': 'INVALID_SERVICE_NAME',
                    'message': error_msg
                }
            }), 400
        logger.info(f"Service name validation passed")

        # Auto-assign port if not provided
        port = options.get('port')
        if not port:
            logger.info("Port not provided, auto-assigning...")
            port = compose_mgr.get_next_available_port()
            options['port'] = port
            logger.info(f"Auto-assigned port: {port}")
        else:
            # Validate provided port
            logger.info(f"Validating provided port: {port}")
            valid, error_msg = compose_mgr.validate_port(port)
            if not valid:
                logger.error(f"Port validation failed: {error_msg}")
                return jsonify({
                    'error': {
                        'code': 'INVALID_PORT',
                        'message': error_msg
                    }
                }), 400
            logger.info(f"Port validation passed")

        # Generate API key if not provided
        api_key = options.get('api_key') or generate_api_key()
        logger.info(f"API Key: {api_key[:10]}...")

        # Prepare service configuration for database (NOT docker-compose dict)
        service_config = {
            'template_type': engine,  # 'llamacpp' or 'vllm'
            'port': port,
            'alias': options.get('alias', service_name),
            'api_key': api_key
        }

        # Add engine-specific required fields
        if engine == 'llamacpp':
            # Validate required options for llama.cpp
            if not options.get('model_path'):
                logger.error("model_path not provided for llamacpp service")
                return jsonify({
                    'error': {
                        'code': 'MISSING_MODEL_PATH',
                        'message': 'model_path is required for llama.cpp services'
                    }
                }), 400

            service_config['model_path'] = options['model_path']
            logger.info(f"Model path: {service_config['model_path']}")
            if options.get('mmproj_path'):
                service_config['mmproj_path'] = options['mmproj_path']
                logger.info(f"MMPROJ path: {service_config['mmproj_path']}")

        else:  # vllm
            # For vllm, use HuggingFace model name
            model_name = options.get('model_name', model_data['name'])
            service_config['model_name'] = model_name
            logger.info(f"vLLM model name: {model_name}")

        # Add all optional flags from options
        # Skip the fields we already processed (service_name, port, alias, api_key, model_path, model_name, mmproj_path)
        skip_fields = {'service_name', 'port', 'alias', 'api_key', 'model_path', 'model_name', 'mmproj_path'}
        # Convert all values to strings since flag_metadata.py expects strings
        optional_flags = {k: str(v) for k, v in options.items() if k not in skip_fields and v is not None}

        if optional_flags:
            service_config['optional_flags'] = optional_flags
            logger.info(f"Optional flags: {json.dumps(optional_flags, indent=2)}")

        logger.info(f"Final service config: {json.dumps(service_config, indent=2)}")

        # Add service to database
        logger.info(f"Adding service '{service_name}' to database...")
        try:
            compose_mgr.add_service_to_db(service_name, service_config)
            logger.info(f"Service '{service_name}' added to database successfully")
        except Exception as e:
            logger.error(f"Failed to add service to database: {str(e)}", exc_info=True)
            raise

        # Rebuild docker-compose.yml from database (uses Jinja templates)
        logger.info(f"Rebuilding docker-compose.yml...")
        try:
            compose_mgr.rebuild_compose_file()
            logger.info(f"docker-compose.yml rebuilt successfully")
        except Exception as e:
            logger.error(f"Failed to rebuild docker-compose.yml: {str(e)}", exc_info=True)
            raise

        logger.info(f"Service created: {service_name} on port {port}")

        return jsonify({
            'success': True,
            'service_name': service_name,
            'port': port,
            'api_key': api_key,
            'message': f"Service '{service_name}' created successfully. Start it to begin using."
        }), 201

    except ValueError as e:
        logger.error(f"Validation error creating service: {e}", exc_info=True)
        return jsonify({
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': str(e)
            }
        }), 400

    except Exception as e:
        logger.error(f"Failed to create service: {e}", exc_info=True)
        logger.error(f"=== SERVICE CREATION FAILED ===")
        return jsonify({
            'error': {
                'code': 'SERVICE_CREATION_ERROR',
                'message': f'Failed to create service: {str(e)}'
            }
        }), 500


# ============================================
# NEW SERVICE MANAGEMENT API (Services Database)
# ============================================

@app.route('/api/v2/services', methods=['POST'])
@require_auth
def create_service_v2():
    """
    Create a new service in services database and rebuild compose file.

    Request body:
    {
        "template_type": "llamacpp" | "vllm",
        "port": 3305,
        "model_path": "/path/to/model.gguf",  // for llamacpp
        "model_name": "org/model",             // for vllm
        "alias": "my-model",
        "api_key": "key-xxx" (optional, auto-generated if not provided),
        "optional_flags": {
            "context_length": "32000",
            "gpu_layers": "40"
        }
    }
    """
    try:
        logger.info(f"=== CREATE SERVICE V2 REQUEST ===")
        data = request.get_json()

        if not data:
            logger.error("Request body is empty")
            return jsonify({'error': 'Request body is required'}), 400

        logger.info(f"Request data: {json.dumps(data, indent=2)}")

        template_type = data.get('template_type')
        if not template_type:
            logger.error("template_type not provided")
            return jsonify({'error': 'template_type is required'}), 400

        if template_type not in ['llamacpp', 'vllm']:
            logger.error(f"Invalid template_type: {template_type}")
            return jsonify({'error': 'template_type must be "llamacpp" or "vllm"'}), 400

        # Auto-generate API key if not provided
        if 'api_key' not in data or not data['api_key']:
            data['api_key'] = generate_api_key()
            logger.info(f"Auto-generated API key: {data['api_key'][:10]}...")

        # Validate configuration
        logger.info(f"Validating configuration for {template_type}")
        valid, errors = validate_service_config(template_type, data)
        if not valid:
            logger.error(f"Validation failed: {errors}")
            return jsonify({'error': 'Validation failed', 'details': errors}), 400

        logger.info(f"Configuration validation passed")

        # Generate service name from alias
        alias = data.get('alias')
        service_name = gen_service_name(template_type, alias)
        logger.info(f"Generated service name: {service_name}")

        # Initialize compose manager
        logger.info(f"Initializing compose manager...")
        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service already exists
        logger.info(f"Checking if service '{service_name}' already exists...")
        existing_service = compose_mgr.get_service_from_db(service_name)
        if existing_service:
            logger.error(f"Service '{service_name}' already exists in database")
            return jsonify({'error': f'Service "{service_name}" already exists'}), 409

        # Check port availability
        logger.info(f"Checking port availability...")
        used_ports = compose_mgr.get_used_ports()
        logger.info(f"Used ports: {used_ports}")
        port = int(data['port'])
        logger.info(f"Requested port: {port}")
        if port in used_ports:
            logger.error(f"Port {port} is already in use")
            return jsonify({'error': f'Port {port} is already in use'}), 409

        logger.info(f"Port {port} is available")

        # Add to database
        logger.info(f"Adding service '{service_name}' to database with data: {json.dumps(data, indent=2)}")
        try:
            compose_mgr.add_service_to_db(service_name, data)
            logger.info(f"Service added to database successfully")
        except Exception as e:
            logger.error(f"Failed to add service to database: {str(e)}", exc_info=True)
            raise

        # Rebuild compose file
        logger.info(f"Rebuilding docker-compose.yml...")
        try:
            compose_mgr.rebuild_compose_file()
            logger.info(f"docker-compose.yml rebuilt successfully")
        except Exception as e:
            logger.error(f"Failed to rebuild docker-compose.yml: {str(e)}", exc_info=True)
            raise

        logger.info(f"=== SERVICE CREATED SUCCESSFULLY: {service_name} on port {port} ===")

        return jsonify({
            'success': True,
            'service_name': service_name,
            'port': port,
            'api_key': data['api_key'],
            'message': f'Service "{service_name}" created successfully'
        }), 201

    except Exception as e:
        logger.error(f"=== SERVICE CREATION FAILED ===")
        logger.error(f"Failed to create service: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/services/<service_name>', methods=['GET'])
@require_auth
def get_service_v2(service_name):
    """Get service configuration from database"""
    try:
        compose_mgr = ComposeManager(COMPOSE_FILE)
        config = compose_mgr.get_service_from_db(service_name)

        if not config:
            return jsonify({'error': f'Service "{service_name}" not found'}), 404

        return jsonify({
            'service_name': service_name,
            'config': config
        }), 200

    except Exception as e:
        logger.error(f"Failed to get service: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/services', methods=['GET'])
@require_auth
def list_services_v2():
    """List all services from database"""
    try:
        compose_mgr = ComposeManager(COMPOSE_FILE)
        services = compose_mgr.list_services_in_db()

        return jsonify({
            'services': services,
            'count': len(services)
        }), 200

    except Exception as e:
        logger.error(f"Failed to list services: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/services/<service_name>', methods=['PUT'])
@require_auth
def update_service_v2(service_name):
    """
    Update service configuration and rebuild compose file.

    Note: template_type cannot be changed.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service exists
        existing = compose_mgr.get_service_from_db(service_name)
        if not existing:
            return jsonify({'error': f'Service "{service_name}" not found'}), 404

        # Prevent template_type change
        if 'template_type' in data and data['template_type'] != existing['template_type']:
            return jsonify({'error': 'Cannot change template_type of existing service'}), 400

        # Use existing template_type
        template_type = existing['template_type']
        data['template_type'] = template_type

        # Validate updated configuration
        valid, errors = validate_service_config(template_type, data)
        if not valid:
            return jsonify({'error': 'Validation failed', 'details': errors}), 400

        # Check port if changed
        if 'port' in data and int(data['port']) != int(existing.get('port', 0)):
            used_ports = compose_mgr.get_used_ports()
            new_port = int(data['port'])
            if new_port in used_ports:
                return jsonify({'error': f'Port {new_port} is already in use'}), 409

        # Update in database
        compose_mgr.update_service_in_db(service_name, data)

        # Rebuild compose file
        compose_mgr.rebuild_compose_file()

        logger.info(f"Service updated: {service_name}")

        return jsonify({
            'success': True,
            'service_name': service_name,
            'message': f'Service "{service_name}" updated successfully'
        }), 200

    except Exception as e:
        logger.error(f"Failed to update service: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/services/<service_name>', methods=['DELETE'])
@require_auth
def delete_service_v2(service_name):
    """Delete service from database and rebuild compose file"""
    try:
        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service exists
        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({'error': f'Service "{service_name}" not found'}), 404

        # Get engine type before deletion
        engine = service_config.get('template_type', 'llamacpp')

        # Stop and remove container if running
        try:
            subprocess.run(
                ['docker', 'compose', '-f', COMPOSE_FILE, 'stop', service_name],
                capture_output=True,
                timeout=30
            )
            subprocess.run(
                ['docker', 'compose', '-f', COMPOSE_FILE, 'rm', '-f', service_name],
                capture_output=True,
                timeout=10
            )
            logger.info(f"Stopped and removed container for: {service_name}")
        except Exception as e:
            logger.warning(f"Error stopping container (may not be running): {e}")

        # Remove from database
        compose_mgr.remove_service_from_db(service_name)

        # Rebuild compose file
        compose_mgr.rebuild_compose_file()

        logger.info(f"Service deleted: {service_name}")

        return jsonify({
            'success': True,
            'message': f'Service "{service_name}" deleted successfully'
        }), 200

    except Exception as e:
        logger.error(f"Failed to delete service: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/flag-metadata/<template_type>', methods=['GET'])
@require_auth
def get_flags_metadata(template_type):
    """Get flag metadata for a template type"""
    try:
        if template_type not in ['llamacpp', 'vllm']:
            return jsonify({'error': 'template_type must be "llamacpp" or "vllm"'}), 400

        metadata = get_flag_metadata(template_type)
        mandatory = MANDATORY_FIELDS.get(template_type, [])

        return jsonify({
            'template_type': template_type,
            'mandatory_fields': mandatory,
            'optional_flags': metadata
        }), 200

    except Exception as e:
        logger.error(f"Failed to get flag metadata: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/services/<service_name>/set-public-port', methods=['POST'])
@require_auth
def set_public_port(service_name):
    """
    Set service to use the public port (3301).
    If another service is using 3301, reassign it to a random 33XX port.
    """
    try:
        logger.info(f"=== SET PUBLIC PORT REQUEST for {service_name} ===")
        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service exists
        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({'error': f'Service "{service_name}" not found'}), 404

        # Check if service is already on 3301
        current_port = service_config.get('port')
        if current_port == 3301:
            return jsonify({
                'success': True,
                'message': f'Service "{service_name}" is already on port 3301',
                'no_change': True
            }), 200

        # Find service currently using port 3301
        all_services = compose_mgr.list_services_in_db()
        conflicting_service = None
        conflicting_service_name = None

        for svc_name, svc_config in all_services.items():
            if svc_config.get('port') == 3301:
                conflicting_service = svc_config
                conflicting_service_name = svc_name
                break

        # Prepare updates
        updates_made = []

        if conflicting_service:
            # Reassign conflicting service to random 33XX port
            new_port = compose_mgr.get_next_available_port(start_port=3300, end_port=3399)
            logger.info(f"Reassigning {conflicting_service_name} from port 3301 to {new_port}")

            conflicting_service['port'] = new_port
            compose_mgr.update_service_in_db(conflicting_service_name, conflicting_service)

            updates_made.append({
                'service': conflicting_service_name,
                'old_port': 3301,
                'new_port': new_port
            })

        # Set requested service to 3301
        logger.info(f"Setting {service_name} from port {current_port} to 3301")
        service_config['port'] = 3301
        compose_mgr.update_service_in_db(service_name, service_config)

        updates_made.append({
            'service': service_name,
            'old_port': current_port,
            'new_port': 3301
        })

        # Rebuild compose file
        logger.info("Rebuilding docker-compose.yml...")
        compose_mgr.rebuild_compose_file()

        # Restart affected services
        services_to_restart = [service_name]
        if conflicting_service_name:
            services_to_restart.append(conflicting_service_name)

        restart_results = []
        for svc in services_to_restart:
            container = get_service_container(svc)
            if container and container.status == 'running':
                try:
                    # Use docker compose to recreate with new port
                    result = subprocess.run([
                        'docker', 'compose', '-f', COMPOSE_FILE, 'up', '-d', '--force-recreate', svc
                    ], capture_output=True, text=True, timeout=60)

                    if result.returncode == 0:
                        restart_results.append({'service': svc, 'restarted': True})
                        logger.info(f"Restarted service: {svc}")
                    else:
                        restart_results.append({'service': svc, 'restarted': False, 'error': result.stderr})
                        logger.warning(f"Failed to restart {svc}: {result.stderr}")
                except Exception as e:
                    restart_results.append({'service': svc, 'restarted': False, 'error': str(e)})
                    logger.error(f"Failed to restart {svc}: {e}")

        logger.info(f"=== PUBLIC PORT SET SUCCESSFULLY ===")

        return jsonify({
            'success': True,
            'message': f'Service "{service_name}" now on port 3301',
            'updates': updates_made,
            'restarts': restart_results
        }), 200

    except Exception as e:
        logger.error(f"Failed to set public port: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/services/<service_name>/register-openwebui', methods=['POST'])
@require_auth
def register_service_openwebui(service_name):
    """
    Manually register a service with Open WebUI.
    """
    try:
        logger.info(f"=== MANUAL REGISTER OPENWEBUI REQUEST for {service_name} ===")
        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service exists
        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({'error': f'Service "{service_name}" not found'}), 404

        engine = service_config.get('template_type', '')
        port = service_config.get('port', 0)
        api_key = service_config.get('api_key', '')

        if not engine:
            return jsonify({'error': 'Service has no template_type configured'}), 400

        # Check if already registered
        if is_service_registered_in_openwebui(service_name, engine):
            return jsonify({
                'success': True,
                'message': f'Service "{service_name}" is already registered with Open WebUI',
                'already_registered': True
            }), 200

        # Register with Open WebUI
        success = add_service_to_openwebui(service_name, port, api_key, engine)

        if success:
            return jsonify({
                'success': True,
                'message': f'Service "{service_name}" registered with Open WebUI'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to register service with Open WebUI. Check dashboard logs.'
            }), 500

    except Exception as e:
        logger.error(f"Failed to register service with Open WebUI: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/services/<service_name>/unregister-openwebui', methods=['POST'])
@require_auth
def unregister_service_openwebui(service_name):
    """
    Manually unregister a service from Open WebUI.
    """
    try:
        logger.info(f"=== MANUAL UNREGISTER OPENWEBUI REQUEST for {service_name} ===")
        compose_mgr = ComposeManager(COMPOSE_FILE)

        # Check if service exists
        service_config = compose_mgr.get_service_from_db(service_name)
        if not service_config:
            return jsonify({'error': f'Service "{service_name}" not found'}), 404

        engine = service_config.get('template_type', '')

        if not engine:
            return jsonify({'error': 'Service has no template_type configured'}), 400

        # Check if registered
        if not is_service_registered_in_openwebui(service_name, engine):
            return jsonify({
                'success': True,
                'message': f'Service "{service_name}" is not registered with Open WebUI',
                'already_unregistered': True
            }), 200

        # Unregister from Open WebUI
        success = remove_service_from_openwebui(service_name, engine)

        if success:
            return jsonify({
                'success': True,
                'message': f'Service "{service_name}" unregistered from Open WebUI'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to unregister service from Open WebUI. Check dashboard logs.'
            }), 500

    except Exception as e:
        logger.error(f"Failed to unregister service from Open WebUI: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/openwebui/restart', methods=['POST'])
@require_auth
def restart_openwebui():
    """
    Restart the Open WebUI container to apply configuration changes.
    """
    try:
        logger.info("=== RESTARTING OPEN WEBUI CONTAINER ===")

        result = subprocess.run(
            ['docker', 'restart', 'open-webui'],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            logger.error(f"Failed to restart Open WebUI: {result.stderr}")
            return jsonify({
                'success': False,
                'error': f'Failed to restart: {result.stderr}'
            }), 500

        logger.info("Open WebUI container restarted successfully")
        return jsonify({
            'success': True,
            'message': 'Open WebUI restarted successfully'
        }), 200

    except subprocess.TimeoutExpired:
        logger.error("Timeout while restarting Open WebUI")
        return jsonify({
            'success': False,
            'error': 'Timeout while restarting Open WebUI'
        }), 500
    except Exception as e:
        logger.error(f"Failed to restart Open WebUI: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/')
def index():
    """Serve the frontend"""
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


if __name__ == '__main__':
    logger.info(f'Starting LLM Dashboard on {DASHBOARD_HOST}:{DASHBOARD_PORT}')
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=(LOG_LEVEL == 'DEBUG'))
