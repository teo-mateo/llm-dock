"""
Shared service-config primitives: API key generation and Docker-safe service names.
"""

import re
import secrets


def generate_api_key() -> str:
    """Generate a secure random API key"""
    return f"key-{secrets.token_hex(16)}"


def sanitize_service_name(name: str) -> str:
    """
    Sanitize service name to be Docker-compatible.

    Rules:
    - Lowercase
    - Alphanumeric + hyphens only
    - Max 63 characters
    """
    # Convert to lowercase
    name = name.lower()

    # Replace underscores and spaces with hyphens
    name = name.replace('_', '-').replace(' ', '-')

    # Remove any character that's not alphanumeric or hyphen
    name = re.sub(r'[^a-z0-9-]', '', name)

    # Remove consecutive hyphens
    name = re.sub(r'-+', '-', name)

    # Trim hyphens from start/end
    name = name.strip('-')

    # Limit length
    if len(name) > 63:
        name = name[:63].rstrip('-')

    return name
