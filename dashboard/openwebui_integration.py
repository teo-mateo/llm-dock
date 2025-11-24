#!/usr/bin/env python3
"""
Open WebUI Integration
Handles automatic registration of model services with Open WebUI
"""

import json
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def add_service_to_openwebui(service_name: str, port: int, api_key: str, engine: str):
    """
    Add a newly created service to Open WebUI's configuration.

    Args:
        service_name: Name of the service (e.g., "llamacpp-qwen3-vl-8b-q8")
        port: Host port the service is exposed on
        api_key: API key for the service
        engine: Engine type ("llamacpp" or "vllm")

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Construct the base URL (internal docker network address)
        # For llamacpp: http://service:8080/v1
        # For vllm: http://service:8000/v1
        internal_port = 8080 if engine == "llamacpp" else 8000
        base_url = f"http://{service_name}:{internal_port}/v1"

        logger.info(f"Adding service '{service_name}' to Open WebUI")
        logger.info(f"  Base URL: {base_url}")
        logger.info(f"  API Key: {api_key[:10]}...")

        # Python script to execute inside the Open WebUI container
        python_script = f"""
import sqlite3
import json
from datetime import datetime

try:
    conn = sqlite3.connect('/app/backend/data/webui.db')
    cursor = conn.cursor()

    # Read current config
    cursor.execute('SELECT id, data, version FROM config WHERE id = 1')
    row = cursor.fetchone()

    if not row:
        print('ERROR: No config found')
        exit(1)

    config_id, data_json, version = row
    data = json.loads(data_json)

    # Ensure openai section exists
    if 'openai' not in data:
        data['openai'] = {{
            'enable': True,
            'api_base_urls': [],
            'api_keys': [],
            'api_configs': {{}}
        }}

    openai_config = data['openai']

    # Check if this service is already registered
    base_url = '{base_url}'
    if base_url in openai_config.get('api_base_urls', []):
        print(f'Service already registered: {{base_url}}')
        exit(0)

    # Add the new service
    api_base_urls = openai_config.get('api_base_urls', [])
    api_keys = openai_config.get('api_keys', [])
    api_configs = openai_config.get('api_configs', {{}})

    # Append new values
    api_base_urls.append(base_url)
    api_keys.append('{api_key}')

    # Create new config entry with the next index
    next_index = str(len(api_base_urls) - 1)
    api_configs[next_index] = {{
        'enable': True,
        'tags': [],
        'prefix_id': '',
        'model_ids': [],
        'connection_type': 'external',
        'auth_type': 'bearer'
    }}

    # Update openai section
    openai_config['enable'] = True
    openai_config['api_base_urls'] = api_base_urls
    openai_config['api_keys'] = api_keys
    openai_config['api_configs'] = api_configs

    data['openai'] = openai_config

    # Save back to database
    updated_json = json.dumps(data)
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')

    cursor.execute(
        'UPDATE config SET data = ?, updated_at = ? WHERE id = ?',
        (updated_json, now, config_id)
    )

    conn.commit()
    conn.close()

    print(f'Successfully added {{base_url}} to Open WebUI')

except Exception as e:
    print(f'ERROR: {{str(e)}}')
    import traceback
    traceback.print_exc()
    exit(1)
"""

        # Execute the Python script inside the Open WebUI container
        result = subprocess.run(
            ['docker', 'exec', 'open-webui', 'python', '-c', python_script],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            logger.error(f"Failed to add service to Open WebUI: {result.stderr}")
            logger.error(f"stdout: {result.stdout}")
            return False

        logger.info(f"Open WebUI response: {result.stdout.strip()}")
        logger.info(f"Service '{service_name}' successfully registered with Open WebUI")
        return True

    except subprocess.TimeoutExpired:
        logger.error("Timeout while adding service to Open WebUI")
        return False
    except Exception as e:
        logger.error(f"Error adding service to Open WebUI: {e}", exc_info=True)
        return False


def remove_service_from_openwebui(service_name: str, engine: str):
    """
    Remove a service from Open WebUI's configuration.

    Args:
        service_name: Name of the service to remove
        engine: Engine type ("llamacpp" or "vllm")

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Construct the base URL
        internal_port = 8080 if engine == "llamacpp" else 8000
        base_url = f"http://{service_name}:{internal_port}/v1"

        logger.info(f"Removing service '{service_name}' from Open WebUI")
        logger.info(f"  Base URL: {base_url}")

        # Python script to execute inside the Open WebUI container
        python_script = f"""
import sqlite3
import json
from datetime import datetime

try:
    conn = sqlite3.connect('/app/backend/data/webui.db')
    cursor = conn.cursor()

    # Read current config
    cursor.execute('SELECT id, data, version FROM config WHERE id = 1')
    row = cursor.fetchone()

    if not row:
        print('ERROR: No config found')
        exit(1)

    config_id, data_json, version = row
    data = json.loads(data_json)

    # Check if openai section exists
    if 'openai' not in data or 'api_base_urls' not in data['openai']:
        print('No services registered in Open WebUI')
        exit(0)

    openai_config = data['openai']
    base_url = '{base_url}'

    # Find and remove the service
    api_base_urls = openai_config.get('api_base_urls', [])

    if base_url not in api_base_urls:
        print(f'Service not found: {{base_url}}')
        exit(0)

    # Get the index to remove
    index_to_remove = api_base_urls.index(base_url)

    # Remove from all arrays
    api_base_urls.pop(index_to_remove)
    api_keys = openai_config.get('api_keys', [])
    if index_to_remove < len(api_keys):
        api_keys.pop(index_to_remove)

    # Rebuild api_configs with new indices
    old_configs = openai_config.get('api_configs', {{}})
    new_configs = {{}}

    for i in range(len(api_base_urls)):
        old_index = str(i if i < index_to_remove else i + 1)
        if old_index in old_configs:
            new_configs[str(i)] = old_configs[old_index]
        else:
            # Default config for entries without existing config
            new_configs[str(i)] = {{
                'enable': True,
                'tags': [],
                'prefix_id': '',
                'model_ids': [],
                'connection_type': 'external',
                'auth_type': 'bearer'
            }}

    # Update openai section
    openai_config['api_base_urls'] = api_base_urls
    openai_config['api_keys'] = api_keys
    openai_config['api_configs'] = new_configs

    data['openai'] = openai_config

    # Save back to database
    updated_json = json.dumps(data)
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')

    cursor.execute(
        'UPDATE config SET data = ?, updated_at = ? WHERE id = ?',
        (updated_json, now, config_id)
    )

    conn.commit()
    conn.close()

    print(f'Successfully removed {{base_url}} from Open WebUI')

except Exception as e:
    print(f'ERROR: {{str(e)}}')
    import traceback
    traceback.print_exc()
    exit(1)
"""

        # Execute the Python script inside the Open WebUI container
        result = subprocess.run(
            ['docker', 'exec', 'open-webui', 'python', '-c', python_script],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            logger.error(f"Failed to remove service from Open WebUI: {result.stderr}")
            logger.error(f"stdout: {result.stdout}")
            return False

        logger.info(f"Open WebUI response: {result.stdout.strip()}")
        logger.info(f"Service '{service_name}' successfully removed from Open WebUI")
        return True

    except subprocess.TimeoutExpired:
        logger.error("Timeout while removing service from Open WebUI")
        return False
    except Exception as e:
        logger.error(f"Error removing service from Open WebUI: {e}", exc_info=True)
        return False
