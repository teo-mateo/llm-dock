# LLM-Dock — DwarfStar 4 (ds4) image
#
# ds4 is antirez's native inference engine tailored for DeepSeek V4 Flash.
# Built from source (no upstream image exists). Multi-stage: compile with the
# full CUDA devel toolkit, ship only the binaries on the CUDA runtime image.

# ---- Build stage -----------------------------------------------------------
FROM nvidia/cuda:12.9.0-devel-ubuntu24.04 AS builder

# Pinned to the commit verified to build on this host (== origin/main at the
# time of writing, no local diffs).
ARG DS4_COMMIT=e34a8086693ba7ca5cfabd2b9028ee52f0bfac2e

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/antirez/ds4.git /src && \
    git -C /src checkout "${DS4_COMMIT}"

# Build with an explicit GPU arch instead of `make cuda-generic`: the generic
# target uses -arch=native, which requires the GPU to be visible to nvcc — it
# is NOT during `docker build`. sm_120 = RTX PRO 6000 Blackwell.
RUN make -C /src cuda CUDA_ARCH=sm_120

# ---- Runtime stage ---------------------------------------------------------
# The runtime image already ships libcudart + libcublas, the only runtime libs
# the Makefile links. ds4_web.c uses raw POSIX sockets, so no libcurl/OpenSSL.
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04

# Build metadata
ARG BUILD_DATE
ARG BUILD_COMMIT
ARG DS4_COMMIT=e34a8086693ba7ca5cfabd2b9028ee52f0bfac2e
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}" \
      org.llm-dock.ds4.commit="${DS4_COMMIT}"

COPY --from=builder \
     /src/ds4 /src/ds4-server /src/ds4-bench /src/ds4-eval /src/ds4-agent \
     /usr/local/bin/

EXPOSE 8000

# Phase 2's ds4.j2 supplies the command args (-m <gguf> --ctx … --warm-weights …).
ENTRYPOINT ["ds4-server"]
