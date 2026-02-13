#!/bin/bash
#
# vLLM Benchmark Script
# Runs online serving benchmark against a running vLLM container.
#
# Usage: ./bench.sh <container-name> [options]
# Example: ./bench.sh vllm-glm-4-7-flash-nvfp4
#          ./bench.sh vllm-glm-4-7-flash-nvfp4 --num-prompts 50 --input-len 512

set -e

CONTAINER="${1:?Usage: $0 <container-name> [extra bench args...]}"
shift

# Extract API key from container command args
API_KEY=$(docker inspect "${CONTAINER}" --format '{{join .Args " "}}' | grep -oP '(?<=--api-key )\S+')
if [ -z "${API_KEY}" ]; then
    echo "Error: Could not extract API key from container ${CONTAINER}"
    exit 1
fi

# Defaults
NUM_PROMPTS="${NUM_PROMPTS:-20}"
INPUT_LEN="${INPUT_LEN:-256}"
OUTPUT_LEN="${OUTPUT_LEN:-128}"
REQUEST_RATE="${REQUEST_RATE:-4}"

echo "=========================================="
echo "  vLLM Online Serving Benchmark"
echo "=========================================="
echo ""
echo "  Container:    ${CONTAINER}"
echo "  Num prompts:  ${NUM_PROMPTS}"
echo "  Input len:    ${INPUT_LEN}"
echo "  Output len:   ${OUTPUT_LEN}"
echo "  Request rate: ${REQUEST_RATE} req/s"
echo ""

docker exec "${CONTAINER}" vllm bench serve \
    --backend openai-chat \
    --endpoint /v1/chat/completions \
    --base-url http://localhost:8000 \
    --header "Authorization=Bearer ${API_KEY}" \
    --dataset-name random \
    --random-input-len "${INPUT_LEN}" \
    --random-output-len "${OUTPUT_LEN}" \
    --num-prompts "${NUM_PROMPTS}" \
    --request-rate "${REQUEST_RATE}" \
    "$@"
