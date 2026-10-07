# docs/stack/Dockerfile — the HEP stack in a container, built by build_stack.py (Ubuntu 24.04, as the lab PC).
#
# From the repository root (Dockerfile.dockerignore sends only docs/stack/ and the patches):
#
#   docker build -f docs/stack/Dockerfile -t hep-stack .                                  # the core stack
#   docker build -f docs/stack/Dockerfile --build-arg PACKAGES=all -t hep-stack:all .     # everything
#   docker build -f docs/stack/Dockerfile --build-arg CORES=8 --build-arg ROOT_CORES=2 -t hep-stack .
#
#   docker run --rm -it -v "$PWD":/work -w /work hep-stack       # a shell in the repository, stack loaded
#
# The build takes hours (ROOT alone is 1–2 h) and ~20 GB of disk; give Docker 3 GB of memory per ROOT
# core (root_cores). Sources and build trees are removed in the same layer, so the image keeps only the installs.
# The stack's environment is the repository's utils/Env/hep_env.sh, so mount the repository at /work.

FROM ubuntu:24.04

ARG PACKAGES=core
ARG CORES=0
ARG ROOT_CORES=0
ARG GRAPHICS=OFF
ARG GEANT4_DATA=ON

ENV HEKIT_ROOT=/work LANG=C.UTF-8

# The repository's layout, so packages.toml's patch path resolves.
COPY docs/stack/ /opt/hek/docs/stack/
COPY utils/Env/patches/ /opt/hek/utils/Env/patches/

RUN apt-get update && apt-get install -y --no-install-recommends python3 && \
    python3 /opt/hek/docs/stack/build_stack.py prefix=/opt/hep hekit_root=/work packages="$PACKAGES" \
        cores="$CORES" root_cores="$ROOT_CORES" graphics="$GRAPHICS" geant4_data="$GEANT4_DATA" && \
    rm -rf /opt/hep/src /opt/hep/build /var/lib/apt/lists/* /root/.cache/pip

RUN echo '[ -n "$BASH_VERSION" ] && [ -f "$HEKIT_ROOT/utils/Env/hep_env.sh" ] && . /opt/hep/setup.sh' \
        > /etc/profile.d/hep.sh && \
    echo 'source /etc/profile.d/hep.sh' >> /etc/bash.bashrc

CMD ["bash"]
