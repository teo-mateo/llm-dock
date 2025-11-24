"""
Docker Compose file manager with safe atomic updates.
"""

import os
import shutil
import subprocess
import fcntl
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Set, Optional
from datetime import datetime
import logging
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from flag_metadata import render_flag, generate_service_name

logger = logging.getLogger(__name__)

# Markers for dynamic services section
BEGIN_DYNAMIC_MARKER = "# <<<<<<< BEGIN DYNAMIC"
END_DYNAMIC_MARKER = "# >>>>>>> END DYNAMIC"


class ComposeManager:
    """Manages docker-compose.yml with atomic updates and rollback"""

    def __init__(self, compose_file: str, services_db_file: str = "services.json"):
        """
        Initialize compose manager.

        Args:
            compose_file: Path to docker-compose.yml
            services_db_file: Path to services.json database
        """
        self.compose_path = Path(compose_file)
        if not self.compose_path.exists():
            raise FileNotFoundError(f"Compose file not found: {compose_file}")

        # Services database
        self.services_db_path = Path(compose_file).parent / services_db_file

        # Jinja2 environment for templates
        template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))

    def get_existing_services(self) -> Set[str]:
        """Get list of existing service names"""
        config = self._read_compose()
        return set(config.get('services', {}).keys())

    def get_used_ports(self) -> Set[int]:
        """
        Get set of all ports currently in use by services.

        Returns:
            Set of port numbers
        """
        config = self._read_compose()
        services = config.get('services', {})
        used_ports = set()

        for service_config in services.values():
            ports = service_config.get('ports', [])
            for port_mapping in ports:
                # Parse "3301:8080" format
                if isinstance(port_mapping, str) and ':' in port_mapping:
                    host_port = int(port_mapping.split(':')[0])
                    used_ports.add(host_port)
                elif isinstance(port_mapping, int):
                    used_ports.add(port_mapping)

        return used_ports

    def get_next_available_port(self, start_port: int = 3300, end_port: int = 3400) -> int:
        """
        Find next available port in range.

        Args:
            start_port: Starting port (default: 3300)
            end_port: Ending port (default: 3400)

        Returns:
            Next available port number

        Raises:
            ValueError: If no ports available in range
        """
        used_ports = self.get_used_ports()
        # Also reserve dashboard port
        used_ports.add(3399)

        port = start_port
        while port <= end_port:
            if port not in used_ports:
                return port
            port += 1

        raise ValueError(f"No available ports in range {start_port}-{end_port}")

    def validate_service_name(self, service_name: str) -> tuple[bool, Optional[str]]:
        """
        Validate service name.

        Args:
            service_name: Proposed service name

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not service_name:
            return False, "Service name cannot be empty"

        if len(service_name) > 63:
            return False, "Service name too long (max 63 characters)"

        if not service_name.replace('-', '').replace('_', '').isalnum():
            return False, "Service name must be alphanumeric with hyphens/underscores"

        if service_name in self.get_existing_services():
            return False, f"Service '{service_name}' already exists"

        return True, None

    def validate_port(self, port: int) -> tuple[bool, Optional[str]]:
        """
        Validate port number.

        Args:
            port: Proposed port number

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not (1024 <= port <= 65535):
            return False, "Port must be between 1024 and 65535"

        if port in self.get_used_ports():
            next_port = self.get_next_available_port()
            return False, f"Port {port} already in use. Next available: {next_port}"

        return True, None

    def add_service(self, service_name: str, service_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new service to docker-compose.yml with atomic update.

        Args:
            service_name: Name of the service
            service_config: Service configuration dict

        Returns:
            Dict with success status and message

        Raises:
            ValueError: If validation fails
            IOError: If file operations fail
        """
        # Pre-flight validations
        valid, error = self.validate_service_name(service_name)
        if not valid:
            raise ValueError(error)

        # Extract and validate port
        ports = service_config.get('ports', [])
        if ports:
            port_str = ports[0] if isinstance(ports[0], str) else str(ports[0])
            host_port = int(port_str.split(':')[0])
            valid, error = self.validate_port(host_port)
            if not valid:
                raise ValueError(error)

        # Acquire lock and perform atomic update
        lock_path = self.compose_path.with_suffix('.lock')
        try:
            with open(lock_path, 'w') as lock_file:
                # Acquire exclusive lock (blocks if another process has lock)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

                try:
                    result = self._atomic_add_service(service_name, service_config)
                finally:
                    # Release lock
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

            return result

        except Exception as e:
            logger.error(f"Failed to add service: {e}")
            raise

    def _read_compose(self) -> Dict[str, Any]:
        """Read and parse docker-compose.yml"""
        with open(self.compose_path, 'r') as f:
            return yaml.safe_load(f) or {}

    def _write_compose(self, config: Dict[str, Any], path: Path):
        """Write docker-compose.yml with proper formatting"""
        with open(path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def _atomic_add_service(self, service_name: str, service_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Atomic service addition with backup and rollback.

        Returns:
            Dict with success/error info
        """
        backup_path = self.compose_path.with_suffix('.yml.backup')
        temp_path = self.compose_path.with_suffix('.yml.tmp')

        try:
            # Step 1: Create backup
            shutil.copy2(self.compose_path, backup_path)
            logger.info(f"Created backup: {backup_path}")

            # Step 2: Read existing config
            config = self._read_compose()

            if 'services' not in config:
                raise ValueError("Invalid compose file: missing 'services' section")

            # Step 3: Add new service
            config['services'][service_name] = service_config

            # Step 4: Write to temporary file
            self._write_compose(config, temp_path)
            logger.info(f"Wrote temporary file: {temp_path}")

            # Step 5: Validate with docker compose
            validation_result = self._validate_compose_file(temp_path)
            if not validation_result['valid']:
                raise ValueError(f"Invalid compose configuration: {validation_result['error']}")

            # Step 6: Atomic rename (replace original)
            os.replace(temp_path, self.compose_path)
            logger.info(f"Successfully added service: {service_name}")

            return {
                'success': True,
                'message': f"Service '{service_name}' added successfully",
                'service_name': service_name,
                'backup_created': str(backup_path)
            }

        except Exception as e:
            logger.error(f"Error adding service, attempting rollback: {e}")

            # Rollback: restore from backup
            if backup_path.exists():
                try:
                    os.replace(backup_path, self.compose_path)
                    logger.info("Rollback successful")
                except Exception as rollback_error:
                    logger.error(f"CRITICAL: Rollback failed: {rollback_error}")
                    raise IOError(f"Rollback failed after error: {e}. Manual recovery required.") from rollback_error

            # Clean up temp file
            if temp_path.exists():
                temp_path.unlink()

            raise

        finally:
            # Clean up temp file if it still exists
            if temp_path.exists():
                temp_path.unlink()

    def _validate_compose_file(self, path: Path) -> Dict[str, Any]:
        """
        Validate docker-compose file using docker compose config command.

        Args:
            path: Path to compose file to validate

        Returns:
            Dict with 'valid' (bool) and 'error' (str) keys
        """
        try:
            result = subprocess.run(
                ['docker', 'compose', '-f', str(path), 'config'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return {'valid': True, 'error': None}
            else:
                return {
                    'valid': False,
                    'error': result.stderr.strip() or result.stdout.strip() or 'Unknown validation error'
                }

        except subprocess.TimeoutExpired:
            return {'valid': False, 'error': 'Validation timeout (10s)'}
        except FileNotFoundError:
            logger.warning("docker compose command not found, skipping validation")
            return {'valid': True, 'error': None}  # Allow if docker not available
        except Exception as e:
            return {'valid': False, 'error': str(e)}

    def remove_service(self, service_name: str) -> Dict[str, Any]:
        """
        Remove a service from docker-compose.yml.

        Args:
            service_name: Name of service to remove

        Returns:
            Dict with success status

        Raises:
            ValueError: If service doesn't exist
        """
        existing_services = self.get_existing_services()
        if service_name not in existing_services:
            raise ValueError(f"Service '{service_name}' does not exist")

        lock_path = self.compose_path.with_suffix('.lock')
        try:
            with open(lock_path, 'w') as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

                try:
                    backup_path = self.compose_path.with_suffix('.yml.backup')
                    shutil.copy2(self.compose_path, backup_path)

                    config = self._read_compose()
                    del config['services'][service_name]

                    self._write_compose(config, self.compose_path)
                    logger.info(f"Removed service: {service_name}")

                    return {
                        'success': True,
                        'message': f"Service '{service_name}' removed successfully"
                    }

                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        except Exception as e:
            logger.error(f"Error removing service: {e}")
            raise

    # ============================================
    # SERVICES DATABASE METHODS
    # ============================================

    def _load_services_db(self) -> Dict[str, Any]:
        """Load services database from JSON file"""
        if not self.services_db_path.exists():
            return {}

        try:
            with open(self.services_db_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in services.json: {e}")
            return {}

    def _save_services_db(self, services: Dict[str, Any]):
        """Save services database to JSON file"""
        with open(self.services_db_path, 'w') as f:
            json.dump(services, f, indent=2)

    def add_service_to_db(self, service_name: str, config: Dict[str, Any]):
        """Add service to database"""
        services = self._load_services_db()
        services[service_name] = config
        self._save_services_db(services)

    def update_service_in_db(self, service_name: str, config: Dict[str, Any]):
        """Update service in database"""
        services = self._load_services_db()
        if service_name not in services:
            raise ValueError(f"Service '{service_name}' not found in database")
        services[service_name] = config
        self._save_services_db(services)

    def remove_service_from_db(self, service_name: str):
        """Remove service from database"""
        services = self._load_services_db()
        if service_name not in services:
            raise ValueError(f"Service '{service_name}' not found in database")
        del services[service_name]
        self._save_services_db(services)

    def get_service_from_db(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get service config from database"""
        services = self._load_services_db()
        return services.get(service_name)

    def list_services_in_db(self) -> Dict[str, Any]:
        """List all services in database"""
        return self._load_services_db()

    # ============================================
    # TEMPLATE RENDERING METHODS
    # ============================================

    def _render_service(self, service_name: str, config: Dict[str, Any]) -> str:
        """
        Render service YAML from template and config.

        Args:
            service_name: Name of the service
            config: Service configuration from database

        Returns:
            Rendered YAML as string
        """
        template_type = config['template_type']

        try:
            template = self.jinja_env.get_template(f"{template_type}.j2")
        except TemplateNotFound:
            raise ValueError(f"Template not found for type: {template_type}")

        # Prepare template context
        context = {
            'service_name': service_name,
            'port': config['port'],
        }

        # Add mandatory fields based on template type
        if template_type == 'llamacpp':
            context['model_path'] = config['model_path']
            context['alias'] = config['alias']
            context['api_key'] = config['api_key']
            context['mmproj_path'] = config.get('mmproj_path')
        elif template_type == 'vllm':
            context['model_name'] = config['model_name']
            context['alias'] = config['alias']
            context['api_key'] = config['api_key']

        # Render optional flags
        optional_flags = config.get('optional_flags', {})
        rendered_flags = []

        for flag_name, flag_value in optional_flags.items():
            # Handle environment variables specially
            if flag_name == 'attention_backend':
                context['attention_backend'] = flag_value
                continue

            # Render regular flags
            rendered = render_flag(flag_name, flag_value, template_type)
            if rendered:
                rendered_flags.append(rendered)

        context['rendered_flags'] = rendered_flags

        # Render template
        return template.render(**context)

    def rebuild_compose_file(self):
        """
        Rebuild docker-compose.yml from static section + services database.

        This completely regenerates the dynamic section from services.json.
        """
        lock_path = self.compose_path.with_suffix('.lock')

        try:
            with open(lock_path, 'w') as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

                try:
                    self._rebuild_compose_file_locked()
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        except Exception as e:
            logger.error(f"Failed to rebuild compose file: {e}")
            raise

    def _rebuild_compose_file_locked(self):
        """Internal method to rebuild compose file (assumes lock held)"""
        backup_path = self.compose_path.with_suffix('.yml.backup')
        temp_path = self.compose_path.with_suffix('.yml.tmp')

        try:
            # Backup current file
            shutil.copy2(self.compose_path, backup_path)

            # Read file and split into sections
            prefix, suffix = self._split_compose_file()

            # Generate dynamic section from database
            dynamic_section = self._generate_dynamic_section()

            # Write complete file
            with open(temp_path, 'w') as f:
                f.write(prefix)
                f.write(dynamic_section)
                f.write(suffix)

            # Validate
            validation_result = self._validate_compose_file(temp_path)
            if not validation_result['valid']:
                raise ValueError(f"Generated compose file is invalid: {validation_result['error']}")

            # Atomic replace
            os.replace(temp_path, self.compose_path)
            logger.info("Successfully rebuilt docker-compose.yml")

        except Exception as e:
            logger.error(f"Error rebuilding compose file: {e}")
            # Rollback
            if backup_path.exists():
                os.replace(backup_path, self.compose_path)
                logger.info("Rolled back to backup")
            raise

        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _split_compose_file(self) -> tuple[str, str]:
        """
        Split compose file into prefix (before BEGIN), and suffix (after END).

        Returns:
            (prefix_section, suffix_section)
        """
        with open(self.compose_path, 'r') as f:
            content = f.read()

        # Find markers
        begin_idx = content.find(BEGIN_DYNAMIC_MARKER)
        end_idx = content.find(END_DYNAMIC_MARKER)

        if begin_idx == -1:
            raise ValueError(f"BEGIN marker '{BEGIN_DYNAMIC_MARKER}' not found in compose file")
        if end_idx == -1:
            raise ValueError(f"END marker '{END_DYNAMIC_MARKER}' not found in compose file")

        # Split content
        # Prefix: everything up to and including BEGIN marker line
        prefix_end = content.find('\n', begin_idx) + 1
        prefix = content[:prefix_end]

        # Suffix: everything from END marker line onwards
        suffix_start = content.rfind('\n', 0, end_idx)
        if suffix_start == -1:
            suffix_start = 0
        suffix = content[suffix_start:]

        return prefix, suffix

    def _generate_dynamic_section(self) -> str:
        """Generate dynamic section from services database"""
        services_db = self._load_services_db()

        if not services_db:
            # No services - return empty string
            return ""

        sections = []

        # Render each service
        for service_name, config in services_db.items():
            try:
                rendered = self._render_service(service_name, config)
                sections.append(rendered)
                sections.append("\n")
            except Exception as e:
                logger.error(f"Failed to render service '{service_name}': {e}")
                raise

        return ''.join(sections)
