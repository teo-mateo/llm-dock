from flag_metadata import (
    BENCHMARK_ENGINES,
    SERVICE_ENGINES,
    SERVICE_NAME_PREFIXES,
)
from metrics_catalogue import METRICS_ENGINES

DEFAULT_PATH_PLACEHOLDER = "/hf-cache/… or /local-models/…"
DIRECTORY_PLACEHOLDER = "/hf-cache/… or /local-models/… (model directory)"

# How each engine is presented in the UI. Everything else in the catalogue is
# derived from the engine tables; a test requires one row per service engine.
ENGINE_PRESENTATION = {
    "llamacpp": {"label": "llama.cpp", "hint": "GGUF file", "model_source": "file", "gguf_picker": True},
    "ik_llamacpp": {"label": "ik llama.cpp", "hint": "GGUF file (ik fork)", "model_source": "file", "gguf_picker": True},
    "vllm": {"label": "vLLM", "hint": "HuggingFace org/name", "model_source": "repo", "gguf_picker": False},
    "ds4": {"label": "ds4", "hint": "DeepSeek V4 Flash file", "model_source": "file", "gguf_picker": True},
    "tabbyapi": {
        "label": "TabbyAPI", "hint": "EXL3 model directory", "model_source": "directory",
        "gguf_picker": False, "placeholder": DIRECTORY_PLACEHOLDER,
    },
    "ninfer": {"label": "NInfer", "hint": ".ninfer artifact", "model_source": "file", "gguf_picker": False},
    "sglang": {
        "label": "SGLang / Pennyroyal", "hint": "RTX PRO 6000 model directory", "model_source": "directory",
        "gguf_picker": False, "placeholder": DIRECTORY_PLACEHOLDER,
    },
    "maya": {
        "label": "Project Maya", "hint": "Maya pack directory", "model_source": "directory",
        "gguf_picker": False, "placeholder": "~/.cache/maya/<model>/<pack> (absolute host path)",
    },
}


def build_catalogue() -> list[dict]:
    return [
        {
            "type": engine,
            "label": ENGINE_PRESENTATION[engine]["label"],
            "hint": ENGINE_PRESENTATION[engine]["hint"],
            "model_source": ENGINE_PRESENTATION[engine]["model_source"],
            "placeholder": ENGINE_PRESENTATION[engine].get("placeholder", DEFAULT_PATH_PLACEHOLDER),
            "gguf_picker": ENGINE_PRESENTATION[engine]["gguf_picker"],
            "metrics": engine in METRICS_ENGINES,
            "benchmark": engine in BENCHMARK_ENGINES,
            "name_prefix": SERVICE_NAME_PREFIXES.get(engine, engine),
        }
        for engine in SERVICE_ENGINES
    ]
