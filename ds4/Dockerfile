# LLM-Dock — DwarfStar 4 (ds4) image
#
# ds4 is antirez's native inference engine tailored for DeepSeek V4 Flash.
# Built from source (no upstream image exists). Multi-stage: compile with the
# full CUDA devel toolkit, ship only the binaries on the CUDA runtime image.

# ---- Build stage -----------------------------------------------------------
FROM nvidia/cuda:12.9.0-devel-ubuntu24.04 AS builder

# Pinned to the commit verified to build on this host (== origin/main at the
# time of writing, no local diffs).
ARG DS4_COMMIT=54b36ed9ba42da31b24f2d1a5feb075c2475dbb1

# Target GPU arch. Defaults to sm_120 (RTX PRO 6000 Blackwell); override via
# build-ds4.sh for other GPUs. NOT cuda-generic/-arch=native, which needs the
# GPU visible to nvcc — it isn't during `docker build`.
# Note: ds4's Makefile compiles with -march=native, so binaries are also tuned
# to the build host's CPU. Intentional here (image is built and run on the same
# machine); rebuild on the target host if that ever changes.
ARG CUDA_ARCH=sm_120

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/antirez/ds4.git /src && \
    git -C /src checkout "${DS4_COMMIT}"

# Upstream 54b36ed uses FLT_MAX in ds4_cuda.cu without including float.h;
# nvcc 12.9 on ubuntu24.04 doesn't pull it in transitively. Drop this once
# fixed upstream.
RUN sed -i '1i #include <float.h>' /src/ds4_cuda.cu

# Upstream 54b36ed regression: ds4_gpu_set_model_map_range host-registers the
# whole model first (g_model_registered=1), which makes cuda_model_copy_chunked
# early-return before copying — so DS4_CUDA_COPY_MODEL_CHUNKED can never reach
# VRAM residency and decode runs at PCIe zero-copy speed (~0.7 t/s on this
# host, no HMM). Let the chunked copy proceed when only the host registration
# exists; on copy failure it still falls back to the registered zero-copy
# mapping. Drop once fixed upstream.
RUN sed -i '/^static int cuda_model_copy_chunked/,+10 s/if (g_model_device_owned || g_model_registered) return 1;/if (g_model_device_owned) return 1;/' /src/ds4_cuda.cu && \
    grep -A9 '^static int cuda_model_copy_chunked' /src/ds4_cuda.cu | grep -q 'if (g_model_device_owned) return 1;'

RUN make -C /src cuda CUDA_ARCH="${CUDA_ARCH}"

# ---- Runtime stage ---------------------------------------------------------
# The runtime image already ships libcudart + libcublas, the only runtime libs
# the Makefile links. ds4_web.c uses raw POSIX sockets, so no libcurl/OpenSSL.
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04

# Build metadata
ARG BUILD_DATE
ARG BUILD_COMMIT
ARG DS4_COMMIT=54b36ed9ba42da31b24f2d1a5feb075c2475dbb1
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}" \
      org.llm-dock.ds4.commit="${DS4_COMMIT}"

COPY --from=builder \
     /src/ds4 /src/ds4-server /src/ds4-bench /src/ds4-eval /src/ds4-agent \
     /usr/local/bin/

EXPOSE 8000

# Phase 2's ds4.j2 supplies the command args (-m <gguf> --ctx … --warm-weights …).
ENTRYPOINT ["ds4-server"]
