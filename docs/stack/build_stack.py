#!/usr/bin/env python3
"""docs/stack/build_stack.py — build the HEP stack from source, as packages.toml and settings.toml say.

    python3 docs/stack/build_stack.py                          # the core stack into ~/HEP
    python3 docs/stack/build_stack.py packages=all cores=8     # everything, 8 compilers at once
    python3 docs/stack/build_stack.py packages="rivet pythia8" root.release=6.40.06
    python3 docs/stack/build_stack.py --config my.toml         # settings, and package changes, from a file
    python3 docs/stack/build_stack.py --list                   # each package: release, needs, state
    python3 docs/stack/build_stack.py --dry-run > build.sh     # the build as a bash script; nothing is run

A setting is a key of settings.toml, given as key=value; a package's key as <package>.<key>=value.
A finished package is stamped ($prefix/.stamps/<name>-<release>) and skipped after, so a rerun
resumes; delete a stamp to redo its package. Every tarball is fetched before the first build, so a
dead link stops the run at once. Each package logs to $prefix/logs/<name>.log.

Standard library only: Python 3.11+ (tomllib), or an older Python with tomli.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NoReturn

try:
    import tomllib
except ModuleNotFoundError:                                        # Python < 3.11
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        sys.exit("build_stack.py reads TOML: it needs Python 3.11+, or the tomli package")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FIELDS = {"release", "url", "kind", "needs", "group", "install", "probe", "args", "optional", "patch",
          "env", "pre", "post", "cores"}
KINDS = ("autotools", "cmake", "unpack", "none")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
TARBALLS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz")

SETUP = """#!/bin/bash
# {prefix}/setup.sh: source it once per session (written by docs/stack/build_stack.py).
export HEP={prefix}
export HEP_INSTALL=$HEP/install
export HEKIT_ROOT=${{HEKIT_ROOT:-{hekit_root}}}
source "$HEKIT_ROOT/utils/Env/hep_env.sh"
"""


def die(message: str) -> NoReturn:
    sys.exit(f"\033[31merror: {message}\033[0m")


def say(message: str) -> None:
    print(f"\033[1m==> {message}\033[0m", file=sys.stderr, flush=True)


# ── the files and the command line ─────────────────────────────────────────────────────────────

def read(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        die(f"cannot read {path}: {error.strerror}")
    except tomllib.TOMLDecodeError as error:
        die(f"{path}: {error}")


def coerce(text: str, like):
    """A command-line value, as the type of the value it replaces."""
    if isinstance(like, bool):
        return text.lower() in ("1", "true", "yes", "on")
    if isinstance(like, int):
        try:
            return int(text)
        except ValueError:
            die(f"'{text}' is not a number")
    if isinstance(like, list):
        return text.replace(",", " ").split()
    return text


def merge(settings: dict, packages: dict, extra: dict) -> None:
    """A --config file: its settings replace, its [package] tables change or add packages."""
    for key, value in extra.items():
        if key in settings:
            if isinstance(settings[key], dict):
                settings[key].update(value)
            else:
                settings[key] = value
        elif isinstance(value, dict):
            packages.setdefault(key, {}).update(value)
        else:
            die(f"--config: no setting '{key}' (settings.toml)")


def options(argv: list[str]) -> tuple[str, dict, dict]:
    settings, packages = read(HERE / "settings.toml"), read(HERE / "packages.toml")
    mode, given = "build", []
    args = iter(argv)
    for arg in args:
        if arg in ("-h", "--help"):
            print(__doc__.split("\n", 1)[1].rstrip())
            sys.exit(0)
        elif arg in ("-n", "--dry-run"):
            mode = "script"
        elif arg == "--list":
            mode = "list"
        elif arg == "--config":
            merge(settings, packages, read(Path(next(args, "") or die("--config needs a file"))))
        elif "=" in arg:
            given.append(arg.split("=", 1))
        else:
            die(f"unknown argument '{arg}' (see --help)")
    for key, text in given:                                        # after --config: the command line wins
        name, _, field = key.rpartition(".")
        if not name:
            if key not in settings or isinstance(settings[key], dict):
                die(f"no setting '{key}' (settings.toml)")
            settings[key] = coerce(text, settings[key])
        elif name not in packages:
            die(f"no package '{name}' (packages.toml)")
        elif field not in FIELDS:
            die(f"a package has no key '{field}' (packages.toml says which)")
        else:
            packages[name][field] = coerce(text, packages[name].get(field, ""))
    for name, p in packages.items():
        if unknown := sorted(set(p) - FIELDS):
            die(f"[{name}] has no key {', '.join(unknown)}")
        if p.get("kind") not in KINDS:
            die(f"[{name}].kind must be one of {', '.join(KINDS)}")
        if p["kind"] != "none" and not p.get("url"):
            die(f"[{name}] has no url")
        for other in [*p.get("needs", []), *p.get("optional", {})]:
            if other not in packages:
                die(f"[{name}] names '{other}', which is not a package")
    return mode, settings, packages


# ── placeholders ───────────────────────────────────────────────────────────────────────────────

def probe(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


def ram_kb() -> int:
    try:
        return int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text())[1])
    except (OSError, TypeError):
        return 8_000_000


def context(s: dict) -> dict:
    """The placeholders every package sees: the settings, and what follows from them."""
    prefix = Path(s["prefix"]).expanduser().resolve()
    python = shutil.which(s["python"]) or die(f"no {s['python']}: install Python 3, or set python=")
    py = probe([python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"])
    cores = s["cores"] or len(os.sched_getaffinity(0))             # the CPUs this process may run on
    machine = os.uname().machine
    return {**s, "prefix": str(prefix), "inst": str(prefix / "install"), "venv": str(prefix / ".venv"),
            "cores": cores, "root_cores": s["root_cores"] or max(1, min(cores, ram_kb() // 3_000_000)),
            "python": python, "py": py, "pyxy": py.replace(".", ""),
            "pyinc": probe([python, "-c", "import sysconfig; print(sysconfig.get_paths()['include'])"]),
            "cxxflags": f"{s['opt_flags']} -std=c++{s['cxx_std']}", "arch": {"x86_64": "x64"}.get(machine, machine),
            "repo": str(REPO), "hekit_root": s["hekit_root"] or str(REPO)}


def scope(name: str, p: dict, c: dict) -> dict:
    """A package's own placeholders on top of the run's."""
    release = str(p.get("release", ""))
    return {**c, "release": release, "series": release.rpartition(".")[0] or release,
            "src": f"{c['prefix']}/src/{name}", "build": f"{c['prefix']}/build/{name}",
            "install": f"{c['inst']}/{p.get('install', name)}"}


def expand(text: str, k: dict) -> str:
    def one(match: re.Match) -> str:
        if match[1] not in k:
            die(f"no placeholder {{{match[1]}}} (in '{text}')")
        value = k[match[1]]
        return " ".join(map(str, value)) if isinstance(value, list) else str(value)
    return PLACEHOLDER.sub(one, str(text))


def words(items: list[str], k: dict) -> list[str]:
    """Arguments: each item one word, but an item that is only a list placeholder gives its words."""
    out = []
    for item in items:
        whole = PLACEHOLDER.fullmatch(item)
        if whole and isinstance(k.get(whole[1]), list):
            out += [expand(value, k) for value in k[whole[1]]]
        else:
            out.append(expand(item, k))
    return out


# ── the packages ───────────────────────────────────────────────────────────────────────────────

def stamp(name: str, p: dict, c: dict) -> Path:
    return Path(c["prefix"], ".stamps", name + (f"-{p['release']}" if p.get("release") else ""))


def present(name: str, p: dict, c: dict) -> bool:
    """Built here (stamped), or installed some other way (its probe file is there)."""
    marker = p.get("probe", "{install}")
    return stamp(name, p, c).exists() or bool(marker) and Path(expand(marker, scope(name, p, c))).exists()


def tarball(name: str, p: dict, c: dict) -> tuple[Path, str]:
    url = expand(p["url"], scope(name, p, c))
    ending = next((end for end in TARBALLS if url.endswith(end)), ".tar")
    return Path(c["prefix"], "src", f"{name}-{p.get('release', '')}{ending}"), url


def plan(s: dict, packages: dict, c: dict) -> tuple[list[str], list[str]]:
    """The packages to go through, in build order, and those of them added because others need them."""
    want = s["packages"].split() if isinstance(s["packages"], str) else list(s["packages"])
    if want == ["core"]:
        chosen = [n for n, p in packages.items() if p.get("group", "core") == "core"]
    elif want == ["all"]:
        chosen = list(packages)
    else:
        chosen = want
        for name in want:
            if name not in packages:
                die(f"no package '{name}'; there are: {' '.join(packages)}")
    order: list[str] = []

    def visit(name: str, chain: list[str]) -> None:
        if name in order:
            return
        if name in chain:
            die("the needs go round: " + " → ".join([*chain, name]))
        for need in packages[name].get("needs", []):
            if need in chosen or not present(need, packages[need], c):
                visit(need, [*chain, name])
        order.append(name)

    for name in packages:                                          # the file's order, needs first
        if name in chosen:
            visit(name, [])
    return order, [n for n in order if n not in chosen]


class Shell:
    """Runs the build's commands, each into its package's log; for --dry-run, prints them as bash."""

    def __init__(self, script: bool, env: dict[str, str]):
        self.script, self.env, self.name, self.log = script, env, "setup", Path(os.devnull)

    def run(self, argv: list[str], cwd: str | None = None, env: dict[str, str] | None = None) -> None:
        if self.script:
            line = " ".join([*(f"{key}={shlex.quote(value)}" for key, value in (env or {}).items()),
                             shlex.join(argv)])
            print(f"cd {shlex.quote(cwd)} && {line}" if cwd else line)
            return
        with open(self.log, "a", encoding="utf-8") as log:
            log.write(f"+ {shlex.join(argv)}\n")
            log.flush()
            try:
                code = subprocess.run(argv, cwd=cwd, env={**self.env, **(env or {})}, stdin=subprocess.DEVNULL,
                                      stdout=log, stderr=subprocess.STDOUT).returncode
            except OSError as error:
                log.write(f"{error}\n")
                code = 127
        if code:
            tail = self.log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
            print("\n".join(tail), file=sys.stderr)
            die(f"{self.name}: '{shlex.join(argv)}' failed; the whole log is {self.log}")


def fetch(items: list[tuple[Path, str]], shell: Shell) -> None:
    """Every tarball not yet in src/, four at a time, before anything is built."""
    missing = [(file, url) for file, url in items if not file.is_file() or not file.stat().st_size]
    if shell.script:
        for file, url in missing:
            part = shlex.quote(f"{file}.part")
            print(f"curl -fL --retry 3 -o {part} {shlex.quote(url)} && mv {part} {shlex.quote(str(file))}")
        return
    if not missing:
        return
    say(f"downloading {len(missing)} tarball{'s' if len(missing) > 1 else ''}")

    def get(item: tuple[Path, str]) -> str | None:
        file, url = item
        part = file.with_name(file.name + ".part")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "build_stack.py"})
            with urllib.request.urlopen(request, timeout=60) as response, open(part, "wb") as out:
                shutil.copyfileobj(response, out, 1 << 20)
        except (OSError, ValueError) as error:
            return f"{url}: {error}"
        part.replace(file)
        return None

    with ThreadPoolExecutor(4) as pool:
        if errors := [error for error in pool.map(get, missing) if error]:
            die("downloads failed (set <package>.url=…, or put the tarball in src/ yourself):\n  "
                + "\n  ".join(errors))


def build(name: str, p: dict, c: dict, shell: Shell, have: set[str]) -> None:
    k = scope(name, p, c)
    kind = p["kind"]
    if kind != "none":
        into = k["install"] if kind == "unpack" else k["src"]      # afresh, so a failed try leaves nothing
        shell.run(["rm", "-rf", into])
        shell.run(["mkdir", "-p", into])
        shell.run(["tar", "xf", str(tarball(name, p, c)[0]), "-C", into, "--strip-components=1"])
    if p.get("patch"):
        shell.run(["patch", "-d", k["src"], "-p0", "-i", str(REPO / expand(p["patch"], k))])
    env = {key: expand(value, k) for key, value in p.get("env", {}).items()}
    where = {"unpack": k["install"], "none": c["prefix"]}.get(kind, k["src"])
    for text in p.get("pre", []):
        shell.run(words(shlex.split(text), k), where, env)
    args = words(p.get("args", []), k)
    for other, extra in p.get("optional", {}).items():
        if other in have:
            args += words(extra, k)
    jobs = f"-j{expand(str(p.get('cores', '{cores}')), k)}"                 # make's and cmake's: compilers at once
    if kind == "autotools":
        shell.run(["./configure", f"--prefix={k['install']}", *args], k["src"], env)
        shell.run(["make", jobs], k["src"], env)
        shell.run(["make", "install"], k["src"], env)
    elif kind == "cmake":
        shell.run(["cmake", "-S", k["src"], "-B", k["build"], f"-DCMAKE_INSTALL_PREFIX={k['install']}",
                   "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_CXX_STANDARD={c['cxx_std']}", *args], env=env)
        shell.run(["cmake", "--build", k["build"], jobs], env=env)
        shell.run(["cmake", "--install", k["build"]], env=env)
    for text in p.get("post", []):
        shell.run(words(shlex.split(text), k), where, env)


def system(s: dict, c: dict, shell: Shell) -> None:
    """apt_packages, through sudo when not root; stamped like a package."""
    done = Path(c["prefix"], ".stamps", "system")
    if done.exists():
        say("system packages: done already")
        return
    if not shutil.which("apt-get"):
        die("no apt-get: install settings.toml's apt_packages (under this system's names), then system=false")
    sudo = [] if os.geteuid() == 0 else ["sudo"]
    say("system packages (apt)")
    shell.name, shell.log = "system", Path(c["prefix"], "logs", "system.log")
    if sudo and not shell.script and subprocess.run(["sudo", "-v"]).returncode:    # its prompt, not in the log
        die("sudo failed: run as root, or install the system packages and set system=false")
    shell.run([*sudo, "apt-get", "update"])
    shell.run([*sudo, "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y",
               "--no-install-recommends", *s["apt_packages"]])
    if not shell.script:
        done.touch()


def environment(s: dict, c: dict, packages: dict) -> tuple[dict[str, list[str]], dict[str, str]]:
    """The build's paths (each install's bin/, lib/ and Python directory; the venv first) and [env]."""
    dirs = dict.fromkeys(f"{c['inst']}/{p.get('install', n)}" for n, p in packages.items() if p["kind"] != "none")
    paths = {"PATH": [f"{c['venv']}/bin", *(f"{d}/bin" for d in dirs)],
             "LD_LIBRARY_PATH": [f"{d}/lib" for d in dirs],
             "PYTHONPATH": [f"{d}/lib/python{c['py']}/site-packages" for d in dirs]}
    return paths, {key: expand(value, c) for key, value in s["env"].items()}


def show(order: list[str], packages: dict, c: dict) -> None:
    """Each package: built here (stamped) or installed otherwise, and whether this run builds it."""
    print(f"{'package':12} {'release':9} {'group':6} {'state':10} {'this run':9} needs")
    for name, p in packages.items():
        built = stamp(name, p, c).exists()
        state = "built" if built else "installed" if present(name, p, c) else ""
        run = "build" if name in order and not built else ""
        print(f"{name:12} {p.get('release', '—'):9} {p.get('group', 'core'):6} {state:10} {run:9} "
              f"{' '.join(p.get('needs', []))}")


def main(argv: list[str]) -> None:
    mode, s, packages = options(argv)
    c = context(s)
    order, added = plan(s, packages, c)
    if mode == "list":
        show(order, packages, c)
        return
    script = mode == "script"
    paths, fixed = environment(s, c, packages)
    env = dict(os.environ)
    for key, items in paths.items():
        env[key] = ":".join([*items, *([os.environ[key]] if os.environ.get(key) else [])])
    shell = Shell(script, {**env, **fixed})
    prefix = Path(c["prefix"])
    folders = [prefix / f for f in ("src", "build", "install", "logs", ".stamps")]
    if script:
        print("#!/usr/bin/env bash\n# The HEP stack's build, as `build_stack.py --dry-run` printed it: run it on a fresh\n"
              "# prefix (it neither reads nor writes stamps).\nset -euo pipefail")
        print("mkdir -p " + " ".join(shlex.quote(str(f)) for f in folders))
        for key, items in paths.items():
            print(f'export {key}={shlex.quote(":".join(items))}"${{{key}:+:${key}}}"')
        for key, value in fixed.items():
            print(f"export {key}={shlex.quote(value)}")
    else:
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
    say(f"HEP stack → {prefix}: {' '.join(order)}" + (f"  (added, as needed: {' '.join(added)})" if added else ""))
    say(f"C++{c['cxx_std']} {c['opt_flags']}, {c['cores']} cores (ROOT {c['root_cores']})"
        + (", dry run: nothing is run" if script else ""))
    if s["system"]:
        system(s, c, shell)
    todo = [n for n in order if not stamp(n, packages[n], c).exists()]
    fetch([tarball(n, packages[n], c) for n in todo if packages[n]["kind"] != "none"], shell)
    have = {n for n, p in packages.items() if present(n, p, c)} | set(order)
    for name in order:
        p = packages[name]
        label = name + (f" {p['release']}" if p.get("release") else "")
        if name not in todo:
            say(f"{label}: done already")
            continue
        say(label)
        shell.name, shell.log = name, prefix / "logs" / f"{name}.log"
        started = time.monotonic()
        if script:
            print(f"\n# == {label}")
        else:
            shell.log.write_text("", encoding="utf-8")
        build(name, p, c, shell, have)
        if not script:
            stamp(name, p, c).touch()
            say(f"{label}: done in {(time.monotonic() - started) / 60:.0f} min")
    setup = prefix / "setup.sh"                                    # the lab PC's stub; one already there is kept
    if script:
        print(f"\n[ -e {shlex.quote(str(setup))} ] || cat > {shlex.quote(str(setup))} <<'EOF'\n"
              f"{SETUP.format(**c)}EOF")
    elif not setup.exists():
        setup.write_text(SETUP.format(**c), encoding="utf-8")
    say(f"done: source {setup}")


if __name__ == "__main__":
    main(sys.argv[1:])
