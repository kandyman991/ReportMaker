"""Synthetic rich ribbon, typography persistence and export regression gates."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
import json
import unittest

from reportmaker.model import ParagraphBlock, LocalizedText
from reportmaker.engine import ProjectEditor
from reportmaker.rich_text import (
    RichFormatting, TextRun, ParagraphStyle, validate_rich, safe_html)
from reportmaker.project_io import ReportProject, save_project, load_project
from reportmaker.export import export_project
from test_m4_export import synthetic_project


class RichModelTests(unittest.TestCase):
    def test_source_text_is_single_canonical_wording_with_emoji_offsets(self):
        text = "A😀nálise\nValve replacement"
        format = RichFormatting(
            runs=[TextRun(1, 3, family="Cambria", size=14.0,
                          bold=True, underline=True, color="#1166aa"),
                  TextRun(8, 13, italic=True, highlight="#ffff00")],
            paragraphs=[ParagraphStyle(0, align="justify", line_height=1.5),
                        ParagraphStyle(text.index("\n") + 1, align="right", indent=2)])
        validate_rich(format, text)
        html = safe_html(text, format)
        self.assertIn("font-weight:bold", html)
        self.assertIn("text-align:right", html)
        self.assertIn("😀", html)
        target = synthetic_project()
        block = next(x for x in target.report.modules[0].blocks
                     if isinstance(x, ParagraphBlock))
        block.text.update_original(text)
        block.rich = deepcopy(format)
        with TemporaryDirectory() as d:
            file = Path(d) / "format.rmproj"
            save_project(target, file)
            reloaded = load_project(file)
            result = next(x for x in reloaded.report.modules[0].blocks
                          if isinstance(x, ParagraphBlock))
            self.assertEqual(result.text.original, text)
            self.assertEqual(result.rich, format)
            self.assertEqual(reloaded.loaded_version, 4)

    def test_tampered_format_ranges_rejected_atomically(self):
        project = synthetic_project()
        block = next(x for x in project.report.modules[0].blocks
                     if isinstance(x, ParagraphBlock))
        with TemporaryDirectory() as d:
            file = Path(d) / "kept.rmproj"
            save_project(project, file)
            good = file.read_bytes()
            for entry in [
                TextRun(0, len(block.text.original)+1),
                TextRun(0, 1, size=99),
                TextRun(0, 1, family="invalid\nfamily"),
                TextRun(0, 1, color="url(https://example.org)"),
                TextRun(True, 1),
                TextRun(0, 1, bold="yes"),
            ]:
                block.rich = RichFormatting(runs=[entry])
                with self.subTest(entry=repr(entry)):
                    with self.assertRaises(ValueError):
                        save_project(project, file)
                    self.assertEqual(file.read_bytes(), good)

    def test_legacy_v3_opens_and_keeps_original_during_v4_upgrade(self):
        project = synthetic_project()
        with TemporaryDirectory() as d:
            file = Path(d) / "old-v3.rmproj"
            save_project(project, file)
            with ZipFile(file) as source:
                manifest = json.loads(source.read("manifest.json"))
                blobs = {i.filename: source.read(i.filename) for i in source.infolist()
                         if i.filename.startswith("assets/")}
            manifest["version"] = 3
            def remove_rich(module):
                for item in module["blocks"]:
                    if item["kind"] in ("paragraph", "heading"):
                        item.pop("rich", None)
                    if item["kind"] == "module":
                        remove_rich(item["module"])
            for module in manifest["report"]["modules"] + [manifest["report"]["conclusion"]]:
                remove_rich(module)
            with ZipFile(file, "w", ZIP_DEFLATED) as target:
                target.writestr("manifest.json", json.dumps(manifest))
                for name, data in blobs.items():
                    target.writestr(name, data)
            prior = file.read_bytes()
            loaded = load_project(file)
            self.assertEqual(loaded.loaded_version, 3)
            with self.assertRaisesRegex(ValueError, "Save As"):
                save_project(loaded, file)
            self.assertEqual(file.read_bytes(), prior)
            upgraded = Path(d) / "new-v4.rmproj"
            save_project(loaded, upgraded)
            self.assertEqual(load_project(upgraded).loaded_version, 4)

    def test_project_history_restores_original_formatting(self):
        project = synthetic_project()
        editor = ProjectEditor(project.report)
        def change(report):
            block = next(x for x in report.modules[0].blocks
                         if isinstance(x, ParagraphBlock))
            block.rich = RichFormatting(runs=[TextRun(0, 4, bold=True)])
        editor.apply(change)
        self.assertTrue(editor.undo())
        block = next(x for x in editor.report.modules[0].blocks if isinstance(x, ParagraphBlock))
        self.assertFalse(block.rich.runs)
        self.assertTrue(editor.redo())
        block = next(x for x in editor.report.modules[0].blocks if isinstance(x, ParagraphBlock))
        self.assertTrue(block.rich.runs[0].bold)

    def test_docx_runs_remain_editable_with_formatted_size_and_color(self):
        from docx import Document
        project = synthetic_project()
        block = next(x for x in project.report.modules[0].blocks
                     if isinstance(x, ParagraphBlock))
        block.text.update_original("Formatted valve")
        block.rich = RichFormatting(runs=[TextRun(0, 9, bold=True, size=16.0,
                                                 color="#336699")])
        with TemporaryDirectory() as d:
            file = Path(d) / "report.docx"
            export_project(project, file, format="docx")
            doc = Document(file)
            paragraph = next(p for p in doc.paragraphs if "Formatted valve" in p.text)
            self.assertIn("Formatted valve", paragraph.text)
            self.assertTrue(paragraph.runs[0].bold)
            self.assertAlmostEqual(paragraph.runs[0].font.size.pt, 16)

class RichQtTests(unittest.TestCase):
    def test_ribbon_selection_formatting_roundtrip(self):
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QTextCursor
            from PySide6.QtWidgets import QApplication, QPushButton
            from reportmaker.rich_editor import SafeRichTextEdit, RichTextRibbon, apply_rich, capture_rich
        except ImportError:
            self.skipTest("Desktop PySide6 not available")
        app = QApplication.instance() or QApplication([])
        editor = SafeRichTextEdit()
        ribbon = RichTextRibbon(editor)
        source = "Valve 😀 position\nReplace gasket"
        apply_rich(editor, source, RichFormatting())
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        ribbon.findChild(QPushButton, "richBold").click()
        ribbon.findChild(QPushButton, "richUnderline").click()
        content, rich = capture_rich(editor)
        self.assertEqual(content, source)
        self.assertTrue(any(r.bold for r in rich.runs))
        self.assertTrue(any(r.underline for r in rich.runs))
        clone = SafeRichTextEdit()
        apply_rich(clone, content, rich)
        same_text, same_format = capture_rich(clone)
        self.assertEqual(same_text, source)
        self.assertTrue(any(r.bold and r.underline for r in same_format.runs))
        self.assertEqual(clone.toPlainText(), source)

if __name__ == "__main__":
    unittest.main()
