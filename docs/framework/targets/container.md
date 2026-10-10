# Target: a container image

`$HEP` (the stack and HEimdall) shipped as one image, with work dirs mounted into it: Docker on a
PC, Apptainer on a cluster ([cluster](cluster.md), way A). The user chooses this target; P0 never
picks it alone. Only what differs from the phase files is here (D11).

**The user is learning Docker** (the user, 2026-10-07):
- explain each command before running it;
- never build, push or tag an image without asking;
- the image stays private: it is moved as a file, never pushed to a public registry.

## Prerequisites

- **Docker usable by the user.** Joining the `docker` group is the user's own action (it is
  root-equivalent), so P0 records "installed, no group" and stops there.
- About 25 GB free while building (the image keeps the installs only: about 10 GB with
  `packages=all`).
- 3 GB of memory per ROOT compiler (`ROOT_CORES`).

## The Dockerfile

`stack/container/Dockerfile`, written by P2 S1 (C49). The build context is HEimdall itself:

```dockerfile
# stack/container/Dockerfile — HEimdall and its stack in one image (Ubuntu 24.04, as the lab PC).
#
# From $HEP/HEimdall (the context: stack/container/Dockerfile.dockerignore keeps build/ out):
#   docker build -f stack/container/Dockerfile -t heimdall .
#   docker build -f stack/container/Dockerfile --build-arg PACKAGES=core --build-arg ROOT_CORES=2 -t heimdall:core .
#
# A work dir is mounted, never copied in:
#   docker run --rm -it --user "$(id -u):$(id -g)" -v ~/Github/High-Energy:/work -w /work heimdall
FROM ubuntu:24.04

ARG PACKAGES=all
ARG CORES=0
ARG ROOT_CORES=0
ARG GRAPHICS=OFF
ARG GEANT4_DATA=ON

ENV HEP=/opt/hep LANG=C.UTF-8

COPY . /opt/hep/HEimdall

RUN apt-get update && apt-get install -y --no-install-recommends python3 && \
    python3 /opt/hep/HEimdall/stack/build_stack.py prefix=/opt/hep packages="$PACKAGES" \
        cores="$CORES" root_cores="$ROOT_CORES" graphics="$GRAPHICS" geant4_data="$GEANT4_DATA" && \
    bash -c 'source /opt/hep/setup.sh && make -C "$HEP_FW" all' && \
    rm -rf /opt/hep/src /opt/hep/build /var/lib/apt/lists/* /root/.cache/pip && \
    chmod -R a+rX /opt/hep

RUN echo '[ -n "$BASH_VERSION" ] && . /opt/hep/setup.sh' > /etc/profile.d/hep.sh && \
    echo 'source /etc/profile.d/hep.sh' >> /etc/bash.bashrc

CMD ["bash"]
```

`stack/container/Dockerfile.dockerignore`:

```
build/
**/__pycache__/
.pytest_cache/
```

`.git/` goes into the image on purpose: provenance records HEimdall's revision (01 §5.6).

## Apptainer

`stack/container/heimdall.def` (new in P2 S1) builds the `.sif` from a saved Docker image, so a
cluster needs no Docker:

```
Bootstrap: docker-archive
From: heimdall.tar

%environment
    . /opt/hep/setup.sh

%runscript
    exec bash "$@"
```

```bash
docker save heimdall -o heimdall.tar                   # on the PC: a file, moved by hand (scp, a disk)
apptainer build heimdall.sif stack/container/heimdall.def   # where heimdall.tar is
```

## What replaces which phase

**P2 is replaced by `docker build`.** That is a gate: hours of build, plus the downloads. P2 S3's
rows then run inside the image:

```bash
docker run --rm heimdall bash -lc 'root-config --version; lhapdf list --installed | wc -l'
```

**P3 and P4** happen in HEimdall's repo outside the image, and the image is rebuilt after them.
Their tests run inside it, with HEimdall bind-mounted over `/opt/hep/HEimdall` while developing.

**P5's work dirs** are mounted at the same path inside as outside:

```bash
docker run --rm -it --user "$(id -u):$(id -g)" -v "$HOME/Github/High-Energy:$HOME/Github/High-Energy" -w "$HOME/Github/High-Energy" heimdall
```

Then the absolute paths in provenance mean the same thing on both sides.

## Verification (added to P2 S3, P5)

| # | Command | Expected |
|---|---|---|
| C1 | `docker image inspect heimdall --format '{{.Size}}'` | recorded (about 10 GB) |
| C2 | `docker run --rm heimdall bash -lc 'hep where --fw'` | `/opt/hep/HEimdall` |
| C3 | the P2 S3 rows, each through `docker run --rm heimdall bash -lc '…'` | as there |
| C4 | in a mounted High-Energy: `hep check; echo "exit $?"` | `exit 0` |
| C5 | after a run inside: `find ~/Github/High-Energy/results -user root \| wc -l` | `0` (`--user` kept the files the user's) |

## Known limits

- **`hep watch`** only sees runs in the same network namespace: run it in the same container, or
  start containers with `--network host`.
- **Graphics are off** (`GRAPHICS=OFF`). The pages are files (PDF and PNG), and the deck viewer is
  served to the host by `-p <port>:<port>`.
- **The image is Ubuntu 24.04**, so the lab PC's baselines hold inside it, whatever the host runs.
