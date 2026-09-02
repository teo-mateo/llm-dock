# LLM-Dock — TabbyAPI (ExLlamaV3 backend) image
#
# ExLlamaV3 itself is a *library* — it has no HTTP server. TabbyAPI is its official
# OpenAI-compatible server, so this runner is "TabbyAPI, with exllamav3 as backend".
#
# This is a thin, labelled re-pin of the upstream image (same pattern as
# vllm/Dockerfile: FROM upstream + metadata + a hardened entrypoint), because
# TabbyAPI is a rolling release with no git tags and no GitHub releases — `latest`
# is the only moving tag, so a digest is the only reproducible reference.
#
# Upstream image facts: nvidia/cuda:12.8.1-runtime + python3.12/3.13 venv at
# /opt/venv, WORKDIR /app, torch+exllamav3 installed from the [cu12] extra
# (exllamav3 v1.4.5+cu128.torch2.9.0 as of the pin below), ENTRYPOINT ["python3"],
# CMD ["main.py","--host","0.0.0.0"]. curl is installed, so HEALTHCHECK works.
#
# To re-pin: resolve the current digest of :latest, replace it in BOTH ARG lines
# below (an ARG declared before FROM does not cross the FROM boundary), then
# rebuild and re-verify the service template — TabbyAPI's CLI surface is
# generated from its pydantic config model, so an upstream release can add or
# rename flags that tabbyapi.j2 passes.
#
#   TOK=$(curl -s "https://ghcr.io/token?scope=repository:theroyallab/tabbyapi:pull" \
#         | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
#   curl -sI -H "Authorization: Bearer $TOK" \
#        -H "Accept: application/vnd.oci.image.index.v1+json" \
#        https://ghcr.io/v2/theroyallab/tabbyapi/manifests/latest \
#     | grep -i docker-content-digest

# Base image, digest-pinned. Override for a CUDA 13 host with
#   --build-arg TABBYAPI_REF=ghcr.io/theroyallab/tabbyapi@<cu13 digest>
ARG TABBYAPI_REF=ghcr.io/theroyallab/tabbyapi@sha256:3a1418a7a2828fc405d592b54107cc3b9f6fef78235022494eaa7e9114809f67
FROM ${TABBYAPI_REF}

# Re-declared so the labels below can see it (keep in sync with the ARG above FROM).
ARG TABBYAPI_REF=ghcr.io/theroyallab/tabbyapi@sha256:3a1418a7a2828fc405d592b54107cc3b9f6fef78235022494eaa7e9114809f67

# Build metadata
ARG BUILD_DATE
ARG BUILD_COMMIT
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}" \
      org.llm-dock.tabbyapi.base="${TABBYAPI_REF}" \
      org.llm-dock.tabbyapi.upstream="ghcr.io/theroyallab/tabbyapi:latest"

# Record the resolved dependency set (exllamav3 and torch are what actually
# determine model-format and GPU-arch support) into the image, so
# `docker run --rm --entrypoint cat llm-dock-tabbyapi /opt/llm-dock.txt` reports
# what a built image really contains. importlib.metadata reads package metadata
# only — no CUDA context, so this runs during build without a GPU.
RUN set -eux; \
    { \
      echo "base=${TABBYAPI_REF}"; \
      echo "exllamav3=$(python3 -c 'from importlib.metadata import version; print(version("exllamav3"))')"; \
      echo "torch=$(python3 -c 'import torch; print(torch.__version__)')"; \
      echo "cuda=cu$(python3 -c 'import torch; print(torch.version.cuda)')"; \
    } > /opt/llm-dock.txt; \
    cat /opt/llm-dock.txt

# Triton JIT-compiles its CUDA driver helper (cuda_utils.c, which includes
# <Python.h>) at the first kernel launch. The upstream image's python3.12 venv
# ships no dev headers, so every Triton path — exllamav3's paged-attention
# kernels and flash-linear-attention — would crash at launch or silently fall
# back to CPU. gcc/build-essential are already present; this is the one
# missing piece. Do NOT remove: any exllamav3 load triggers it.
RUN apt-get update && apt-get install -y --no-install-recommends python3.12-dev \
    && rm -rf /var/lib/apt/lists/*

# llm-dock convention: model servers listen on 8000 inside the container
# (docker_utils.py maps any non-llama.cpp engine to 8000 for Open WebUI
# registration). TabbyAPI's own default is 5000, so the port is set here as the
# image default and again by the compose template.
EXPOSE 8000

# /health is unauthenticated and answers 503 until a model is loaded, which
# makes it a true readiness signal. llm-dock's dashboard doesn't read Docker
# health yet — this is for `docker ps` / `docker inspect` and future use.
# start-period covers weight load + CUDA graph warmup.
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${TABBYAPI_HEALTH_PORT:-8000}/health" || exit 1

# Entrypoint is `python3 main.py` so the compose template's `command:` carries
# only llm-dock-managed flags, like the ds4 template. TabbyAPI's CLI args are
# config.yml *overrides* with dashes (--max-seq-len, --cache-mode), and every
# argument — including booleans — takes a value: `--vision True`, never a bare
# `--vision`.
WORKDIR /app
ENTRYPOINT ["python3", "main.py"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
