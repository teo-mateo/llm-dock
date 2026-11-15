from litellm_gateway import ProviderCreds

SERVICES_DB = {
    "vllm-model-a": {
        "template_type": "vllm",
        "port": 3302,
        "model_name": "model-a",
        "alias": "model-a",
        "api_key": "key-upstream-a",
    },
    "llamacpp-model-b": {
        "template_type": "llamacpp",
        "port": 3309,
        "model_path": "/models/b.gguf",
        "alias": "model-b",
        "api_key": "key-upstream-b",
    },
    "vllm-embeddings": {
        "template_type": "vllm",
        "port": 3370,
        "model_name": "bge-m3",
        "alias": "bge-m3",
        "api_key": "key-embed",
        "params": {"--runner": "pooling"},
    },
    "litellm-gateway": {
        "template_type": "litellm",
        "port": 3377,
        "alias": "gateway",
        "api_key": "key-master",
    },
    "ds4-nokey": {
        "template_type": "ds4",
        "port": 3311,
        "model_path": "/models/ds4",
        "alias": "ds4",
        "api_key": "",
    },
}


def gateway_config(routes, api_key="key-master"):
    return {
        "template_type": "litellm",
        "port": 3377,
        "alias": "gateway",
        "api_key": api_key,
        "routes": routes,
    }


def providers(**entries):
    """A provider_lookup over {id: (base_url, key)}."""
    return lambda pid: ProviderCreds(*entries[pid]) if pid in entries else None


NO_PROVIDERS = providers()
