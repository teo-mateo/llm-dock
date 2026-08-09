---
name: check-upstream
description: Check whether each LLM inference runner used by llm-dock (llama.cpp, vllm, ds4, ik_llama) has upstream changes worth pulling/rebuilding. Use when asked to check for updates, compare the built image against upstream, or decide whether to rebuild a runner image.
---

# Check Upstream Runner Changes

llm-dock builds four inference runner images from source. Each has a
different pinning strategy, so "check upstream" differs per runner. This
skill walks the whole set and tells you how far behind each built image is,
what changed, and whether a rebuild is warranted.

## Runners at a glance

| Runner | Upstream repo | Image | Build script | Pinning |
|--------|---------------|-------|--------------|---------|
| llama.cpp | `ggml-org/llama.cpp` | `llm-dock-llamacpp` | `build-llamacpp.sh` | tracks latest (fresh `--depth 1` clone) |
| vllm | `vllm-project/vllm` | `llm-dock-vllm` | `build-vllm.sh` | pinned by base image **release tag** |
| ds4 | `antirez/ds4` | `llm-dock-ds4` | `build-ds4.sh` | pinned by **commit** + 2 local patches |
| ik_llama | `ikawrakow/ik_llama.cpp` | `llm-dock-ik-llamacpp` | none (manual `docker build`) | tracks latest (clone of `main`) |

All four upstream repos have local checkouts under `/github/`:

- `/github/ggml-org/llama.cpp`
- `/github/vllm-project/vllm`
- `/github/antirez/ds4`
- `/github/ikawrakow/ik_llama.cpp`

## General workflow

For each runner:

