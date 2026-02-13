FROM vllm/vllm-openai:v0.15.1

# Build metadata
ARG BUILD_DATE
ARG BUILD_COMMIT
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}"

# Install transformers from git for newest model support
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install git+https://github.com/huggingface/transformers.git

# Verify installations
RUN python3 -c "from importlib.metadata import version; print(f'vLLM version: {version(\"vllm\")}')" && \
    python3 -c "import transformers; print(f'Transformers version: {transformers.__version__}')"

EXPOSE 8000

ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]
