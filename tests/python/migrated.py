"""Schema-1 inputs as schema-2 files, for tests that compare against the legacy fixtures.

The real `hep config migrate` does the work (P1-S06). The golden comparisons ask it *not* to rename tags
or drop undeclared option quantities, so that point names and counts can be compared with the legacy
fixtures like with like; the configs committed as `.v2.toml` do get those changes.
"""

from __future__ import annotations

from pathlib import Path

from hekit.config.migrate import dumps, migrate_file


def write_v2(source: Path, destination: Path, *, faithful: bool = True) -> Path:
    """Migrate `source` and write it to `destination`."""
    result = migrate_file(source, rename_tags=not faithful, drop_undeclared_options=not faithful)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(dumps(result, name=destination.name, source=str(source)), encoding="utf-8")
    return destination
