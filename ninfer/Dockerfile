# LLM-Dock — NInfer image
#
# NInfer is Neroued's from-scratch C++/CUDA engine for explicitly registered
# Qwen artifacts (a single `.ninfer` file carries weights, tokenizer, chat
# template and media frontend). Built from source: no upstream image exists.
#
# Upstream requires CUDA Toolkit >= 13.1. This host's driver (575.x) tops out at
# CUDA 12.9, so the build pins the commit below and applies
# ninfer-cu129-port.patch, which moves the four kernel families whose staged
# shared memory exceeds the 48 KiB static cap that CUDA <= 12.9 still enforces
# onto the dynamic-shared path (CUDA 13 raised that cap). The patch is a plain
# `git diff` of the pinned tree; bump both together. A second patch,
# ninfer-metrics.patch, adds the authed GET /metrics route from RuntimeStats
# and MemorySummary snapshots (R5 of docs/plans/ninfer-metrics.md): it dies
# when upstream ships a stats endpoint of its own, so its retirement is
# tracked separately in .pi/skills/check-upstream/SKILL.md.
#
# Multi-stage: compile with the full CUDA devel toolkit, ship only the binaries
# on the CUDA runtime image.

# ---- Build stage -----------------------------------------------------------
FROM nvidia/cuda:12.9.0-devel-ubuntu24.04 AS builder

ARG NINFER_COMMIT=d49296868dcc17bd478ec185f0d3a801bcc0bf56

# Ubuntu 24.04 satisfies NInfer's remaining dependency gates from its own
# archive: ffmpeg 6.1 -> libavformat 60 / libavcodec 60 / libavutil 58 /
# libswscale 7, and libcurl 8.5 >= 7.85. No source builds needed.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build git ca-certificates pkg-config \
        libavformat-dev libavcodec-dev libavutil-dev libswscale-dev libcurl4-openssl-dev && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/Neroued/ninfer.git /src && \
    git -C /src checkout "${NINFER_COMMIT}"

COPY ninfer-cu129-port.patch /src/ninfer-cu129-port.patch
RUN git -C /src apply --verbose /src/ninfer-cu129-port.patch
COPY ninfer-metrics.patch /src/ninfer-metrics.patch
RUN git -C /src apply --verbose /src/ninfer-metrics.patch

# CMake itself rejects any CUDA architecture other than sm_120a, which is what
# this host's GPU (RTX PRO 6000 Blackwell) and the RTX 5090 both are.
RUN cmake -S /src -B /src/build -G Ninja -DCMAKE_BUILD_TYPE=Release && \
    cmake --build /src/build -j"$(nproc)"

# ---- Runtime stage ---------------------------------------------------------
# The runtime image already ships libcudart; media decode needs the FFmpeg
# runtime libraries and the HTTP gateway needs libcurl. libcuda comes from the
# container runtime.
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04

ARG BUILD_DATE
ARG BUILD_COMMIT
ARG NINFER_COMMIT=d49296868dcc17bd478ec185f0d3a801bcc0bf56
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}" \
      org.llm-dock.ninfer.commit="${NINFER_COMMIT}"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libavformat60 libavcodec60 libavutil58 libswscale7 libcurl4 && \
    rm -rf /var/lib/apt/lists/*

# Each NInfer binary is ~460 MiB (the CUDA kernels plus a static FFmpeg), so the
# image ships the serving binary and the one-shot CLI, and leaves the offline
# perplexity tool out.
COPY --from=builder \
     /src/build/apps/ninfer-serve /src/build/apps/ninfer \
     /usr/local/bin/

EXPOSE 8080

# ninfer.j2 supplies the artifact path and flags (`ninfer-serve <model.ninfer> …`).
ENTRYPOINT ["ninfer-serve"]
