FROM nvidia/cuda:12.9.0-devel-ubuntu22.04

# Build metadata
ARG BUILD_DATE
ARG BUILD_COMMIT
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}" \
      org.llm-dock.engine="ik_llama.cpp"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential \
    ninja-build \
    wget \
    git \
    pkg-config \
    python3-pip \
    libssl-dev \
    libcurl4-openssl-dev \
    libomp-dev \
 && rm -rf /var/lib/apt/lists/*

# NOT apt's cmake: Ubuntu 22.04 ships 3.22, which has no compile flags for the
# CUDA20 dialect that CMAKE_CXX_STANDARD 20 propagates to the ggml CUDA target
# ("requires the language dialect CUDA20 ... but CMake does not know the compile
# flags"). pip gives a current cmake in /usr/local/bin, ahead of /usr/bin on PATH.
# Upstream's own .devops/llama-server-cuda.Dockerfile does the same.
RUN pip3 install --no-cache-dir cmake && cmake --version

# Which upstream revision to build. Override with --build-arg IK_REF=<sha|tag>
# to pin a known-good commit instead of tracking main.
ARG IK_REF=main
RUN git clone https://github.com/ikawrakow/ik_llama.cpp.git /ik_llama.cpp \
 && cd /ik_llama.cpp \
 && git checkout "${IK_REF}"

WORKDIR /ik_llama.cpp

# Make the CUDA stub library visible as libcuda.so.1 for the linker
RUN ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 && \
    echo "/usr/local/cuda/lib64/stubs" > /etc/ld.so.conf.d/cuda-stubs.conf && \
    ldconfig

# 120 = Blackwell (RTX PRO 6000). Override with --build-arg CUDA_ARCH=<sm>
ARG CUDA_ARCH=120
# -march=native tunes for the BUILD host's CPU (Zen 3 -> AVX2). Set to OFF if
# the image must run on a different machine than it was built on.
ARG GGML_NATIVE=ON

# -mcmodel=large is required: ik_llama.cpp's iqk kernels carry static lookup
# tables that overflow the default code model at link time.
RUN cmake -B build -G Ninja \
   -DGGML_CUDA=ON \
   -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH} \
   -DGGML_NATIVE=${GGML_NATIVE} \
   -DGGML_IQK_MUL_MAT=ON \
   -DGGML_IQK_FLASH_ATTENTION=ON \
   -DGGML_CUDA_USE_GRAPHS=ON \
   -DGGML_OPENMP=ON \
   -DLLAMA_BUILD_SERVER=ON \
   -DLLAMA_BUILD_EXAMPLES=ON \
   -DLLAMA_BUILD_TESTS=OFF \
   -DBUILD_SHARED_LIBS=ON \
   -DCMAKE_C_FLAGS="-fPIC -mcmodel=large" \
   -DCMAKE_CXX_FLAGS="-fPIC -mcmodel=large" \
   -DCMAKE_BUILD_TYPE=Release

# EXAMPLES must be ON above: in ik_llama.cpp the server still lives under
# examples/ (not tools/ as in modern llama.cpp), and add_subdirectory(examples)
# is gated on LLAMA_BUILD_EXAMPLES -- with it OFF, LLAMA_BUILD_SERVER is dead
# code and the build silently produces no llama-server. Building only the
# llama-server target keeps the other examples from being compiled.
RUN cmake --build build --config Release --target llama-server -j$(nproc) \
 && test -x /ik_llama.cpp/build/bin/llama-server

# Drop-in compatibility with dashboard/templates/ik_llamacpp.j2, which uses the
# same /llama.cpp/build/bin/llama-server path as llamacpp.j2. Pointing the
# expected path at the ik build means a service only switches its `image:`.
RUN mkdir -p /llama.cpp/build && ln -s /ik_llama.cpp/build/bin /llama.cpp/build/bin

# Clean up stubs from linker path (runtime will use real drivers)
RUN rm /etc/ld.so.conf.d/cuda-stubs.conf && ldconfig
