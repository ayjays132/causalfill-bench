#!/usr/bin/env python3
"""Verify a complete source/evidence checkout or a release archive without extracting it.

The current inventory covers every eligible file except itself. Historical
inventories are ordinary covered files. A separately pinned restoration manifest
prevents an accidentally missing v0.5.1 log or C frontend from being accepted by
regenerating the current inventory. These checks establish byte integrity, not
authentication, model performance, or a new execution of archived Lean proofs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PREFIX = "causalfill-bench"
SCHEMA = "causalfill.file-inventory.v2"
RESTORED_MANIFEST = "tools/release_manifests/v051-restored-evidence.json"
RESTORED_MANIFEST_SHA256 = "dff99a6c80e4ea2763754101b6a0c873c45ec19c2f052c77630a6b1d99dd1849"
EXCLUDED_COMPONENTS = frozenset({
    "__pycache__", ".lake", ".git", ".venv", "node_modules", "private-runs",
    "dist", "build", "tmp", "output", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox",
})
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo", ".olean", ".ilean", ".key", ".o", ".ir"})
EXCLUDED_NAME_ENDINGS = (".olean.private", ".olean.server", ".ir.sig")
EXCLUDED_NAMES = frozenset({".env", ".DS_Store"})
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


class IntegrityError(ValueError):
    """A release is incomplete, unsafe to unpack, or inconsistent with its inventory."""


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def relative_name(value):
    """Accept a single canonical, cross-platform relative archive member name."""
    require(isinstance(value, str) and bool(value), "empty or non-string file path")
    require(not any(ord(char) < 32 for char in value), "control character in file path")
    require("\\" not in value and ":" not in value, "non-portable file path: " + value)
    path = PurePosixPath(value)
    require(value != "." and not path.is_absolute() and path.as_posix() == value,
            "non-canonical relative file path: " + value)
    require(all(part not in {"", ".", ".."} for part in path.parts),
            "unsafe relative file path: " + value)
    return value


def inventory_name(version):
    require(isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][A-Za-z0-9.-]+)?", version),
            "invalid release version")
    return f"reports/source-file-inventory-v{version}.json"


def selection_policy():
    return {
        "excluded_components": sorted(EXCLUDED_COMPONENTS),
        "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
        "excluded_generated_name_endings": list(EXCLUDED_NAME_ENDINGS),
        "excluded_names": sorted(EXCLUDED_NAMES),
        "exclude_egg_info_directories": True,
        "exclude_elf_executables": True,
        "reject_symbolic_links": True,
    }


def path_allowed(relative):
    path = PurePosixPath(relative)
    return (not any(part in EXCLUDED_COMPONENTS or part.endswith(".egg-info") for part in path.parts)
            and path.suffix not in EXCLUDED_SUFFIXES
            and path.name not in EXCLUDED_NAMES
            and not path.name.endswith(EXCLUDED_NAME_ENDINGS))


def no_symlink_path(root, relative):
    path = Path(root)
    for part in PurePosixPath(relative_name(relative)).parts:
        path = path / part
        require(not path.is_symlink(), "symbolic link in release path: " + relative)
    return path


def hash_stream(stream):
    digest = hashlib.sha256()
    size = 0
    prefix = b""
    while True:
        data = stream.read(CHUNK_BYTES)
        if not data:
            break
        if size == 0:
            prefix = data[:4]
        size += len(data)
        digest.update(data)
    return size, digest.hexdigest(), prefix


def file_record(path, relative):
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), "not a regular release file: " + relative)
    with path.open("rb") as stream:
        size, digest, _ = hash_stream(stream)
    return {"path": relative, "bytes": size, "sha256": digest,
            "mode": "0755" if info.st_mode & 0o111 else "0644"}


def eligible(path, root=ROOT):
    """Compatibility predicate for the historical v0.5.1 inventory comparison."""
    path, root = Path(path), Path(root)
    relative = path.relative_to(root).as_posix()
    if not path_allowed(relative) or path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(4) != b"\x7fELF"


def release_files(root, excluded_inventory=None):
    """Walk the declared scope, rejecting links rather than silently dropping them."""
    root = Path(root).resolve()
    require(root.is_dir(), "release root is not a directory")
    selected = {}
    for parent, directories, filenames in os.walk(root, followlinks=False):
        base = Path(parent)
        kept = []
        for name in sorted(directories):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if not path_allowed(relative):
                continue
            require(not path.is_symlink(), "symbolic link in release path: " + relative)
            kept.append(name)
        directories[:] = kept
        for name in sorted(filenames):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if not path_allowed(relative):
                continue
            relative_name(relative)
            require(not path.is_symlink(), "symbolic link in release path: " + relative)
            require(path.is_file(), "not a regular release file: " + relative)
            if relative == excluded_inventory:
                continue
            if eligible(path, root):
                selected[relative] = path
    return dict(sorted(selected.items()))


def parse_json(data, label):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeDecodeError) as exc:
        raise IntegrityError(f"invalid JSON in {label}: {exc}") from exc


def pinned_manifest(data):
    require(hashlib.sha256(data).hexdigest() == RESTORED_MANIFEST_SHA256,
            "restoration manifest changed; historical evidence pins must not be regenerated")
    result = parse_json(data, RESTORED_MANIFEST)
    require(result.get("schema") == "causalfill.restored-evidence.v1", "wrong restoration schema")
    require(result.get("file_count") == len(result.get("files", [])) == 134,
            "incomplete restoration manifest")
    return result


def validate_restored(root):
    root = Path(root)
    manifest_path = no_symlink_path(root, RESTORED_MANIFEST)
    require(manifest_path.is_file(), "missing restoration manifest: " + RESTORED_MANIFEST)
    manifest = pinned_manifest(manifest_path.read_bytes())
    for expected in manifest["files"]:
        relative = relative_name(expected["path"])
        path = no_symlink_path(root, relative)
        require(path.is_file(), "missing restored evidence: " + relative)
        observed = file_record(path, relative)
        require(observed["bytes"] == expected["bytes"] and observed["sha256"] == expected["sha256"],
                "restored evidence changed: " + relative)
    return manifest["file_count"]


def inventory_entries(data, version, name):
    inventory = parse_json(data, name)
    require(isinstance(inventory, dict), "inventory must be a JSON object")
    require(inventory.get("schema") == SCHEMA, "unsupported current inventory schema")
    require(inventory.get("version") == version, "inventory release version mismatch")
    require(inventory.get("inventory") == name == inventory_name(version), "inventory path mismatch")
    require(inventory.get("archive_prefix") == ARCHIVE_PREFIX, "archive prefix mismatch")
    require(inventory.get("selection_policy") == selection_policy(), "inventory selection policy changed")
    files = inventory.get("files")
    require(isinstance(files, list) and bool(files), "inventory has no files")
    entries = {}
    for entry in files:
        require(isinstance(entry, dict), "invalid file inventory entry")
        relative = relative_name(entry.get("path"))
        require(relative != name, "inventory must not include itself")
        require(path_allowed(relative), "excluded runtime file appears in inventory: " + relative)
        require(relative not in entries, "duplicate file in inventory: " + relative)
        require(type(entry.get("bytes")) is int and entry["bytes"] >= 0, "invalid file size: " + relative)
        require(isinstance(entry.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]),
                "invalid SHA-256 digest: " + relative)
        require(isinstance(entry.get("mode"), str) and entry["mode"] in {"0644", "0755"},
                "invalid archive mode: " + relative)
        entries[relative] = entry
    require(list(entries) == sorted(entries), "inventory files must be sorted by path")
    require(inventory.get("file_count") == len(entries), "inventory file count mismatch")
    require(RESTORED_MANIFEST in entries, "restoration manifest is not inventoried")
    return inventory, entries


def tracked_files(root):
    result = subprocess.run(["git", "ls-files", "-z", "--cached"], cwd=root,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0, "--require-tracked requires a Git checkout")
    return set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""}


def check_tracked(root, names):
    missing = sorted(set(names) - tracked_files(root))
    require(not missing, "release files are not tracked in Git: " + ", ".join(missing[:12])
            + (f" (and {len(missing)-12} more)" if len(missing) > 12 else ""))


def write_inventory(root, version, require_tracked=False):
    root = Path(root).resolve()
    validate_restored(root)
    name = inventory_name(version)
    files = release_files(root, name)
    if require_tracked:
        check_tracked(root, [*files, name])
    entries = [file_record(path, relative) for relative, path in files.items()]
    inventory = {
        "schema": SCHEMA, "version": version, "inventory": name,
        "archive_prefix": ARCHIVE_PREFIX,
        "scope": "All eligible regular release files except this inventory itself, including historical inventories and frozen evidence. SHA-256 is byte integrity, not authentication or a new verification run.",
        "selection_policy": selection_policy(), "file_count": len(entries), "files": entries,
    }
    target = no_symlink_path(root, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(inventory, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".inventory-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.chmod(0o644)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return inventory


def validate_checkout(root, version, require_tracked=False):
    root = Path(root).resolve()
    restored_count = validate_restored(root)
    name = inventory_name(version)
    inventory_path = no_symlink_path(root, name)
    require(inventory_path.is_file(), "missing current inventory; use checkout --write-inventory after freezing release files")
    data = inventory_path.read_bytes()
    _, expected = inventory_entries(data, version, name)
    actual = release_files(root, name)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    require(not missing, "inventoried files are missing: " + ", ".join(missing[:12]))
    require(not extra, "files are absent from the inventory: " + ", ".join(extra[:12]))
    for relative, path in actual.items():
        observed = file_record(path, relative)
        require(observed == expected[relative], "file differs from current inventory: " + relative)
    if require_tracked:
        check_tracked(root, [*actual, name])
    return {"status": "passed", "version": version, "files": len(actual) + 1,
            "inventory": name, "inventory_sha256": hashlib.sha256(data).hexdigest(),
            "restored_files_verified": restored_count, "tracked_files_required": require_tracked}


def validate_archive(archive_path, version):
    """Stream and hash archive members; never materialize an untrusted tar member."""
    archive_path = Path(archive_path)
    name = inventory_name(version)
    observed, seen, captured, directories = {}, set(), {}, set()
    with tarfile.open(archive_path, "r|*") as archive:
        for member in archive:
            raw = member.name
            require(raw not in seen, "duplicate archive member: " + raw)
            seen.add(raw)
            if member.isdir() and raw in {ARCHIVE_PREFIX, ARCHIVE_PREFIX + "/"}:
                continue
            require(raw.startswith(ARCHIVE_PREFIX + "/"), "archive member outside release prefix: " + raw)
            relative = relative_name(raw[len(ARCHIVE_PREFIX) + 1:].rstrip("/") if member.isdir()
                                     else raw[len(ARCHIVE_PREFIX) + 1:])
            require(path_allowed(relative), "excluded runtime file in archive: " + relative)
            parents = {parent.as_posix() for parent in PurePosixPath(relative).parents if parent.as_posix() != "."}
            require(not any(parent in observed for parent in parents),
                    "archive file is used as a parent directory: " + relative)
            directories.update(parents)
            if member.isdir():
                require(relative not in observed, "archive file/directory path collision: " + relative)
                directories.add(relative)
                continue
            require(member.type in {tarfile.REGTYPE, tarfile.AREGTYPE} and not member.sparse,
                    "non-regular archive member: " + relative)
            require(relative not in directories, "archive file/directory path collision: " + relative)
            require(member.mode in {0o644, 0o755}, "unsafe or unexpected archive file mode: " + relative)
            stream = archive.extractfile(member)
            require(stream is not None, "unreadable archive member: " + relative)
            with stream:
                if relative in {name, RESTORED_MANIFEST}:
                    require(member.size <= MAX_INVENTORY_BYTES, "inventory exceeds size limit")
                    data = stream.read(MAX_INVENTORY_BYTES + 1)
                    captured[relative] = data
                    size, digest, prefix = len(data), hashlib.sha256(data).hexdigest(), data[:4]
                else:
                    size, digest, prefix = hash_stream(stream)
            require(prefix != b"\x7fELF", "compiled executable in source archive: " + relative)
            require(size == member.size, "truncated archive member: " + relative)
            require(relative not in observed, "duplicate archive file: " + relative)
            observed[relative] = {"path": relative, "bytes": size, "sha256": digest,
                                  "mode": f"{member.mode:04o}"}
    require(name in captured, "current inventory is missing from archive")
    _, expected = inventory_entries(captured[name], version, name)
    require(RESTORED_MANIFEST in captured, "restoration manifest is missing from archive")
    restored = pinned_manifest(captured[RESTORED_MANIFEST])
    for entry in restored["files"]:
        relative = relative_name(entry["path"])
        actual = observed.get(relative)
        require(actual is not None, "restored evidence is missing from archive: " + relative)
        require(actual["bytes"] == entry["bytes"] and actual["sha256"] == entry["sha256"],
                "restored evidence changed in archive: " + relative)
    del observed[name]
    missing, extra = sorted(set(expected) - set(observed)), sorted(set(observed) - set(expected))
    require(not missing, "inventoried files are missing from archive: " + ", ".join(missing[:12]))
    require(not extra, "uninventoried files in archive: " + ", ".join(extra[:12]))
    for relative, expected_entry in expected.items():
        require(observed[relative] == expected_entry, "archive file differs from inventory: " + relative)
    with archive_path.open("rb") as stream:
        archive_bytes, archive_sha256, _ = hash_stream(stream)
    return {"status": "passed", "version": version, "files": len(expected) + 1,
            "bytes": archive_bytes, "sha256": archive_sha256, "inventory": name,
            "inventory_sha256": hashlib.sha256(captured[name]).hexdigest(),
            "restored_files_verified": restored["file_count"]}


def main():
    sys.path.insert(0, str(ROOT))
    from causalfill import __version__
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    checkout = commands.add_parser("checkout", help="check every file against the current release inventory")
    checkout.add_argument("--write-inventory", action="store_true", help="freeze the current bytes before checking them")
    checkout.add_argument("--require-tracked", action="store_true", help="reject release files absent from the Git index")
    checkout.add_argument("--inventory", help="assert the expected current inventory path")
    commands.add_parser("historical", help="check only the original 134 restored files and their pinned manifest")
    archive = commands.add_parser("archive", help="verify a tar archive in place, without extraction")
    archive.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "historical":
            result = {"status": "passed", "restored_files_verified": validate_restored(ROOT)}
        elif args.command == "archive":
            result = validate_archive(args.path, __version__)
        else:
            if args.inventory:
                require(args.inventory == inventory_name(__version__), "--inventory must name the current version's inventory")
            if args.write_inventory:
                write_inventory(ROOT, __version__, args.require_tracked)
            result = validate_checkout(ROOT, __version__, args.require_tracked)
        print(json.dumps(result, indent=2))
    except (IntegrityError, OSError, tarfile.TarError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
