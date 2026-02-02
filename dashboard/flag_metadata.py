"""
Flag metadata and validation for service templates.
Defines how flags are rendered and validated for each template type.
"""

from typing import Dict, Any, List, Tuple, Optional
from service_templates import sanitize_service_name

# ============================================
# MANDATORY FIELDS (per template type)
# ============================================

MANDATORY_FIELDS = {
    'llamacpp': ['port', 'model_path', 'alias', 'api_key'],
    'vllm': ['port', 'model_name', 'alias', 'api_key']
}

# ============================================
# FLAG METADATA
# Defines CLI mapping and type for each flag
# ============================================

LLAMACPP_FLAGS = {
    # Core model flags
    'mmproj_path': {
        'cli': '--mmproj',
        'type': 'path',
        'description': 'Path to multi-modal projector (for vision models)'
    },

    # Context and performance
    'context_length': {
        'cli': '-c',
        'type': 'int',
        'description': 'Context length in tokens',
        'default': '128000'
    },
    'gpu_layers': {
        'cli': '-ngl',
        'type': 'int',
        'description': 'Number of layers to offload to GPU (999 = all)',
        'default': '999'
    },
    'batch_size': {
        'cli': '-b',
        'type': 'int',
        'description': 'Batch size for prompt processing',
        'default': '256'
    },
    'ubatch_size': {
        'cli': '-ub',
        'type': 'int',
        'description': 'Physical batch size for prompt processing',
        'default': '256'
    },

    # Sampling parameters
    'repeat_penalty': {
        'cli': '--repeat_penalty',
        'type': 'float',
        'description': 'Penalty for repeating tokens',
        'default': '1.3'
    },
    'top_p': {
        'cli': '--top-p',
        'type': 'float',
        'description': 'Top-p sampling',
        'default': '0.95'
    },
    'top_k': {
        'cli': '--top-k',
        'type': 'float',
        'description': 'Top-k sampling',
        'default': '40.0'
    },
    'temperature': {
        'cli': '-t',
        'type': 'float',
        'description': 'Temperature for sampling',
        'default': '1.0'
    },

    # Features
    'flash_attn': {
        'cli': '--flash-attn',
        'type': 'string',
        'description': 'Flash attention mode (on, off, or auto)',
        'default': 'auto'
    },
    'jinja': {
        'cli': '--jinja',
        'type': 'bool',
        'description': 'Enable Jinja template parsing'
    },
    'verbose': {
        'cli': '-v',
        'type': 'bool',
        'description': 'Enable verbose logging (max verbosity)'
    },
    'log_verbosity': {
        'cli': '--log-verbosity',
        'type': 'int',
        'description': 'Set verbosity threshold level'
    },
    'log_file': {
        'cli': '--log-file',
        'type': 'string',
        'description': 'Log output to file'
    },
    'reasoning_format': {
        'cli': '--reasoning-format',
        'type': 'string',
        'description': 'Reasoning format (auto, cot, etc.)'
    },

    # RoPE scaling
    'rope_freq_base': {
        'cli': '--rope-freq-base',
        'type': 'int',
        'description': 'RoPE frequency base'
    },
    'rope_freq_scale': {
        'cli': '--rope-freq-scale',
        'type': 'float',
        'description': 'RoPE frequency scaling factor'
    },
}

