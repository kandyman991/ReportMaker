"""Independent-review regression gates for PR9-F01/F02/F03.

All fixtures are synthetic; no customer material, external files or browser data.
"""
from copy import deepcopy
from hashlib import sha256
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_BZIP2, ZIP_STORED

from reportmaker.engine import ProjectEditor, module_outline
from reportmaker.model import LocalizedText, PhotoBlock
from reportmaker.project_io import ReportProject, load_project, save_project

from test_m2_project import example


class ReviewedM2SafetyTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "project.rmproj"

    def test_f01_deleted_photo_not_present_in_project_or_archive(self):
        project = example()
        editor = ProjectEditor(project.report)
        grandchild = editor.report.modules[0].blocks[1].module
        picture = grandchild.blocks[1]
        self.assertIsInstance(picture, PhotoBlock)
        editor.remove_block(grandchild.id, picture.id)
        project.report = editor.report

        # Keep bytes in memory: undo can restore the original logical image ID.
        self.assertIn("photo-1", project.assets)
        save_project(project, self.path)
        with ZipFile(self.path) as archive:
            self.assertEqual(archive.namelist(), ["manifest.json"])
            self.assertNotIn(b"SYNTHETIC-FAKE-IMAGE", archive.read("manifest.json"))
        reopened = load_project(self.path)
        self.assertEqual(reopened.assets, {})

        self.assertTrue(editor.undo())
        project.report = editor.report
        save_project(project, self.path)
        self.assertEqual(load_project(self.path).assets, project.assets)

        self.assertTrue(editor.redo())
        project.report = editor.report
        save_project(project, self.path)
        self.assertEqual(load_project(self.path).assets, {})

    def test_f01_parent_deletion_and_duplicate_shared_asset_lifecycle(self):
        project = example()
        editor = ProjectEditor(project.report)
        parent_id = editor.report.modules[0].id
        clone_id = editor.duplicate_module(parent_id)
        project.report = editor.report
        save_project(project, self.path)
        self.assertEqual(load_project(self.path).assets, project.assets)

        editor.remove_module(parent_id)
        project.report = editor.report
        save_project(project, self.path)
        self.assertEqual(load_project(self.path).assets, project.assets)
        self.assertEqual(module_outline(project.report)[0].module_id, clone_id)

        editor.remove_module(clone_id)
        project.report = editor.report
        save_project(project, self.path)
        self.assertEqual(load_project(self.path).assets, {})
        with ZipFile(self.path) as archive:
            self.assertNotIn("assets/photo-1", archive.namelist())

        self.assertTrue(editor.undo())
        project.report = editor.report
        save_project(project, self.path)
        self.assertEqual(load_project(self.path).assets, project.assets)

    def test_f01_orphan_asset_and_legacy_v1_orphan_are_scrubbed(self):
        project = example()
        unused = b"NOT-TO-BE-EXPORTED-SYNTHETIC-IMAGE"
        project.assets["obsolete"] = unused
        save_project(project, self.path)
        with ZipFile(self.path) as archive:
            self.assertNotIn("assets/obsolete", archive.namelist())
        self.assertNotIn("obsolete", load_project(self.path).assets)

        # Earlier M2 v1 projects might already include unreferenced assets.
        # Continue to open them for compatibility, but discard orphan bytes.
        with ZipFile(self.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            original_image = archive.read("assets/photo-1")
        # Construct an actual historical v1 manifest. New saves use v2,
        # where undeclared/orphan assets are intentionally forbidden.
        manifest["version"] = 1
        manifest.pop("media_library")
        # Reconstruct actual pre-v3 records, not a v3 manifest with a
        # version number changed: historical photo blocks had no visual key.
        def strip_visuals(module):
            for block in module["blocks"]:
                if block["kind"] in ("paragraph", "heading"):
                    block.pop("rich", None)
                if block["kind"] == "photo":
                    block.pop("visual", None)
                elif block["kind"] == "module":
                    strip_visuals(block["module"])
        for module in (*manifest["report"]["modules"], manifest["report"]["conclusion"]):
            strip_visuals(module)
        manifest["assets"].append({"id": "obsolete", "length": len(unused),
                                   "sha256": sha256(unused).hexdigest()})
        with ZipFile(self.path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("assets/photo-1", original_image)
            archive.writestr("assets/obsolete", unused)
        imported = load_project(self.path)
        self.assertEqual(set(imported.assets), {"photo-1"})
        source_v1 = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Save As"):
            save_project(imported, self.path)
        self.assertEqual(self.path.read_bytes(), source_v1)
        upgraded = self.path.with_name("migrated.rmproj")
        save_project(imported, upgraded)
        with ZipFile(upgraded) as archive:
            self.assertEqual(set(archive.namelist()), {"manifest.json", "assets/photo-1"})

    def test_f02_invalid_mutations_leave_undo_and_source_unchanged(self):
        project = example()
        editor = ProjectEditor(project.report)
        original = deepcopy(editor.report)
        target = editor.report.modules[0].id

        invalid_edits = [
            lambda r: setattr(r, "ticket", 123),
            lambda r: setattr(r, "title", None),
            lambda r: setattr(r, "start_date", "2026-10-25"),
            lambda r: setattr(r, "created_date", None),
            lambda r: setattr(r, "output_languages", ["de", 1]),
            lambda r: setattr(r, "customer_id", ["not-an-id"]),
            lambda r: setattr(r.modules[0].title, "original", None),
            lambda r: r.modules[0].title.translations.update({"de": 19}),
            lambda r: r.modules[0].title.stale_languages.add("fr"),
            lambda r: setattr(r.modules[0].blocks[1].module.blocks[1], "asset_id", "../unsafe"),
            lambda r: setattr(r.modules[0].blocks[1].module.blocks[2].rows[0][0],
                              "original", ["invalid"]),
        ]
        for change in invalid_edits:
            with self.subTest(change=invalid_edits.index(change)):
                with self.assertRaises(ValueError):
                    editor.apply(change)
                self.assertEqual(editor.report, original)
                self.assertFalse(editor.can_undo)
                self.assertFalse(editor.can_redo)
        with self.assertRaises(ValueError):
            editor.rename_module(target, None)
        self.assertEqual(editor.report, original)
        self.assertEqual(module_outline(editor.report)[0].title, "Linea")

    def test_f02_invalid_save_preserves_last_good_file(self):
        project = example()
        save_project(project, self.path)
        baseline = self.path.read_bytes()
        for value in (123, None, {"unexpected": "mapping"}):
            project.report.ticket = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                save_project(project, self.path)
            self.assertEqual(self.path.read_bytes(), baseline)
            self.assertEqual(load_project(self.path).report.ticket, "SYN-777")

    def test_f02_accepted_editor_mutation_roundtrips_exactly(self):
        project = example()
        editor = ProjectEditor(project.report)
        editor.apply(lambda r: setattr(r, "ticket", "SYN-888"))
        title = editor.report.modules[0].id
        editor.rename_module(title, "Retested line")
        editor.apply(lambda r: r.modules[0].title.set_translation("fr-CA", "Ligne test"))
        project.report = editor.report
        save_project(project, self.path)
        reopened = load_project(self.path)
        self.assertEqual(reopened.report, editor.report)
        self.assertEqual(reopened.assets, project.assets)

    def test_f03_unsupported_zip_compression_becomes_value_error(self):
        save_project(example(), self.path)
        with ZipFile(self.path) as archive:
            manifest = archive.read("manifest.json")
            image = archive.read("assets/photo-1")
        # bzip2 is a recognized stdlib ZIP method, deliberately not part of v1.
        with ZipFile(self.path, "w") as archive:
            archive.writestr("manifest.json", manifest, compress_type=ZIP_BZIP2)
            archive.writestr("assets/photo-1", image)
        with self.assertRaisesRegex(ValueError, "Unsupported ZIP compression"):
            load_project(self.path)

        # An *unknown* method number also cannot escape as NotImplementedError.
        with ZipFile(self.path, "w") as archive:
            archive.writestr("manifest.json", manifest, compress_type=ZIP_STORED)
            archive.writestr("assets/photo-1", image, compress_type=ZIP_STORED)
        raw = bytearray(self.path.read_bytes())
        central = raw.index(bytes.fromhex("504b0102"))
        local = raw.index(bytes.fromhex("504b0304"))
        raw[central + 10:central + 12] = (99).to_bytes(2, "little")
        raw[local + 8:local + 10] = (99).to_bytes(2, "little")
        self.path.write_bytes(raw)
        with self.assertRaises(ValueError):
            load_project(self.path)

    def test_f03_corrupted_archive_and_backup_copy_recovery(self):
        project = example()
        save_project(project, self.path)
        backup = Path(self.temp.name) / "manually-saved-copy.rmproj"
        shutil.copy2(self.path, backup)
        self.path.write_bytes(b"simulated torn / damaged project")
        with self.assertRaises(ValueError):
            load_project(self.path)
        recovered = load_project(backup)
        self.assertEqual(recovered.report, project.report)
        self.assertEqual(recovered.assets, project.assets)
        # Atomic save remains able to replace damaged files with valid content.
        save_project(recovered, self.path)
        self.assertEqual(load_project(self.path).report, project.report)
