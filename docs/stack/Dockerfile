# docs/stack/Dockerfile — the HEP stack in a container, built by build_stack.sh (Ubuntu 24.04, as the lab PC).
#
# From the repository root (Dockerfile.dockerignore sends only the script and the patches):
#
#   docker build -f docs/stack/Dockerfile -t hep-stack .                                  # the core stack
#   docker build -f docs/stack/Dockerfile --build-arg PACKAGES=all -t hep-stack:all .     # everything
#   docker build -f docs/stack/Dockerfile --build-arg JOBS=8 --build-arg ROOT_JOBS=2 -t hep-stack .
#
#   docker run --rm -it -v "$PWD":/work -w /work hep-stack       # a shell in the repository, stack loaded
#
# The build takes hours (ROOT alone is 1–2 h) and ~20 GB of disk; give Docker 3 GB of memory per ROOT
# job. Sources and build trees are removed in the same layer, so the image keeps only the installs.
# The stack's environment is the repository's utils/Env/hep_env.sh, so mount the repository at /work.

FROM ubuntu:24.04

ARG PACKAGES=core
ARG JOBS=""
ARG ROOT_JOBS=""
ARG GRAPHICS=OFF
ARG GEANT4_DATA=ON

ENV HEP_PREFIX=/opt/hep HEKIT_ROOT=/work LANG=C.UTF-8

COPY docs/stack/build_stack.sh /opt/hep-build/build_stack.sh
COPY utils/Env/patches/ /opt/hep-build/patches/

RUN bash /opt/hep-build/build_stack.sh PACKAGES="$PACKAGES" ${JOBS:+JOBS=$JOBS} ${ROOT_JOBS:+ROOT_JOBS=$ROOT_JOBS} \
        GRAPHICS="$GRAPHICS" GEANT4_DATA="$GEANT4_DATA" \
        FASTJET_PATCH=/opt/hep-build/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch && \
    rm -rf /opt/hep/src /opt/hep/build /var/lib/apt/lists/* /root/.cache/pip

RUN echo '[ -n "$BASH_VERSION" ] && [ -f "$HEKIT_ROOT/utils/Env/hep_env.sh" ] && . /opt/hep/setup.sh' \
        > /etc/profile.d/hep.sh && \
    echo 'source /etc/profile.d/hep.sh' >> /etc/bash.bashrc

CMD ["bash"]
