FROM nvcr.io/nvidia/pytorch:25.05-py3

# Build metadata
ARG BUILD_DATE
ARG BUILD_COMMIT
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}"

# Set CUDA architecture for Blackwell (sm_120)
ENV TORCH_CUDA_ARCH_LIST="12.0 12.1"

# Install build dependencies
RUN apt-get update
RUN apt-get install -y git
RUN apt-get install -y cmake
RUN apt-get install -y ninja-build
RUN rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install/upgrade build dependencies (disable NGC constraints)
RUN PIP_CONSTRAINT="" pip install --upgrade setuptools_scm "packaging>=24.2" "protobuf>=6.30.0"

# Clone vLLM and install with precompiled CUDA binaries
RUN git clone https://github.com/vllm-project/vllm.git && \
    cd vllm && \
    PIP_CONSTRAINT="" VLLM_USE_PRECOMPILED=1 pip install -e .

# Install transformers from git AFTER vllm (vllm may overwrite with stable version)
RUN pip install git+https://github.com/huggingface/transformers.git

# Verify installations
RUN python3 -c "import vllm; print(f'vLLM version: {vllm.__version__}')" && \
    python3 -c "import transformers; print(f'Transformers version: {transformers.__version__}')"

EXPOSE 8000

ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]
