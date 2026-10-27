"""Synthetic PDF regression: paragraph border paint and canonical list numbering."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import re
import unittest

from pypdf import PdfReader

from reportmaker.export import _pdf_number_marker, export_project
from reportmaker.model import LocalizedText, ParagraphBlock
from reportmaker.rich_text import RichFormatting, ParagraphStyle
from test_m4_export import synthetic_project


def _body_text(reader):
    return "\n".join(page.extract_text() for page in reader.pages[1:])


class RichPdfFidelityTests(unittest.TestCase):
    def test_numbered_and_alphabetic_lists_reset_and_continue_between_blocks(self):
        project = synthetic_project()
        lines = [
            ("Decimal first", "decimal"),
            ("Decimal second", "decimal"),
            ("Text separator", "none"),
            ("Restart first", "decimal"),
            ("Restart second", "decimal"),
            ("Lower one", "lower-alpha"),
            ("Lower two", "lower-alpha"),
            ("Upper one", "upper-alpha"),
            ("Upper two", "upper-alpha"),
        ]
        text = "\n".join(label for label, _ in lines)
        paragraphs = []
        pos = 0
        for label, kind in lines:
            if kind != "none":
                paragraphs.append(ParagraphStyle(pos, list_kind=kind))
            pos += len(label) + 1
        module = project.report.modules[0]
        module.blocks[0] = ParagraphBlock(LocalizedText("it", text),
            rich=RichFormatting(paragraphs=paragraphs))
        module.blocks.insert(1, ParagraphBlock(LocalizedText("it", "Upper three\nPlain end"),
            rich=RichFormatting(paragraphs=[ParagraphStyle(0, list_kind="upper-alpha")])))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "numbering.pdf"
            export_project(project, path, format="pdf")
            body = _body_text(PdfReader(path))
        for label in ("1. Decimal first", "2. Decimal second",
                      "Text separator", "1. Restart first", "2. Restart second",
                      "a. Lower one", "b. Lower two", "A. Upper one",
                      "B. Upper two", "C. Upper three", "Plain end"):
            with self.subTest(label=label):
                self.assertIn(label, body)
        self.assertNotIn("1. Decimal second", body)
        self.assertNotIn("1. Upper two", body)

    def test_alphabetic_markers_continue_after_z(self):
        self.assertEqual(_pdf_number_marker("lower-alpha", 26), "z. ")
        self.assertEqual(_pdf_number_marker("lower-alpha", 27), "aa. ")
        self.assertEqual(_pdf_number_marker("upper-alpha", 52), "AZ. ")

    def test_styled_paragraph_border_is_drawn_as_pdf_rectangle(self):
        project = synthetic_project()
        paragraph = project.report.modules[0].blocks[0]
        self.assertIsInstance(paragraph, ParagraphBlock)
        paragraph.rich = RichFormatting(paragraphs=[
            ParagraphStyle(0, border=True, shading="#eef3fa")])
        with TemporaryDirectory() as directory:
            with_border = Path(directory) / "bordered.pdf"
            without_border = Path(directory) / "unbordered.pdf"
            export_project(project, with_border, format="pdf")
            paragraph.rich.paragraphs[0].border = False
            export_project(project, without_border, format="pdf")
            def painted_border(path):
                reader = PdfReader(path)
                body = "\n".join(
                    page.get_contents().get_data().decode("latin1")
                    for page in reader.pages[1:])
                return len(re.findall(r"(?m)\\.75 w\\s+n [^\\n]+ re S", body))
            self.assertGreater(painted_border(with_border), painted_border(without_border))
            self.assertIn("Verifica avviata", _body_text(PdfReader(with_border)))


if __name__ == "__main__":
    unittest.main()
