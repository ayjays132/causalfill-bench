"""Release regression tests for omitted evidence and ambiguous/unsafe archives.

Fixtures copy only the 134 small restored files, not the archived proof exports or
episode corpus. These tests audit packaging; they do not rerun formal proofs.
"""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from package_release import build_archive
from release_integrity import (
    ARCHIVE_PREFIX, IntegrityError, RESTORED_MANIFEST, inventory_entries,
    inventory_name, validate_archive, validate_checkout, validate_restored,
    write_inventory,
)

VERSION = "0.5.2"


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="causalfill-release-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "source"
        self.root.mkdir()
        manifest = json.loads((ROOT / RESTORED_MANIFEST).read_text())
        for relative in [RESTORED_MANIFEST, *[entry["path"] for entry in manifest["files"]]]:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.log = next(entry["path"] for entry in manifest["files"] if entry["path"].endswith(".log"))
        self.frontend = "formal/embedding/lean_frontend.c"
        (self.root / "README.md").write_text("CausalFill release fixture.\n", encoding="utf-8")

    def tar_entries(self, path):
        with tarfile.open(path, "r:*") as archive:
            return [(member.name, archive.extractfile(member).read()) for member in archive]

    def emit_tar(self, name, entries):
        path = self.base / name
        with tarfile.open(path, "w") as archive:
            for member_name, data in entries:
                member = tarfile.TarInfo(member_name)
                member.size, member.mode = len(data), 0o644
                archive.addfile(member, io.BytesIO(data))
        return path

    def test_missing_restored_log_or_frontend_cannot_be_rebaselined(self):
        self.assertEqual(validate_restored(self.root), 134)
        for relative in (self.log, self.frontend):
            with self.subTest(path=relative):
                (self.root / relative).unlink()
                with self.assertRaisesRegex(IntegrityError, "missing restored evidence"):
                    write_inventory(self.root, VERSION)
                shutil.copyfile(ROOT / relative, self.root / relative)

    def test_modified_evidence_or_restoration_manifest_cannot_be_rebaselined(self):
        path = self.root / self.log
        path.write_bytes(path.read_bytes() + b"changed\n")
        with self.assertRaisesRegex(IntegrityError, "restored evidence changed"):
            write_inventory(self.root, VERSION)
        shutil.copyfile(ROOT / self.log, path)
        manifest_path = self.root / RESTORED_MANIFEST
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(IntegrityError, "restoration manifest changed"):
            write_inventory(self.root, VERSION)

    def test_current_inventory_detects_added_changed_and_missing_files(self):
        write_inventory(self.root, VERSION)
        self.assertEqual(validate_checkout(self.root, VERSION)["status"], "passed")
        extra = self.root / "unrecorded.txt"
        extra.write_text("Unrecorded evidence.\n", encoding="utf-8")
        with self.assertRaisesRegex(IntegrityError, "absent from the inventory"):
            validate_checkout(self.root, VERSION)
        extra.unlink()
        readme = self.root / "README.md"
        readme.write_text("Changed source.\n", encoding="utf-8")
        with self.assertRaisesRegex(IntegrityError, "differs from current inventory"):
            validate_checkout(self.root, VERSION)
        readme.unlink()
        with self.assertRaisesRegex(IntegrityError, "inventoried files are missing"):
            validate_checkout(self.root, VERSION)

    def test_inventory_rejects_duplicate_paths_self_hash_and_invalid_metadata(self):
        original = write_inventory(self.root, VERSION)
        name = inventory_name(VERSION)
        mutations = [
            ("duplicate", lambda doc: doc["files"].insert(0, dict(doc["files"][0]))),
            ("self", lambda doc: doc["files"][0].update(path=name)),
            ("traversal", lambda doc: doc["files"][0].update(path="../escape")),
            ("wrong_version", lambda doc: doc.update(version="0.5.1")),
            ("boolean_size", lambda doc: doc["files"][0].update(bytes=True)),
            ("invalid_mode", lambda doc: doc["files"][0].update(mode=[])),
        ]
        for label, mutate in mutations:
            with self.subTest(mutation=label):
                changed = json.loads(json.dumps(original))
                mutate(changed)
                with self.assertRaises(IntegrityError):
                    inventory_entries(json.dumps(changed).encode(), VERSION, name)
        data = json.dumps(original).replace('"version": "0.5.2"', '"version": "0.5.2", "version": "0.5.2"')
        with self.assertRaisesRegex(IntegrityError, "duplicate JSON key"):
            inventory_entries(data.encode(), VERSION, name)

    def test_archive_is_deterministic_preserves_logs_and_excludes_runtime_files(self):
        for relative in ("private-runs/local.json", "__pycache__/cached.pyc", ".env", "example.egg-info/PKG-INFO"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"runtime only")
        (self.root / "compiled-binary").write_bytes(b"\x7fELFnot a source file")
        first = build_archive(self.root, self.base / "first.tar.gz", VERSION)
        os.utime(self.root / "README.md", (123456789, 123456789))
        second = build_archive(self.root, self.base / "second.tar.gz", VERSION)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["inventory_sha256"], second["inventory_sha256"])
        self.assertEqual(first["restored_files_verified"], 134)
        self.assertEqual(validate_archive(self.base / "first.tar.gz", VERSION)["status"], "passed")
        with tarfile.open(self.base / "first.tar.gz", "r:gz") as archive:
            members = archive.getmembers()
            names = {member.name for member in members}
            self.assertIn(ARCHIVE_PREFIX + "/" + self.log, names)
            self.assertIn(ARCHIVE_PREFIX + "/" + self.frontend, names)
            self.assertNotIn(ARCHIVE_PREFIX + "/.env", names)
            self.assertNotIn(ARCHIVE_PREFIX + "/compiled-binary", names)
            self.assertFalse(any("/private-runs/" in name or ".egg-info/" in name for name in names))
            self.assertTrue(all(member.mtime == member.uid == member.gid == 0 for member in members))

    def test_archive_detects_missing_changed_and_uninventoried_files(self):
        source = self.base / "complete.tar.gz"
        build_archive(self.root, source, VERSION)
        original = self.tar_entries(source)
        prefix = ARCHIVE_PREFIX + "/"
        cases = [
            ("missing.tar", [(name, data) for name, data in original if name != prefix + self.log], "restored evidence is missing"),
            ("changed.tar", [(name, b"changed" if name == prefix + "README.md" else data) for name, data in original], "differs from inventory"),
            ("extra.tar", [*original, (prefix + "unrecorded.txt", b"extra")], "uninventoried files"),
            ("duplicate.tar", [*original, (prefix + "README.md", b"duplicate")], "duplicate archive member"),
        ]
        for name, entries, message in cases:
            with self.subTest(archive=name):
                path = self.emit_tar(name, entries)
                with self.assertRaisesRegex(IntegrityError, message):
                    validate_archive(path, VERSION)

    def test_archive_rejects_traversal_links_special_modes_and_runtime_files(self):
        prefix = ARCHIVE_PREFIX + "/"
        cases = [
            (prefix + "../../escape", tarfile.REGTYPE, 0o644),
            ("/outside", tarfile.REGTYPE, 0o644),
            (prefix + "a\\b", tarfile.REGTYPE, 0o644),
            (prefix + ".", tarfile.REGTYPE, 0o644),
            (prefix + "link", tarfile.SYMTYPE, 0o644),
            (prefix + "hardlink", tarfile.LNKTYPE, 0o644),
            (prefix + "privileged", tarfile.REGTYPE, 0o4755),
            (prefix + "private-runs/result.json", tarfile.REGTYPE, 0o644),
        ]
        for index, (name, kind, mode) in enumerate(cases):
            with self.subTest(member=name):
                path = self.base / f"unsafe-{index}.tar"
                with tarfile.open(path, "w") as archive:
                    member = tarfile.TarInfo(name)
                    member.type, member.mode, member.linkname = kind, mode, "../../outside"
                    archive.addfile(member)
                with self.assertRaises(IntegrityError):
                    validate_archive(path, VERSION)
        self.assertFalse((self.base / "escape").exists())

    def test_archive_rejects_file_directory_collisions_in_either_order(self):
        prefix = ARCHIVE_PREFIX + "/"
        files = [(prefix + "parent", b"file"), (prefix + "parent/child", b"child")]
        for index, entries in enumerate((files, list(reversed(files)))):
            with self.subTest(order=index):
                path = self.emit_tar(f"collision-{index}.tar", entries)
                with self.assertRaisesRegex(IntegrityError, "parent directory|path collision"):
                    validate_archive(path, VERSION)

    @unittest.skipIf(os.name == "nt", "creating test symlinks requires Windows privilege")
    def test_checkout_rejects_file_and_directory_symlinks(self):
        for directory in (False, True):
            with self.subTest(directory=directory):
                link = self.root / "linked"
                target = self.base if directory else self.root / "README.md"
                link.symlink_to(target, target_is_directory=directory)
                with self.assertRaisesRegex(IntegrityError, "symbolic link"):
                    write_inventory(self.root, VERSION)
                link.unlink()

    @unittest.skipUnless(shutil.which("git"), "Git is needed to exercise checkout publication checks")
    def test_git_tracking_guard_and_frozen_log_exceptions(self):
        def git(*args):
            subprocess.run(["git", *args], cwd=self.root, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git("init", "-q")
        git("config", "core.autocrlf", "false")
        (self.root / ".gitignore").write_text("*.log\n", encoding="utf-8")
        write_inventory(self.root, VERSION)
        git("add", "--all")
        with self.assertRaisesRegex(IntegrityError, "not tracked in Git"):
            validate_checkout(self.root, VERSION, require_tracked=True)
        shutil.copyfile(ROOT / ".gitignore", self.root / ".gitignore")
        shutil.copyfile(ROOT / ".gitattributes", self.root / ".gitattributes")
        write_inventory(self.root, VERSION)
        git("config", "core.autocrlf", "true")
        git("add", "--all")
        result = validate_checkout(self.root, VERSION, require_tracked=True)
        self.assertTrue(result["tracked_files_required"])
        # The exact same tracked bytes must survive an autocrlf=true checkout.
        exported = self.base / "windows-style-checkout"
        git("checkout-index", "--all", "--prefix=" + exported.as_posix() + "/")
        self.assertEqual(validate_checkout(exported, VERSION)["status"], "passed")

    def test_archive_output_cannot_be_written_inside_source_tree(self):
        with self.assertRaisesRegex(IntegrityError, "outside the source tree"):
            build_archive(self.root, self.root / "recursive.tar.gz", VERSION)
        self.assertFalse((self.root / "recursive.tar.gz").exists())


if __name__ == "__main__":
    unittest.main()
