# Thin adapter for jpezzulli/sglang-rtxpro6000 (Pennyroyal).
# Pennyroyal v2.5.3, resolved from its release tag. CUDA stays inside Docker;
# the adapter never installs or upgrades a host toolkit or kernel driver.
ARG SGLANG_BASE=ghcr.io/jpezzulli/sglang-rtxpro6000@sha256:81d4d3d19b21e30b895f57e3628a8dd82c02a52c17e6234f5f3ea7836fd31fb3
FROM ${SGLANG_BASE}

ARG SGLANG_BASE
ARG BUILD_DATE
ARG BUILD_COMMIT
LABEL org.llm-dock.build.date="${BUILD_DATE}" \
      org.llm-dock.build.commit="${BUILD_COMMIT}" \
      org.llm-dock.sglang.base="${SGLANG_BASE}" \
      org.opencontainers.image.source="https://github.com/jpezzulli/sglang-rtxpro6000"

# LLM-Dock's standard short bind mounts are created by Docker as root. Running
# with that identity makes the per-service /cache and /nixl mounts writable
# without a host ownership change or a privileged container.
USER root
# Match the CUDA 13.0 Torch wheels: the CUDA 13.3 compatibility package fails
# with error 803 on this host's 575.57.08 kernel driver. NVIDIA's signed R580
# user-mode package works, without changing the host toolkit/kernel driver.
# Fedora 44 publishes only newer packages, so use NVIDIA's RHEL9 repository
# for this one pinned library package (its glibc requirements fit Fedora).
RUN dnf install -y --setopt=install_weak_deps=False --nodocs \
      --repofrompath=cuda-compat130,https://developer.download.nvidia.com/compute/cuda/repos/rhel9/x86_64 \
      --setopt=cuda-compat130.gpgkey=https://developer.download.nvidia.com/compute/cuda/repos/rhel9/x86_64/D42D0685.pub \
      --disablerepo='*' --enablerepo=cuda-compat130 \
      cuda-compat-13-0-580.178.04-1.el9.x86_64 \
    && dnf clean all
RUN test -x /usr/local/bin/pennyroyal \
    && test -x /opt/pennyroyal/.venv/bin/sglang \
    && mv /opt/pennyroyal/.venv/bin/sglang /opt/pennyroyal/.venv/bin/sglang-runtime
COPY --chmod=755 launcher.py /usr/local/bin/llm-dock-sglang
COPY --chmod=755 launcher.py /opt/pennyroyal/.venv/bin/sglang
COPY --chmod=755 gpu_check.py /usr/local/bin/llm-dock-sglang-gpu-check
COPY patch_recipes.py /opt/llm-dock/patch_recipes.py

RUN /opt/pennyroyal/.venv/bin/python /opt/llm-dock/patch_recipes.py \
    && bash -n /opt/pennyroyal/configs/pennyroyal/llm-dock-serve-flash-next.sh \
    && bash -n /opt/pennyroyal/configs/pennyroyal/llm-dock-serve-flash-next-frspec.sh \
    && /opt/pennyroyal/.venv/bin/python -m py_compile /usr/local/bin/llm-dock-sglang \
    && /usr/local/bin/pennyroyal --check

# Preserve the upstream /health check, port and working directory. The
# adapter supplies checkpoint quantization and sizing before cache derivation,
# then adds identity/auth after the recipe has assembled its command.
EXPOSE 8001
ENTRYPOINT ["/usr/local/bin/llm-dock-sglang"]
CMD ["--help"]
