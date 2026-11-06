#!/usr/bin/env python3
"""Build and verify a deterministic source/evidence archive with a complete inventory.

Write the archive outside the checkout. Historical evidence is preserved and its
restored files are checked before the current inventory can be regenerated.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from causalfill import __version__
from release_integrity import (
    ARCHIVE_PREFIX, EXCLUDED_COMPONENTS, EXCLUDED_SUFFIXES, EXCLUDED_NAME_ENDINGS,
    IntegrityError, eligible, inventory_entries, inventory_name, no_symlink_path,
    require, validate_archive, validate_checkout, write_inventory,
)

INVENTORY = inventory_name(__version__)


def build_archive(root, output, version, require_tracked=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    require(not output.is_relative_to(root), "Write the archive outside the source tree.")
    write_inventory(root, version, require_tracked)
    inventory_relative = inventory_name(version)
    inventory_data = (root / inventory_relative).read_bytes()
    _, entries = inventory_entries(inventory_data, version, inventory_relative)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".causalfill-package-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with temporary.open("wb") as stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                    for relative in sorted([*entries, inventory_relative]):
                        if relative == inventory_relative:
                            size, mode = len(inventory_data), 0o644
                            source = io.BytesIO(inventory_data)
                        else:
                            expected = entries[relative]
                            path = no_symlink_path(root, relative)
                            require(path.is_file(), "source file disappeared while packaging: " + relative)
                            size, mode = expected["bytes"], int(expected["mode"], 8)
                            source = path.open("rb")
                        info = tarfile.TarInfo(ARCHIVE_PREFIX + "/" + relative)
                        info.size, info.mode, info.mtime = size, mode, 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        with source:
                            archive.addfile(info, source)
        # Bind the archived bytes to the inventory and reject a source tree that
        # changed while the archive was being written.
        receipt = validate_archive(temporary, version)
        validate_checkout(root, version, require_tracked)
        temporary.replace(output)
        return {"archive": str(output), **receipt,
                "tracked_files_required": require_tracked,
                "scope": "Byte integrity of source and retained evidence; archived proof/model claims keep their original scope."}
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-tracked", action="store_true", help="require every packaged file in the Git index")
    args = parser.parse_args()
    try:
        print(json.dumps(build_archive(ROOT, args.output, __version__, args.require_tracked), indent=2))
    except (IntegrityError, OSError, tarfile.TarError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
