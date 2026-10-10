# Target: a container image

Heimdall, with its stack built inside it, shipped as one image; work dirs are mounted into it.
Docker on a PC, Apptainer on a cluster ([cluster](cluster.md), way A). The user chooses this
target; P0 never picks it alone. Only what differs from the phase files is here (D11).

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

`platforms/container/Dockerfile`, written by P2 S1 (C49). The build context is Heimdall itself, and
the image holds it at `/opt/heimdall`, which is `$HEP` inside:

```dockerfile
# platforms/container/Dockerfile — Heimdall and its stack in one image (Ubuntu 24.04, as the lab PC).
#
# From ~/Github/Heimdall (the context; platforms/container/Dockerfile.dockerignore keeps the ignored trees out):
#   docker build -f platforms/container/Dockerfile -t heimdall .
#   docker build -f platforms/container/Dockerfile --build-arg PACKAGES=core --build-arg ROOT_CORES=2 -t heimdall:core .
#
# A work dir is mounted, never copied in:
#   docker run --rm -it --user "$(id -u):$(id -g)" -v ~/Github/Top-Quark:/work -w /work heimdall
FROM ubuntu:24.04

ARG PACKAGES=all
ARG CORES=0
ARG ROOT_CORES=0
ARG GRAPHICS=OFF
ARG GEANT4_DATA=ON

ENV LANG=C.UTF-8

COPY . /opt/heimdall

RUN apt-get update && apt-get install -y --no-install-recommends python3 && \
    cd /opt/heimdall && python3 build_stack.py packages="$PACKAGES" \
        cores="$CORES" root_cores="$ROOT_CORES" graphics="$GRAPHICS" geant4_data="$GEANT4_DATA" && \
    bash -c 'source /opt/heimdall/setup.sh && make -C "$HEP" all' && \
    rm -rf /opt/heimdall/stash /opt/heimdall/forge /var/lib/apt/lists/* /root/.cache/pip && \
    chmod -R a+rX /opt/heimdall

RUN echo '[ -n "$BASH_VERSION" ] && . /opt/heimdall/setup.sh' > /etc/profile.d/hep.sh && \
    echo 'source /etc/profile.d/hep.sh' >> /etc/bash.bashrc

CMD ["bash"]
```

`platforms/container/Dockerfile.dockerignore`:

```
stack/
forge/
stash/
env/venv/
framework/Apps/
.setup/
**/__pycache__/
.pytest_cache/
```

`.git/` goes into the image on purpose: provenance records Heimdall's revision (01 §5.6).
`forge/` is removed in the image's last build layer, together with `stash/`. The tests' scratch is
then made afresh by the first test run inside a container.

## Apptainer

`platforms/container/heimdall.def` (new in P2 S1) builds the `.sif` from a saved Docker image, so a
cluster needs no Docker:

```
Bootstrap: docker-archive
From: heimdall.tar

%environment
    . /opt/heimdall/setup.sh

%runscript
    exec bash "$@"
```

```bash
docker save heimdall -o heimdall.tar                          # on the PC: a file, moved by hand (scp, a disk)
apptainer build heimdall.sif platforms/container/heimdall.def # where heimdall.tar is
```

## What replaces which phase

**P2 is replaced by `docker build`.** That is a gate: hours of build, plus the downloads. P2 S3's
rows then run inside the image:

```bash
docker run --rm heimdall bash -lc 'root-config --version; lhapdf list --installed | wc -l'
```

**P3 and P4** happen in `~/Github/Heimdall` outside the image, and the image is rebuilt after them.

**P5's work dirs** are mounted at the same path inside as outside:

```bash
docker run --rm -it --user "$(id -u):$(id -g)" -v "$HOME/Github/Top-Quark:$HOME/Github/Top-Quark" -w "$HOME/Github/Top-Quark" heimdall
```

Then the absolute paths in provenance mean the same thing on both sides.

## Verification (added to P2 S3, P5)

| # | Command | Expected |
|---|---|---|
| C1 | `docker image inspect heimdall --format '{{.Size}}'` | recorded (about 10 GB) |
| C2 | `docker run --rm heimdall bash -lc 'hep where --hep'` | `/opt/heimdall` |
| C3 | the P2 S3 rows, each through `docker run --rm heimdall bash -lc '…'` | as there |
| C4 | in a mounted Top-Quark: `hep check; echo "exit $?"` | `exit 0` |
| C5 | after a run inside: `find ~/Github/Top-Quark/results -user root \| wc -l` | `0` (`--user` kept the files the user's) |

## Known limits

- **`hep watch`** only sees runs in the same network namespace: run it in the same container, or
  start containers with `--network host`.
- **Graphics are off** (`GRAPHICS=OFF`). The pages are files (PDF and PNG), and the deck viewer is
  served to the host by `-p <port>:<port>`.
- **The image is Ubuntu 24.04**, so the lab PC's baselines hold inside it, whatever the host runs.
