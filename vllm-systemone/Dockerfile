ARG VLLM_SYSTEMONE_BASE=llm-dock-vllm:cu129-580
FROM ${VLLM_SYSTEMONE_BASE}

ARG BUILD_DATE
ARG BUILD_COMMIT
ARG OPENJEV_COMMIT=5ec9e5fd2f80a6fff386779b1e5ac7e389971889
ARG SHIM_SHA256=81a22f1b1b8912a465059207ef9f60b7c6c16b4de6372305d867efbe38a1987a
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}" \
      org.llm-dock.openjev.commit="${OPENJEV_COMMIT}" \
      org.llm-dock.openjev.shim-sha256="${SHIM_SHA256}"

RUN mkdir -p /opt/systemone && \
    python3 -c "import urllib.request; urllib.request.urlretrieve('https://huggingface.co/openjev/openjev/resolve/${OPENJEV_COMMIT}/helper/shim.py', '/opt/systemone/shim.py')" && \
    echo "${SHIM_SHA256}  /opt/systemone/shim.py" | sha256sum -c -

COPY systemone /opt/systemone/systemone
ENV PYTHONPATH=/opt/systemone

RUN python3 -c "import systemone.middleware, systemone.launcher"
