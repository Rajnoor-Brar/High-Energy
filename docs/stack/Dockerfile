# docs/stack/Dockerfile — the HEP stack in a container, built by build_stack.sh (Ubuntu 24.04, as the lab PC).
#
# From the repository root (the context is filtered by Dockerfile.dockerignore: only the script and
# the patches are sent):
#
#   docker build -f docs/stack/Dockerfile -t hep-stack .                                  # the core stack
#   docker build -f docs/stack/Dockerfile --build-arg PACKAGES=all -t hep-stack:all .     # everything
#   docker build -f docs/stack/Dockerfile --build-arg JOBS=8 --build-arg ROOT_JOBS=2 -t hep-stack .
#
#   docker run --rm -it -v "$PWD":/work -w /work hep-stack                 # a shell with the stack loaded
#
# The build takes hours (ROOT alone is 1–2 h) and needs ~20 GB of disk; give Docker 3 GB of memory
# per ROOT job. The sources and build trees are removed in the same layer, so the image keeps only
# the installs.

FROM ubuntu:24.04

ARG PACKAGES=core
ARG JOBS=""
ARG ROOT_JOBS=auto
ARG ROOT_GRAPHICS=OFF
ARG GEANT4_DATA=ON
ARG GEANT4_X11=OFF

ENV DEBIAN_FRONTEND=noninteractive \
    HEP_PREFIX=/opt/hep \
    LANG=C.UTF-8

COPY docs/stack/build_stack.sh /opt/hep-build/build_stack.sh
COPY utils/Env/patches/ /opt/hep-build/patches/

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates sudo && \
    bash /opt/hep-build/build_stack.sh \
        PACKAGES="$PACKAGES" ${JOBS:+JOBS=$JOBS} ROOT_JOBS="$ROOT_JOBS" \
        ROOT_GRAPHICS="$ROOT_GRAPHICS" GEANT4_DATA="$GEANT4_DATA" GEANT4_X11="$GEANT4_X11" \
        FASTJET_PATCH=/opt/hep-build/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch \
        SETUP_STYLE=standalone KEEP_BUILD=0 && \
    rm -rf /opt/hep/src /opt/hep/build /var/lib/apt/lists/* /root/.cache/pip

RUN echo 'source /opt/hep/setup.sh' > /etc/profile.d/hep.sh && \
    echo '[ -f /opt/hep/setup.sh ] && source /opt/hep/setup.sh' >> /etc/bash.bashrc

CMD ["bash"]