VLLM_FLAGS = {
    # ========== CONTEXT & MEMORY (Top Priority) ==========
    'max_model_len': {
        'cli': '--max-model-len',
        'type': 'int',
        'category': 'Context & Memory',
        'description': 'Maximum context length in tokens. Determines longest input the model can process.',
        'impact': 'Critical'
    },
    'gpu_memory_utilization': {
        'cli': '--gpu-memory-utilization',
        'type': 'float',
        'category': 'Context & Memory',
        'description': 'Fraction of GPU memory to use (0.0-1.0). Higher = more concurrent requests but risk of OOM.',
        'default': '0.92',
        'impact': 'High'
    },
    'swap_space': {
        'cli': '--swap-space',
        'type': 'float',
        'category': 'Context & Memory',
        'description': 'CPU swap space per GPU in GiB. Spills to CPU when GPU full, reduces OOM but slower.',
        'default': '4',
        'impact': 'Medium'
    },
    'cpu_offload_gb': {
        'cli': '--cpu-offload-gb',
        'type': 'float',
        'category': 'Context & Memory',
        'description': 'Offload this much memory to CPU. Virtually increases GPU capacity at cost of speed.',
        'default': '0',
        'impact': 'Medium'
    },

    # ========== QUANTIZATION & PRECISION ==========
    'quantization': {
        'cli': '--quantization',
        'type': 'string',
        'category': 'Quantization & Precision',
        'description': 'Quantization method (awq, gptq, fp8, etc.). Reduces model size and speeds up inference.',
        'options': 'aqlm, awq, deepspeedfp, fp8, gptq_marlin, awq_marlin, gptq, bitsandbytes, qqq, hqq, marlin',
        'impact': 'Critical'
    },
    'dtype': {
        'cli': '--dtype',
        'type': 'string',
        'category': 'Quantization & Precision',
        'description': 'Model data type (auto, float16, bfloat16, float32). Affects speed and memory.',
        'options': 'auto, float16, bfloat16, float32',
        'impact': 'High'
    },
    'kv_cache_dtype': {
        'cli': '--kv-cache-dtype',
        'type': 'string',
        'category': 'Quantization & Precision',
        'description': 'KV cache format (auto, fp8, fp8_e5m2, fp8_e4m3). FP8 saves 40-50% memory for long sequences.',
        'options': 'auto, fp8, fp8_e5m2, fp8_e4m3',
        'impact': 'High'
    },

    # ========== BATCHING & THROUGHPUT ==========
    'max_num_batched_tokens': {
        'cli': '--max-num-batched-tokens',
        'type': 'int',
        'category': 'Batching & Throughput',
        'description': 'Maximum tokens processed per batch iteration. Higher = better throughput, higher memory.',
        'default': '8192',
        'impact': 'High'
    },
    'max_num_seqs': {
        'cli': '--max-num-seqs',
        'type': 'int',
        'category': 'Batching & Throughput',
        'description': 'Maximum concurrent sequences. Higher = more parallel requests but uses more memory.',
        'default': '128',
        'impact': 'High'
    },
    'max_num_partial_prefills': {
        'cli': '--max-num-partial-prefills',
        'type': 'int',
        'category': 'Batching & Throughput',
        'description': 'Maximum concurrent chunked prefills. Improves throughput for long prompts.',
        'default': '1',
        'impact': 'Medium'
    },
    'enable_chunked_prefill': {
        'cli': '--enable-chunked-prefill',
        'type': 'bool',
        'category': 'Batching & Throughput',
        'description': 'Split large prompts into chunks to reduce first-token latency.',
        'impact': 'Medium'
    },

    # ========== CACHING & OPTIMIZATION ==========
    'enable_prefix_caching': {
        'cli': '--enable-prefix-caching',
        'type': 'bool',
        'category': 'Caching & Optimization',
        'description': 'Reuse computation for repeated prompt prefixes. Massive speedup for repeated queries.',
        'impact': 'High'
    },
    'block_size': {
        'cli': '--block-size',
        'type': 'int',
        'category': 'Caching & Optimization',
        'description': 'Token block size (8, 16, 32, 64, 128). Affects memory efficiency vs latency.',
        'options': '8, 16, 32, 64, 128',
        'impact': 'Low'
    },

    # ========== DISTRIBUTED & SCALING ==========
    'tensor_parallel_size': {
        'cli': '--tensor-parallel-size',
        'type': 'int',
        'category': 'Distributed & Scaling',
        'description': 'Shard model across N GPUs. Essential for models larger than single GPU.',
        'default': '1',
        'impact': 'Critical'
    },
    'pipeline_parallel_size': {
        'cli': '--pipeline-parallel-size',
        'type': 'int',
        'category': 'Distributed & Scaling',
        'description': 'Pipeline parallelism across N stages. Distribute across multiple nodes.',
        'default': '1',
        'impact': 'High'
    },

    # ========== MODEL FORMAT & LOADING ==========
    'load_format': {
        'cli': '--load-format',
        'type': 'string',
        'category': 'Model Format & Loading',
        'description': 'Weight format (auto, safetensors, tensorizer, gguf, etc.). Auto-detect or force specific format.',
        'options': 'auto, safetensors, pt, gguf, tensorizer, npcache',
        'impact': 'Medium'
    },
    'trust_remote_code': {
        'cli': '--trust-remote-code',
        'type': 'bool',
        'category': 'Model Format & Loading',
        'description': 'Allow execution of custom code from model repo. Required for some models.',
        'impact': 'Low'
    },

    # ========== GENERATION & SAMPLING ==========
    'max_logprobs': {
        'cli': '--max-logprobs',
        'type': 'int',
        'category': 'Generation & Sampling',
        'description': 'Maximum log probabilities to return. For ranking/uncertainty estimation.',
        'default': '20',
        'impact': 'Low'
    },
    'seed': {
        'cli': '--seed',
        'type': 'int',
        'category': 'Generation & Sampling',
        'description': 'Random seed for reproducible outputs.',
        'impact': 'Low'
    },

    # ========== LORA & ADAPTERS ==========
    'enable_lora': {
        'cli': '--enable-lora',
        'type': 'bool',
        'category': 'LoRA & Adapters',
        'description': 'Enable LoRA adapter support for fine-tuned model variants.',
        'impact': 'Medium'
    },
    'max_loras': {
        'cli': '--max-loras',
        'type': 'int',
        'category': 'LoRA & Adapters',
        'description': 'Maximum LoRA adapters in a single batch.',
        'default': '1',
        'impact': 'Low'
    },
    'max_lora_rank': {
        'cli': '--max-lora-rank',
        'type': 'int',
        'category': 'LoRA & Adapters',
        'description': 'Maximum LoRA rank (complexity of adapter).',
        'default': '16',
        'impact': 'Low'
    },

    # ========== MULTIMODAL ==========
    'limit_mm_per_prompt': {
        'cli': '--limit-mm-per-prompt',
        'type': 'string',
        'category': 'Multimodal',
        'description': 'Limit multimodal inputs per request. Format: "image=16,video=2"',
        'impact': 'Low'
    },

    # ========== FEATURES & TOOLS ==========
    'enable_auto_tool_choice': {
        'cli': '--enable-auto-tool-choice',
        'type': 'bool',
        'category': 'Features & Tools',
        'description': 'Enable automatic tool choice in function calling.',
        'default': 'true',
        'impact': 'Low'
    },
    'tool_call_parser': {
        'cli': '--tool-call-parser',
        'type': 'string',
        'category': 'Features & Tools',
        'description': 'Tool call parser (hermes, pythonic, etc.). Model-specific.',
        'options': 'hermes, pythonic, auto',
        'default': 'hermes',
        'impact': 'Low'
    },

    # ========== ROPE SCALING ==========
    'rope_scaling': {
        'cli': '--rope-scaling',
        'type': 'string',
        'category': 'RoPE Scaling',
        'description': 'RoPE scaling config as JSON. Extends context length. Example: {"type":"dynamic","factor":2.0}',
        'impact': 'Medium'
    },
    'rope_theta': {
        'cli': '--rope-theta',
        'type': 'float',
        'category': 'RoPE Scaling',
        'description': 'RoPE theta parameter. Frequency base for positional encoding.',
        'impact': 'Low'
    },

    # ========== ATTENTION & OPTIMIZATION ==========
    'attention_backend': {
        'cli': 'VLLM_ATTENTION_BACKEND',
        'type': 'env',
        'category': 'Attention & Optimization',
        'description': 'Attention backend (FLASHINFER, XFORMERS, TORCH, etc.). FLASHINFER is fastest.',
        'options': 'FLASHINFER, XFORMERS, TORCH',
        'default': 'FLASHINFER',
        'impact': 'High'
    },

    # ========== SCHEDULING ==========
    'scheduling_policy': {
        'cli': '--scheduling-policy',
        'type': 'string',
        'category': 'Scheduling',
        'description': 'Scheduling policy (fcfs=first-come-first-serve, priority=by priority).',
        'options': 'fcfs, priority',
        'default': 'fcfs',
        'impact': 'Low'
    },
    'preemption_mode': {
        'cli': '--preemption-mode',
        'type': 'string',
        'category': 'Scheduling',
        'description': 'Preemption mode (recompute=recompute from checkpoint, swap=swap to CPU).',
        'options': 'recompute, swap',
        'impact': 'Medium'
    },
}

