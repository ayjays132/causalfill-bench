#!/usr/bin/env python3
"""Create a deterministic source/evidence archive with a per-file inventory.

Compiler caches, installed toolchains, credentials and local environments are
not release artifacts. The inventory commits every other regular source file;
it excludes its own bytes to avoid a recursive hash definition.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill import __version__
INVENTORY = f"reports/source-file-inventory-v{__version__}.json"
EXCLUDED_COMPONENTS = {"__pycache__", ".lake", ".git", ".venv", "node_modules", "private-runs", "dist", "build", "tmp", "output"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".olean", ".ilean", ".key", ".o", ".ir"}
EXCLUDED_NAME_ENDINGS = (".olean.private", ".olean.server", ".ir.sig")


def eligible(path):
    relative = path.relative_to(ROOT)
    selected = (path.is_file() and not path.is_symlink()
            and not any(part in EXCLUDED_COMPONENTS for part in relative.parts)
            and path.suffix not in EXCLUDED_SUFFIXES
            and not path.name.endswith(EXCLUDED_NAME_ENDINGS))
    if not selected:
        return False
    with path.open("rb") as stream:
        return stream.read(4) != b"\x7fELF"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Write the archive outside the source tree.")
    paths = sorted(p for p in ROOT.rglob("*") if eligible(p) and p.relative_to(ROOT).as_posix() != INVENTORY)
    entries = [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    inventory = {"schema": "causalfill.file-inventory.v1", "version": __version__,
                 "scope": "All archived regular files except this inventory itself; SHA-256 is integrity, not authentication.",
                 "excluded_components": sorted(EXCLUDED_COMPONENTS),
                 "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
                 "excluded_generated_name_endings": EXCLUDED_NAME_ENDINGS,
                 "exclude_elf_executables": True, "files": entries}
    (ROOT / INVENTORY).write_text(json.dumps(inventory, indent=2) + "\n")
    paths = sorted([*paths, ROOT / INVENTORY])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                for path in paths:
                    data = path.read_bytes()
                    name = "causalfill-bench/" + path.relative_to(ROOT).as_posix()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(data))
    print(json.dumps({"archive": str(output), "files": len(paths),
                      "bytes": output.stat().st_size,
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
