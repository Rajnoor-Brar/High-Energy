"""FIFOs and the private directory they live in (06 §4; finding 00/B19).

The old tools built pipe paths from fixed `/tmp` names, so two runs on the same machine could hand each
other's events to Rivet, and a crash left the pipe behind (00/B19). Everything here is per-run,
created with the user's own permissions only, and removed whatever happens — including the case where
the process is killed before it can clean up, since the directory carries the pid and `hep doctor` can
recognise an orphan.

A FIFO is also the one place where "open" blocks: `open(fifo, "r")` waits for a writer and vice versa.
The supervisor therefore never opens one itself; it hands the *path* to both stages and watches them.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import HepError

PREFIX = "hekit-run-"


def looks_like_ours(path: Path) -> bool:
    """A directory this module would have made, for `hep doctor` to spot leftovers."""
    return path.is_dir() and path.name.startswith(PREFIX)


@dataclass
class Transport:
    """A per-run private directory holding this run's FIFOs.

    Use it as a context manager; the directory and everything in it goes away on exit.
    """

    label: str = ""
    root: Path | None = None                 # where the private directory is made (default: TMPDIR)
    directory: Path | None = field(default=None, init=False)
    fifos: dict[str, Path] = field(default_factory=dict, init=False)

    def __enter__(self) -> "Transport":
        self.open()
        return self

    def __exit__(self, *_exception) -> None:
        self.close()

    def open(self) -> Path:
        if self.directory is not None:
            return self.directory
        suffix = f"-{self.label}" if self.label else ""
        parent = str(self.root) if self.root is not None else None
        if parent is not None:
            Path(parent).mkdir(parents=True, exist_ok=True)
        # mkdtemp gives 0700 and a name nothing else can guess — both matter on a shared machine.
        self.directory = Path(tempfile.mkdtemp(prefix=f"{PREFIX}{os.getpid()}-", suffix=suffix,
                                               dir=parent))
        return self.directory

    def fifo(self, name: str) -> Path:
        """Create (once) and return a named FIFO inside the private directory."""
        if self.directory is None:
            self.open()
        if name in self.fifos:
            return self.fifos[name]
        path = self.directory / name
        os.mkfifo(path, 0o600)
        self.fifos[name] = path
        return path

    def adopt(self, path: Path | str, name: str = "") -> Path:
        """Use a FIFO the user named instead of a private one (`[generator].hepmc` as a literal path).

        It has to exist and be a FIFO: pointing a pipeline at a regular file would "work" and quietly
        buffer a hundred gigabytes onto a disk.
        """
        path = Path(path)
        if not os.path.lexists(path):
            raise HepError(f"the FIFO {path} does not exist",
                           hint="create it with mkfifo, or leave the path unset for a private one")
        if not stat.S_ISFIFO(os.stat(path).st_mode):
            raise HepError(f"{path} exists but is not a FIFO")
        self.fifos[name or path.name] = path
        return path

    def close(self) -> None:
        """Remove the private directory. FIFOs the user named are left alone."""
        directory = self.directory
        self.directory = None
        self.fifos = {}
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)