# ============================================
# VALIDATION RULES
# ============================================

LLAMACPP_VALIDATION = {
    'context_length': {
        'type': 'int',
        'min': 512,
        'max': 1000000
    },
    'gpu_layers': {
        'type': 'int',
        'min': 0,
        'max': 999
    },
    'batch_size': {
        'type': 'int',
        'min': 1,
        'max': 2048
    },
    'ubatch_size': {
        'type': 'int',
        'min': 1,
        'max': 2048
    },
    'repeat_penalty': {
        'type': 'float',
        'min': 0.0,
        'max': 2.0
    },
    'top_p': {
        'type': 'float',
        'min': 0.0,
        'max': 1.0
    },
    'top_k': {
        'type': 'float',
        'min': 1.0,
        'max': 100.0
    },
    'temperature': {
        'type': 'float',
        'min': 0.0,
        'max': 2.0
    },
    'rope_freq_base': {
        'type': 'int',
        'min': 1,
        'max': 1000000
    },
    'rope_freq_scale': {
        'type': 'float',
        'min': 0.0,
        'max': 10.0
    },
}

VLLM_VALIDATION = {
    'max_model_len': {
        'type': 'int',
        'min': 512,
        'max': 1000000
    },
    'gpu_memory_utilization': {
        'type': 'float',
        'min': 0.1,
        'max': 1.0
    },
    'max_num_batched_tokens': {
        'type': 'int',
        'min': 1,
        'max': 100000
    },
    'max_num_seqs': {
        'type': 'int',
        'min': 1,
        'max': 1000
    },
}

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_flag_metadata(template_type: str) -> Dict[str, Any]:
    """Get flag metadata for template type"""
    if template_type == 'llamacpp':
        return LLAMACPP_FLAGS
    elif template_type == 'vllm':
        return VLLM_FLAGS
    else:
        return {}

