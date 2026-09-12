FROM nvidia/cuda:12.9.0-devel-ubuntu22.04

# Build metadata
ARG BUILD_DATE
ARG BUILD_COMMIT
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    wget \
    git \
    pkg-config \
    libssl-dev \
    libcurl4-openssl-dev \
    libomp-dev

# Make the CUDA stub library visible as libcuda.so.1 for the linker
#RUN ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1

RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /llama.cpp

WORKDIR /llama.cpp

# Create symlink and add stubs to linker path
RUN ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 && \
    echo "/usr/local/cuda/lib64/stubs" > /etc/ld.so.conf.d/cuda-stubs.conf && \
    ldconfig

# 120 = Blackwell (RTX PRO 6000). Override with --build-arg CUDA_ARCH=<arch>;
# build-llamacpp.sh passes the arch it detected, so a committed value here only has to
# be right for a bare `docker build ./llama.cpp/`.
ARG CUDA_ARCH=120
RUN cmake -B build \
   -DGGML_CUDA=ON \
   -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH} \
   -DLLAMA_BUILD_EXAMPLES=OFF \
   -DLLAMA_BUILD_TESTS=OFF \
   -DCMAKE_BUILD_TYPE=Release

RUN cmake --build build --config Release -j$(nproc)

# Clean up stubs from linker path (runtime will use real drivers)
RUN rm /etc/ld.so.conf.d/cuda-stubs.conf && ldconfig