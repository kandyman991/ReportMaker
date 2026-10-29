"""M4.5.2 synthetic, offline visual photo layer regression gates."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from reportmaker.engine import ProjectEditor, validate_report_tree
from reportmaker.export import ExportError, prepare_export
from reportmaker.model import (
    LocalizedText, PhotoBlock, PhotoMark, PhotoVisual,
    validate_photo_visual,
)
from reportmaker.project_io import ReportProject, load_project, save_project
from test_m4_export import synthetic_project


def photo(project):
    return project.report.modules[0].blocks[1].module.blocks[1]


def sample_mark(kind="arrow"):
    return PhotoMark(kind, .15, .2, .85, .78, color="#ff5533",
                     text=LocalizedText("it", "Valve 4") if kind in ("text", "callout") else None)


class M45VisualModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.path = self.dir / "report.rmproj"
        self.project = synthetic_project()

    def test_multilingual_marks_layout_and_crop_survive_save_open(self):
        target = photo(self.project)
        note = sample_mark("callout")
        note.text.set_translation("de", "Ventil 4")
        target.visual = PhotoVisual(crop=(.1,.12,.76,.67), rotation=90,
                                    straighten=5, flip_h=True, width_pct=66,
                                    alignment="right", marks=[sample_mark(), note])
        before_bytes = self.project.assets[target.asset_id]
        save_project(self.project, self.path)
        reopened = load_project(self.path)
        actual = photo(reopened)
        self.assertEqual(actual.visual, target.visual)
        self.assertEqual(reopened.assets[actual.asset_id], before_bytes)
        self.assertEqual(actual.visual.marks[1].text.translations["de"], "Ventil 4")
        actual.visual.marks[1].text.update_original("Valve 5")
        self.assertIn("de", actual.visual.marks[1].text.stale_languages)
        with ZipFile(self.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["version"], 5)
            self.assertNotIn("original_path", archive.read("manifest.json").decode())
        self.assertNotIn(b"Valve 4", before_bytes)

    def test_two_placements_share_image_bytes_but_not_edits(self):
        target = photo(self.project)
        duplicate = deepcopy(target)
        duplicate.id = "copy-photo-2"
        target.visual.marks.append(sample_mark("ellipse"))
        self.project.report.modules[1].blocks.append(duplicate)
        save_project(self.project, self.path)
        stored = load_project(self.path)
        first = photo(stored)
        second = stored.report.modules[1].blocks[-1]
        self.assertEqual(first.asset_id, second.asset_id)
        self.assertEqual(len(first.visual.marks), 1)
        self.assertEqual(second.visual.marks, [])
        with ZipFile(self.path) as bundle:
            self.assertEqual(bundle.namelist().count("assets/synthetic"), 1)

    def test_photo_visual_undo_redo_is_transactional(self):
        editor = ProjectEditor(self.project.report)
        original = deepcopy(photo(ReportProject(editor.report)).visual)
        def update(report):
            report.modules[0].blocks[1].module.blocks[1].visual.marks.append(
                sample_mark("text"))
        editor.apply(update)
        self.assertEqual(len(photo(ReportProject(editor.report)).visual.marks), 1)
        self.assertTrue(editor.undo())
        self.assertEqual(photo(ReportProject(editor.report)).visual, original)
        self.assertTrue(editor.redo())
        self.assertEqual(len(photo(ReportProject(editor.report)).visual.marks), 1)

    def test_invalid_annotation_rejected_without_save_clobber(self):
        save_project(self.project, self.path)
        baseline = self.path.read_bytes()
        for invalid in (
            PhotoVisual(crop=(.9, .1, .4, .7)),
            PhotoVisual(rotation=19),
            PhotoVisual(straighten=99),
            PhotoVisual(width_pct=101),
            PhotoVisual(marks=[PhotoMark("arrow", float("nan"), .2, .7, .8)]),
            PhotoVisual(marks=[PhotoMark("text", .1,.1,.2,.2)]),
            PhotoVisual(marks=[PhotoMark("pen", .1,.1,.2,.2,
                                         points=[(.1,.1)])]),
            PhotoVisual(marks=[PhotoMark("rectangle", .1,.2,.3,.4,
                                         color="javascript:alert(1)")]),
        ):
            with self.subTest(visual=repr(invalid)[:60]):
                photo(self.project).visual = invalid
                with self.assertRaises(ValueError):
                    save_project(self.project, self.path)
                self.assertEqual(self.path.read_bytes(), baseline)

    def test_schema_v2_opens_but_cannot_upgrade_in_place(self):
        save_project(self.project, self.path)
        with ZipFile(self.path) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            assets = {item.filename: bundle.read(item.filename)
                      for item in bundle.infolist() if item.filename.startswith("assets/")}
        manifest["version"] = 2
        manifest["report"].pop("localization_ledger")
        # Historical v2 files have no v3 visual layers OR v4 rich spans,
        # including in the mandatory Conclusions module.
        for module in manifest["report"]["modules"] + [manifest["report"]["conclusion"]]:
            def remove_visual(obj):
                for block in obj["blocks"]:
                    if block["kind"] in ("paragraph", "heading"):
                        block.pop("rich", None)
                    if block["kind"] == "photo":
                        block.pop("visual")
                    elif block["kind"] == "module":
                        remove_visual(block["module"])
            remove_visual(module)
        with ZipFile(self.path, "w", ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest))
            for name, blob in assets.items():
                bundle.writestr(name, blob)
        original = self.path.read_bytes()
        loaded = load_project(self.path)
        self.assertEqual(loaded.loaded_version, 2)
        self.assertEqual(photo(loaded).visual, PhotoVisual())
        with self.assertRaisesRegex(ValueError, "Save As"):
            save_project(loaded, self.path)
        self.assertEqual(self.path.read_bytes(), original)
        updated = self.dir / "copy-v3.rmproj"
        save_project(loaded, updated)
        self.assertEqual(load_project(updated).loaded_version, 5)

    def test_v3_missing_or_corrupt_visual_is_rejected(self):
        save_project(self.project, self.path)
        with ZipFile(self.path) as bundle:
            baseline = json.loads(bundle.read("manifest.json"))
            assets = {entry.filename: bundle.read(entry.filename)
                      for entry in bundle.infolist() if entry.filename.startswith("assets/")}
        for action in ("missing", "extra", "outside", "duplicated"):
            manifest = deepcopy(baseline)
            visual = manifest["report"]["modules"][0]["blocks"][1]["module"]["blocks"][1]["visual"]
            if action == "missing":
                del manifest["report"]["modules"][0]["blocks"][1]["module"]["blocks"][1]["visual"]
            elif action == "extra":
                visual["secret"] = "data"
            elif action == "outside":
                visual["crop"] = [-.1,0,1,1]
            else:
                item = json.loads(json.dumps(visual))
                item["marks"] = [
                    {"id":"f"*32,"kind":"line","x":.1,"y":.1,"x2":.8,"y2":.8,
                     "color":"#ffffff","thickness":3,"text":None,"points":[]}] * 2
                visual.update(item)
            with self.subTest(action=action):
                with ZipFile(self.path, "w", ZIP_DEFLATED) as bundle:
                    bundle.writestr("manifest.json", json.dumps(manifest))
                    for name, blob in assets.items():
                        bundle.writestr(name, blob)
                unchanged = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    load_project(self.path)
                self.assertEqual(self.path.read_bytes(), unchanged)

    def test_customer_export_fails_instead_of_silently_dropping_visible_marks(self):
        target = photo(self.project)
        target.visual.marks.append(sample_mark("text"))
        with self.assertRaisesRegex(ExportError, "M4.5.4"):
            prepare_export(self.project)
        target.visual = PhotoVisual()
        self.assertTrue(prepare_export(self.project).items)


class M45QtCompositionTests(unittest.TestCase):
    def test_transforms_and_annotations_render_without_mutating_image(self):
        try:
            from PySide6.QtGui import QImage
            from PySide6.QtWidgets import QApplication
            from reportmaker.photo_editor import render_photo
        except ImportError:
            self.skipTest("Desktop Qt is not installed")
        app = QApplication.instance() or QApplication([])
        raw = BytesIO()
        Image.new("RGB", (420, 240), (20, 60, 90)).save(raw, format="PNG")
        original = raw.getvalue()
        visual = PhotoVisual(crop=(.1,.05,.7,.7), rotation=90, flip_v=True,
                             straighten=4, marks=[sample_mark("arrow"),
                                                  sample_mark("callout")])
        result = render_photo(original, visual, 600)
        self.assertFalse(result.isNull())
        self.assertGreater(result.width(), 0)
        self.assertGreater(result.height(), 0)
        self.assertEqual(original, raw.getvalue())
        self.assertNotEqual(result.size(), QImage.fromData(original).size())


    def test_canvas_draw_arrow_cancel_and_dialog_undo_redo(self):
        try:
            from PySide6.QtCore import Qt, QPoint
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication
            from reportmaker.photo_editor import PictureEditorDialog
        except ImportError:
            self.skipTest("Desktop Qt is not installed")
        app = QApplication.instance() or QApplication([])
        buffer = BytesIO()
        Image.new("RGB", (480, 320), (34, 75, 112)).save(buffer, format="PNG")
        original = buffer.getvalue()
        source_visual = PhotoVisual()
        dialog = PictureEditorDialog(None, original, source_visual, "it")
        dialog.show()
        app.processEvents()
        dialog.tool_choice.setCurrentIndex(dialog.tool_choice.findData("arrow"))
        canvas = dialog.canvas
        r = canvas._display_rect
        self.assertGreater(r.width(), 100)
        a = QPoint(int(r.left() + r.width() * .2),
                   int(r.top() + r.height() * .2))
        b = QPoint(int(r.left() + r.width() * .7),
                   int(r.top() + r.height() * .65))
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=a)
        QTest.mouseMove(canvas, b)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=b)
        self.assertEqual([m.kind for m in dialog.visual.marks], ["arrow"])
        self.assertEqual(source_visual, PhotoVisual())
        self.assertGreater(dialog.visual.marks[0].x2,
                           dialog.visual.marks[0].x)
        dialog.undo()
        self.assertEqual(dialog.visual.marks, [])
        dialog.redo()
        self.assertEqual(len(dialog.visual.marks), 1)
        dialog.reject()
        self.assertEqual(source_visual, PhotoVisual())
        self.assertEqual(buffer.getvalue(), original)


if __name__ == "__main__":
    unittest.main()