def get_validation_rules(template_type: str) -> Dict[str, Any]:
    """Get validation rules for template type"""
    if template_type == 'llamacpp':
        return LLAMACPP_VALIDATION
    elif template_type == 'vllm':
        return VLLM_VALIDATION
    else:
        return {}

def render_flag(flag_name: str, flag_value: str, template_type: str) -> Optional[str]:
    """
    Render a flag as CLI argument.

    Args:
        flag_name: Name of the flag
        flag_value: Value as string
        template_type: 'llamacpp' or 'vllm'

    Returns:
        Rendered CLI argument or None if flag should be skipped
    """
    metadata = get_flag_metadata(template_type)

    if flag_name not in metadata:
        # Unknown flag - skip it
        return None

    flag_meta = metadata[flag_name]
    cli_arg = flag_meta['cli']
    flag_type = flag_meta['type']

    # Skip environment variables (handled separately)
    if flag_type == 'env':
        return None

    # Boolean flags
    if flag_type == 'bool':
        # Empty string or "true" = render flag
        if flag_value == "" or flag_value.lower() == "true":
            return cli_arg
        else:
            return None

    # Value flags (int, float, string, path)
    else:
        if not flag_value or flag_value.strip() == "":
            return None
        return f"{cli_arg} {flag_value}"