1. **Find what the built image actually contains** (the runner commit — see
   per-runner notes below; the `org.llm-dock.build.commit` label is the
   *llm-dock* commit, not the runner's).
2. **Fetch upstream** and compare against that commit.
3. **Read the change log** in the gap and assess whether it's worth a rebuild.
4. Report: how far behind, notable changes, rebuild recommendation.

Fetch upstream without disturbing a dirty working tree:

```bash
cd /github/<org>/<repo>
git fetch origin <branch>
```

Count commits behind and list them:

```bash
git rev-list --count <image_commit>..origin/<branch>   # how far behind
git log --oneline <image_commit>..origin/<branch>      # what changed
```

## llama.cpp

- **Dockerfile:** `llama.cpp/Dockerfile` — `git clone --depth 1 https://github.com/ggml-org/llama.cpp.git` at build time, so the image always tracks latest. There is no pinned version.
- **Find the runner commit in the image:** the label only records the llm-dock commit, so query a running container's cloned repo:

  ```bash
  docker exec <running-llamacpp-container> bash -c 'cd /llama.cpp && git log -1 --format="%h %ad %s"'
  ```

  If no container is up, `docker run --rm --entrypoint bash llm-dock-llamacpp:latest -c 'cd /llama.cpp && git log -1'`.
- **Compare:** the local checkout's `master` is often stale (may be on a PR branch — check `git branch -vv`). Use the image's commit vs `origin/master`:

  ```bash
  cd /github/ggml-org/llama.cpp
  git fetch origin master
  git log --oneline <image_commit>..origin/master
  ```

- **Rebuild:** `./build-llamacpp.sh` (prompts for CUDA arch; detects Blackwell as `120`). A fresh clone means the rebuild always picks up the latest.

## vllm

- **Dockerfile:** `vllm/Dockerfile` — `FROM vllm/vllm-openai:v0.24.0-cu129` (pinned **release tag**), then `pip install git+https://github.com/huggingface/transformers.git` (unpinned transformers).
- **Pinning:** the vllm version comes from the base image tag, *not* a commit. The image labels carry `ai.vllm.build.commit` (upstream commit the release was built from) and `ai.vllm.image.tag`.
- **Check latest release** (this is what matters, not `main`):

  ```bash
  cd /github/vllm-project/vllm
  git ls-remote --tags origin | grep -oE 'refs/tags/v[0-9.]+$' | sed 's/refs\/tags\///' | sort -V | uniq | tail
  ```

  Compare against the tag in `vllm/Dockerfile`. To upgrade, bump the `FROM` tag, then rebuild.
- **Rebuild:** `./build-vllm.sh`. Note the base image is pulled from Docker Hub, so the build needs network access to fetch the new tag.

## ds4

- **Dockerfile:** `ds4/Dockerfile` — pinned `ARG DS4_COMMIT=<sha>` (was `== origin/main` at time of writing), plus **two local `sed` patches** applied at build time:
  1. `#include <float.h>` prepended to `ds4_cuda.cu` (FLT_MAX fix).
  2. `g_model_device_owned || g_model_registered` → `g_model_device_owned` in `cuda_model_copy_chunked` (chunked-copy fix).
- **Find the runner commit:** the label `org.llm-dock.ds4.commit` *does* record the ds4 commit:

  ```bash
  docker inspect llm-dock-ds4:latest --format '{{ index .Config.Labels "org.llm-dock.ds4.commit" }}'
  ```

- **Compare:**

  ```bash
  cd /github/antirez/ds4
  git fetch origin main
  git log --oneline <pinned_commit>..origin/main
  ```

- **Check if the local patches are still needed** — this is the key gotcha for ds4:
  - `float.h`: **now fixed upstream** (commit `727836a` "Include float.h for CUDA FLT_MAX"). Can be dropped when bumping past that commit.
  - chunked-copy fix: **still NOT upstream** — `ds4_cuda.cu` still has `if (g_model_device_owned || g_model_registered) return 1;`. Verify before bumping:

    ```bash
    git show origin/main:ds4_cuda.cu | grep -n "g_model_device_owned || g_model_registered"
    ```

  If the fix is now upstream, remove the corresponding `sed` from the Dockerfile; if not, keep it.
- **Rebuild:** `./build-ds4.sh` (`CUDA_ARCH=sm_120` default; override for other GPUs).

## ik_llama

- **Dockerfile:** `ik_llama.cpp/Dockerfile` — `ARG IK_REF=main` (unpinned, tracks `main`), clones `https://github.com/ikawrakow/ik_llama.cpp.git` at build time.
- **Find the runner commit:** no label records it (`org.llm-dock.build.commit` is empty). Query a running container:

  ```bash
  docker exec <running-ik-container> bash -c 'cd /ik_llama.cpp && git log -1 --format="%h %ad %s"'
  ```

- **Compare:**

  ```bash
  cd /github/ikawrakow/ik_llama.cpp
  git fetch origin main
  git log --oneline <image_commit>..origin/main
  ```

- **Rebuild:** there is **no build script** — build manually:

  ```bash
  cd /github/teo-mateo/llm-dock
  docker build -t llm-dock-ik-llamacpp ./ik_llama.cpp/
  ```

  (Override `IK_REF` to pin a known-good commit: `--build-arg IK_REF=<sha|tag>`.)

## Gotchas

- **`org.llm-dock.build.commit` is the llm-dock commit, not the runner's.** Only ds4 (`org.llm-dock.ds4.commit`) and vllm (`ai.vllm.build.commit`) record their upstream commit in labels. For llama.cpp and ik_llama you must query the git clone inside a running container.
- **llama.cpp and ik_llama track latest** — a rebuild always pulls the newest upstream. The question is only whether the delta since the last build is worth 10–15 min of compile time.
- **vllm is pinned by release tag, not `main`.** `main` being far ahead is irrelevant; check the latest release tag instead.
- **ds4 is the only one with local patches.** When bumping the pinned commit, check both patches against upstream and drop any that are now fixed.
- **Local checkouts can be on unrelated branches.** `/github/ggml-org/llama.cpp` was on a PR branch (`pr-22607`) with uncommitted files — don't assume the checkout's HEAD reflects what the image was built from, and don't touch a dirty working tree.
- **`docker run` may be blocked** in this environment; prefer `docker exec` on a running container, or inspect labels.
