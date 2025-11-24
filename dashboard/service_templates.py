"""
Service templates for llama.cpp and vllm docker-compose services.
"""

import re
import secrets
from typing import Dict, Any, Optional


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


def generate_service_name(model_name: str, engine: str, quantization: Optional[str] = None) -> str:
    """
    Generate service name from model info.

    Args:
        model_name: Full model name (e.g., "unsloth/MiniMax-M2-GGUF")
        engine: "llamacpp" or "vllm"
        quantization: Optional quantization (e.g., "UD-Q2_K_XL")

    Returns:
        Service name like "llammacpp-minimax-m2-q2"
    """
    # Get base name (remove org prefix)
    base_name = model_name.split('/')[-1] if '/' in model_name else model_name

    # Remove common suffixes
    base_name = base_name.replace('-GGUF', '').replace('-Instruct', '').replace('-FP8-Dynamic', '')

    # Add quantization if provided
    if quantization:
        # Simplify quantization name
        quant_short = quantization.replace('UD-', '').replace('_K_XL', '').replace('_', '').lower()
        base_name = f"{base_name}-{quant_short}"

    # Sanitize
    base_name = sanitize_service_name(base_name)

    # Add engine prefix
    service_name = f"{engine}-{base_name}"

    return sanitize_service_name(service_name)


def get_llamacpp_template(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate llama.cpp service configuration for docker-compose.

    Args:
        options: Configuration options with keys:
            - service_name: str
            - port: int
            - model_path: str (container path to GGUF file)
            - mmproj_path: Optional[str] (for vision models)
            - context_length: int (default: 128000)
            - gpu_layers: int (default: 999 = all)
            - batch_size: int (default: 256)
            - repeat_penalty: float (default: 1.3)
            - api_key: str
            - alias: str
            - enable_reasoning: bool (default: False)

    Returns:
        Dictionary suitable for docker-compose.yml services section
    """
    service_name = options['service_name']
    port = options['port']
    model_path = options['model_path']
    api_key = options.get('api_key') or generate_api_key()

    # Build command parts
    cmd_parts = [
        '/llama.cpp/build/bin/llama-server',
        f'-m {model_path}',
    ]

    # Add mmproj for vision models
    if options.get('mmproj_path'):
        cmd_parts.append(f"--mmproj {options['mmproj_path']}")

    # Add configuration flags
    cmd_parts.extend([
        f"--repeat_penalty {options.get('repeat_penalty', 1.3)}",
        f"--alias {options.get('alias', service_name)}",
        '--host "0.0.0.0"',
        '--port 8080',
        f"-c {options.get('context_length', 128000)}",
        f"-ngl {options.get('gpu_layers', 999)}",
        '-t 1.0',
        '--top-p 0.95',
        '--top-k 40.0',
        '--jinja',
    ])

    # Add reasoning format if requested
    if options.get('enable_reasoning', False):
        cmd_parts.append('--reasoning-format auto')

    # Add batch sizes and API key
    batch_size = options.get('batch_size', 256)
    cmd_parts.extend([
        f'-ub {batch_size}',
        f'-b {batch_size}',
        f'--api-key {api_key}'
    ])

    # Join command with proper line continuation
    command = ' \\\n      '.join(cmd_parts)

    return {
        'image': 'my-llamacpp',
        'container_name': service_name,
        'restart': 'no',
        'deploy': {
            'resources': {
                'reservations': {
                    'devices': [{
                        'driver': 'nvidia',
                        'count': 'all',
                        'capabilities': ['gpu']
                    }]
                }
            }
        },
        'ports': [f"{port}:8080"],
        'ipc': 'host',
        'environment': [
            f'LLAMA_SERVER_API_KEY={api_key}'
        ],
        'volumes': [
            '${HOME}/.cache/huggingface:/hf-cache'
        ],
        'command': f"|\n      {command}"
    }


def get_vllm_template(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate vllm service configuration for docker-compose.

    Args:
        options: Configuration options with keys:
            - service_name: str
            - port: int
            - model_name: str (HuggingFace model identifier)
            - context_length: Optional[int]
            - gpu_memory_util: float (default: 0.92)
            - max_batched_tokens: int (default: 8192)
            - max_sequences: int (default: 128)
            - api_key: str
            - alias: str

    Returns:
        Dictionary suitable for docker-compose.yml services section
    """
    service_name = options['service_name']
    port = options['port']
    model_name = options['model_name']
    api_key = options.get('api_key') or generate_api_key()

    # Build command parts
    cmd_parts = [
        f'serve {model_name}',
        '--host 0.0.0.0',
        '--port 8000',
        '--trust-remote-code',
        f"--served-model-name {options.get('alias', service_name)}",
    ]

    # Add context length if specified
    if options.get('context_length'):
        cmd_parts.append(f"--max-model-len {options['context_length']}")

    # Add performance options
    cmd_parts.extend([
        f"--gpu-memory-utilization {options.get('gpu_memory_util', 0.92)}",
        f"--max-num-batched-tokens {options.get('max_batched_tokens', 8192)}",
        f"--max-num-seqs {options.get('max_sequences', 128)}",
        f'--api-key {api_key}',
        '--enable-auto-tool-choice',
        '--tool-call-parser hermes'
    ])

    # Join command
    command = ' '.join(cmd_parts)

    return {
        'image': 'vllm/vllm-openai:v0.11.0',
        'container_name': service_name,
        'restart': 'no',
        'deploy': {
            'resources': {
                'reservations': {
                    'devices': [{
                        'driver': 'nvidia',
                        'count': 'all',
                        'capabilities': ['gpu']
                    }]
                }
            }
        },
        'ports': [f"{port}:8000"],
        'ipc': 'host',
        'environment': [
            'VLLM_ATTENTION_BACKEND=FLASHINFER'
        ],
        'volumes': [
            '${HOME}/.cache/huggingface:/root/.cache/huggingface',
            '${HOME}/.cache/torch:/root/.cache/torch',
            '${HOME}/.triton:/root/.triton'
        ],
        'entrypoint': ['vllm'],
        'command': command
    }


def validate_model_compatibility(model_data: Dict[str, Any], engine: str) -> tuple[bool, Optional[str]]:
    """
    Validate that model format is compatible with selected engine.

    Args:
        model_data: Model info from discovery
        engine: "llamacpp" or "vllm"

    Returns:
        Tuple of (is_valid, error_message)
    """
    files = model_data.get('files', [])

    if not files:
        return False, "No model files found"

    has_gguf = any(f['name'].endswith('.gguf') for f in files)
    has_safetensors = any(f['name'].endswith('.safetensors') for f in files)
    has_bin = any(f['name'].endswith('.bin') for f in files)

    if engine == 'llamacpp':
        if not has_gguf:
            return False, "llama.cpp requires GGUF format models. This model appears to be in safetensors/bin format. Use vllm engine instead."
        return True, None

    elif engine == 'vllm':
        if has_gguf and not (has_safetensors or has_bin):
            return False, "vllm does not support GGUF models. This model is GGUF format. Use llama.cpp engine instead."
        return True, None

    else:
        return False, f"Unknown engine: {engine}"
