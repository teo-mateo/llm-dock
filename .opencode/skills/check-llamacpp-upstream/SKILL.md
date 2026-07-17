---
name: check-llamacpp-upstream
description: Check llama.cpp Docker image version against upstream, compare commits, and summarize relevant changes for rebuilding
metadata:
  audience: maintainers
  workflow: docker-rebuild
---

## What I do

Compare the llama.cpp version baked into the `llm-dock-llamacpp` Docker image against the latest `ggml-org/llama.cpp` upstream, then summarize changes relevant to this project's use of llama.cpp (server flags, CUDA performance, model support, bug fixes).

## When to use me

Use this when asking to check if llama.cpp has new changes, whether the Docker image is outdated, or before rebuilding the `llm-dock-llamacpp` image.

## Prerequisites

- The `llm-dock-llamacpp` Docker image exists locally
- A local clone of `ggml-org/llama.cpp` is available (default: `/github/ggml-org/llama.cpp`)
- Network access to fetch from upstream

## Step-by-step workflow

### 1. Extract image build version

Get the llama.cpp commit hash baked into the Docker image by running git inside the container:

```bash
docker run --rm llm-dock-llamacpp git -C /llama.cpp log --oneline -1
```

Also grab build metadata from Docker labels:

```bash
docker inspect llm-dock-llamacpp | python3 -c "import json,sys; d=json.load(sys.stdin)[0]; print('Build date:', d.get('Config',{}).get('Labels',{}).get('org.llm-dock.build.date','N/A')); print('Build commit:', d.get('Config',{}).get('Labels',{}).get('org.llm-dock.build.commit','N/A'))"
```

Note: the `org.llm-dock.build.commit` label is the **llm-dock** repo commit at build time, not the llama.cpp commit. Use the container git command for the actual llama.cpp version.

### 2. Fetch latest upstream

```bash
cd /github/ggml-org/llama.cpp && git fetch origin master
```

### 3. Count and list commits ahead

```bash
# Count commits between image version and upstream
git log --oneline <image-commit>..origin/master | wc -l

# List all commits
git log --oneline <image-commit>..origin/master
```

If the commit is not in local history (shallow clone / feature branch), fetch it first:

```bash
git fetch origin <image-commit>
```

### 4. Filter for relevant changes

Focus on these categories:

**New server flags** — affects `dashboard/flag_metadata.py` and service configuration:
```bash
git log --oneline <image-commit>..origin/master --grep="add.*option\|new.*flag\|add.*flag\|cors\|reasoning"
```

**CUDA performance** — affects build quality for the host GPU (check `build-llamacpp.sh` for CUDA arch):
```bash
git log --oneline <image-commit>..origin/master --grep="CUDA\|cuda\|flash attention\|FA\|MMQ\|NVFP4\|fp4"
```

**New model support** — may require new flags or parameters:
```bash
git log --oneline <image-commit>..origin/master --grep="DeepSeek\|deepseek\|model.*support\|architecture"
```

**Speculative decoding** — draft model features:
```bash
git log --oneline <image-commit>..origin/master --grep="spec\|speculative\|draft\|DFlash"
```

**Server fixes** — stability and API compatibility:
```bash
git log --oneline <image-commit>..origin/master -- "servers/" "common/arg.cpp" | head -30
```

**Vendor updates** — dependency changes:
```bash
git log --oneline <image-commit>..origin/master --grep="vendor\|cpp-httplib\|BoringSSL"
```

### 5. Cross-reference with llm-dock

Check `dashboard/flag_metadata.py` to see which flags are already exposed in the dashboard. Any new `--flag-name` patterns from llama.cpp that aren't in `LLAMACPP_LLAMA_SERVER_FLAGS` are candidates for adding to the dashboard.

Check `llama.cpp/Dockerfile` to understand the build process:
- The Dockerfile uses `git clone --depth 1` so it always pulls the latest upstream
- CUDA architecture is set dynamically by `build-llamacpp.sh` via sed
- Build metadata (date, llm-dock commit) is stored as Docker labels

### 6. Summarize findings

Present results grouped by:
1. Number of commits ahead
2. New flags (with impact on dashboard)
3. CUDA/GPU performance changes (tailored to host GPU)
4. New model architecture support
5. Server stability fixes
6. Dependency updates
7. Recommendation to rebuild

## Key files reference

| File | Purpose |
|------|---------|
| `llama.cpp/Dockerfile` | Docker image definition, clones latest llama.cpp |
| `build-llamacpp.sh` | Interactive builder, detects GPU arch, runs docker build |
| `dashboard/flag_metadata.py` | Exposed server flags and their descriptions |
| `services.json` | Running service definitions with per-service params |
