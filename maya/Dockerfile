# Project Maya (github.com/mw00/project-maya) for llm-dock.
#
# Built by ../build-maya.sh, which extracts `git archive <MAYA_COMMIT>` of a
# local Maya checkout and passes it as the `maya-src` named build context, so
# the image is exactly that commit (local, unpushed commits included) and never
# the checkout's working tree, build dirs or venv.
#
# CUDA 12.9: the host driver (575.x) tops out there; the native build that this
# image replaces was compiled with /usr/local/cuda-12.9 for sm_120.
ARG CUDA_VERSION=12.9.1

FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential ca-certificates python3 python3-pip \
 && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir cmake==4.4.4 ninja==1.13.2

COPY --from=maya-src . /opt/maya/
WORKDIR /opt/maya
# llama.cpp (ggml) at the commit Maya's setup.py pins, fetched the way setup.py does.
RUN python3 -c "import setup; print(setup.get_llama_cpp())" \
 && rm -f third_party/llama.cpp-*.zip third_party/llama.cpp-*.zip.done

ARG CUDA_ARCH=120
ARG MAYA_TARGETS="maya-ds4 maya"
ARG MAYA_JOBS=
# Same configure line as maya.py's compile_engine(), minus its GPU probe: the
# architecture is a build arg because `docker build` has no GPU.
RUN cmake -G Ninja -S . -B build -DCMAKE_BUILD_TYPE=Release \
      -DSTRATA_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH} \
      -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_BUILD_TESTS=OFF \
      -DSTRATA_GGML_DIR=/opt/maya/third_party/llama.cpp \
 && cmake --build build --target ${MAYA_TARGETS} -j "${MAYA_JOBS:-$(( $(nproc) / 2 ))}" \
 && mkdir -p /opt/maya-bin \
 && for t in ${MAYA_TARGETS}; do cp "build/$t" /opt/maya-bin/; done \
 && rm -rf build

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# The serve-time packages of Maya's setup.py list, at the versions its native
# venv runs (cmake/ninja are build-only).
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir \
      Jinja2==3.1.6 MarkupSafe==3.0.4 jsonschema==4.26.0 numpy==2.2.6 pillow==12.3.0 \
      psutil==7.2.2 PyYAML==6.0.3 regex==2026.9.29 requests==2.34.2 tqdm==4.70.1

COPY --from=build /opt/maya /opt/maya
COPY --from=build /opt/maya-bin/ /opt/maya/build/
COPY launcher.py /opt/llm-dock/launcher.py

ARG CUDA_VERSION
ARG BUILD_DATE
ARG BUILD_COMMIT
ARG MAYA_COMMIT=unknown
ARG MAYA_VERSION=
ARG CUDA_ARCH=120
ARG MAYA_TARGETS="maya-ds4 maya"
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}" \
      org.opencontainers.image.source="https://github.com/mw00/project-maya" \
      org.opencontainers.image.version="${MAYA_VERSION}" \
      org.llm-dock.maya.commit="${MAYA_COMMIT}" \
      org.llm-dock.maya.cuda-arch="${CUDA_ARCH}" \
      org.llm-dock.maya.targets="${MAYA_TARGETS}"
RUN printf 'maya commit: %s\ncuda: %s\narch: sm_%s\ntargets: %s\nllama.cpp: %s\n' \
      "${MAYA_COMMIT}" "${CUDA_VERSION}" "${CUDA_ARCH}" "${MAYA_TARGETS}" \
      "$(sed -n 's/^LLAMA_CPP_COMMIT = "\(.*\)"/\1/p' /opt/maya/setup.py)" > /opt/llm-dock.txt

ENV PATH=/opt/venv/bin:$PATH MAYA_ROOT=/opt/maya MAYA_STATE_DIR=/maya-state \
    MAYA_UPDATE_CHECK=0 PYTHONUNBUFFERED=1
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["python3", "/opt/llm-dock/launcher.py"]
