#!/bin/bash

# GLM-4.7-Flash with vLLM from source + transformers from git
# See: https://huggingface.co/zai-org/GLM-4.7-Flash

docker run --rm -it \
    --gpus all \
    --ipc host \
    -p 8000:8000 \
    -e HF_HUB_OFFLINE=1 \
    -v ${HOME}/.cache/huggingface:/root/.cache/huggingface:ro \
    -v ${HOME}/.cache/torch:/root/.cache/torch \
    -v ${HOME}/.triton:/root/.triton \
    llm-dock-vllm \
    --model zai-org/GLM-4.7-Flash \
    --host 0.0.0.0 \
    --port 8000 \
    --trust-remote-code \
    --served-model-name glm47next \
    --api-key llm-dock \
    --tensor-parallel-size 1 \
    --max-model-len 16384