def generate_service_name(template_type: str, alias: str) -> str:
    """
    Generate service name from template type and alias.

    Convention: {template_type}-{alias}
    Example: llamacpp-minimax-m2-q2

    Args:
        template_type: 'llamacpp' or 'vllm'
        alias: Model alias

    Returns:
        Sanitized service name
    """
    return sanitize_service_name(f"{template_type}-{alias}")

def render_custom_flag(flag_name: str, flag_value: str) -> Optional[str]:
    """
    Render a custom flag as CLI argument.

    Args:
        flag_name: The flag name (must start with - or --)
        flag_value: The flag value (empty string for boolean flags)

    Returns:
        Rendered CLI argument string, or None if flag name is invalid.

    Note:
        For boolean flags (no value needed), pass empty string as flag_value.
        The flag will be rendered as just the flag name (e.g., "--verbose").

        This function includes defensive validation - it returns None for
        invalid flag names rather than raising an exception. Use
        validate_custom_flag_name() for explicit validation with error messages.
    """
    if not flag_name or not flag_name.startswith('-'):
        return None
    if not flag_value or flag_value.strip() == "":
        return flag_name  # Boolean flag (e.g., "--verbose")
    return f"{flag_name} {flag_value}"


def validate_custom_flag_name(flag_name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate custom flag name format.

    Args:
        flag_name: The flag name to validate

    Returns:
        (is_valid, error_message or None)
    """
    if not flag_name:
        return False, "Flag name cannot be empty"
    if not flag_name.startswith('-'):
        return False, "Flag name must start with - or --"
    name_part = flag_name.lstrip('-')
    if not name_part:
        return False, "Flag name cannot be just dashes"
    if not all(c.isalnum() or c in '-_' for c in name_part):
        return False, "Invalid characters in flag name"
    return True, None


def validate_service_config(template_type: str, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate service configuration.

    Args:
        template_type: 'llamacpp' or 'vllm'
        config: Service configuration dict

    Returns:
        (is_valid, list_of_error_messages)
    """
    errors = []

    # Check mandatory fields
    mandatory = MANDATORY_FIELDS.get(template_type, [])
    for field in mandatory:
        if field not in config or not config[field]:
            errors.append(f"Missing mandatory field: {field}")

    # Check port
    if 'port' not in config:
        errors.append("Missing port number")
    else:
        try:
            port = int(config['port'])
            if port < 1024 or port > 65535:
                errors.append(f"Port must be between 1024 and 65535, got {port}")
        except (ValueError, TypeError):
            errors.append(f"Invalid port: {config['port']}")

    # Validate optional flags
    optional_flags = config.get('optional_flags', {})
    validation_rules = get_validation_rules(template_type)

    for flag_name, flag_value in optional_flags.items():
        if flag_name not in validation_rules:
            continue  # Unknown flag, allow it

        rule = validation_rules[flag_name]
        value_type = rule['type']

        # Skip empty values
        if not flag_value or flag_value.strip() == "":
            continue

        # Type validation
        try:
            if value_type == 'int':
                val = int(flag_value)
                if 'min' in rule and val < rule['min']:
                    errors.append(f"{flag_name}: value {val} below minimum {rule['min']}")
                if 'max' in rule and val > rule['max']:
                    errors.append(f"{flag_name}: value {val} above maximum {rule['max']}")

            elif value_type == 'float':
                val = float(flag_value)
                if 'min' in rule and val < rule['min']:
                    errors.append(f"{flag_name}: value {val} below minimum {rule['min']}")
                if 'max' in rule and val > rule['max']:
                    errors.append(f"{flag_name}: value {val} above maximum {rule['max']}")

        except (ValueError, TypeError):
            errors.append(f"{flag_name}: invalid {value_type} value '{flag_value}'")

    # Validate custom flags
    custom_flags = config.get('custom_flags', {})
    for flag_name, flag_value in custom_flags.items():
        is_valid, error = validate_custom_flag_name(flag_name)
        if not is_valid:
            errors.append(f"Custom flag '{flag_name}': {error}")

    return len(errors) == 0, errors
