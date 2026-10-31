"""Phase 1 compact golden contract: synthetic project -> archive -> editable exports.

No production data, network, external original modification, or GUI requirement.
Complements the detailed M2/M4/M6 and V2 migration tests; not a visual proof.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from docx import Document
from PIL import Image
from pypdf import PdfReader

from reportmaker.engine import module_outline
from reportmaker.export import export_project, prepare_export
from reportmaker.model import (
    LocalizedText, Module, NestedModuleBlock, ParagraphBlock, PhotoBlock, Report,
    TableBlock,
)
from reportmaker.project_io import VERSION, ReportProject, load_project, save_project
from reportmaker.reference import manual_snapshot


def localized(source: str) -> LocalizedText:
    value = LocalizedText("it", source)
    value.set_translation("de", "DE " + source)
    return value


def golden_project(image: bytes) -> ReportProject:
    note = localized("Stato iniziale")
    note.update_original("Stato verificato")  # German translation deliberately stale.
    nested = Module(localized("Ispezione"), [
        ParagraphBlock(note),
        PhotoBlock("placed", localized("Foto sintetica")),
        TableBlock([[localized("Voce"), localized("Valore")],
                    [localized("Pressione"), localized("OK")]]),
    ])
    root = Module(localized("Linea"), [NestedModuleBlock(nested)])
    report = Report(
        customer_id=None, customer_snapshot=manual_snapshot(
            "Synthetic Customer", site_name="Demo Site",
            machine_serial="TEST-0001"),
        created_date=date(2026, 10, 31),
        start_date=date(2026, 10, 30), end_date=date(2026, 10, 31),
        primary_language="it", output_languages=["it", "de"],
        title=localized("Rapporto tecnico"), ticket="TEST-123",
        intervention_types=["supervision", "other"],
        other_intervention_detail="Synthetic review",
        modules=[root],
        conclusion=Module(localized("Conclusioni"),
                          [ParagraphBlock(localized("Controllo concluso"))]),
    )
    return ReportProject(report, {"placed": image, "gallery": image},
                         media_library={"gallery": "Unused synthetic image"})


class Phase1GoldenContractTests(unittest.TestCase):
    def test_project_roundtrip_and_derived_export_without_touching_original(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            original = folder / "external-original.png"
            image = Image.new("RGB", (16, 12), (20, 80, 140))
            memory = BytesIO()
            image.save(memory, format="PNG")
            original.write_bytes(memory.getvalue())
            before_original = original.read_bytes()
            project = golden_project(before_original)

            first = folder / "golden.rmproj"
            save_project(project, first)
            loaded = load_project(first)
            self.assertEqual(loaded.report, project.report)
            self.assertEqual(loaded.report.customer_snapshot.customer_name,
                             "Synthetic Customer")
            self.assertIsNone(loaded.report.customer_snapshot.customer_id)
            self.assertEqual(loaded.report.intervention_types, ["supervision", "other"])
            self.assertEqual(loaded.report.output_languages, ["it", "de"])
            self.assertEqual(loaded.media_library, {"gallery": "Unused synthetic image"})
            self.assertEqual(loaded.assets, project.assets)
            child = loaded.report.modules[0].blocks[0].module
            self.assertEqual(child.blocks[0].text.stale_languages, {"de"})
            self.assertEqual(child.blocks[1].asset_id, "placed")
            self.assertIs(loaded.report.ordered_sections()[-1], loaded.report.conclusion)

            outline = module_outline(loaded.report)
            self.assertEqual([(x.number, x.title) for x in outline],
                             [("1", "Linea"), ("1.1", "Ispezione"),
                              ("", "Conclusioni")])
            self.assertEqual(prepare_export(loaded).outline, outline)
            with ZipFile(first) as archive:
                members = set(archive.namelist())
                self.assertEqual(members, {"manifest.json", "assets/placed", "assets/gallery"})
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["version"], VERSION)
                self.assertNotIn("summary", manifest["report"])

            unchanged = deepcopy(loaded.report)
            word = folder / "export.docx"
            pdf = folder / "export.pdf"
            export_project(loaded, word, format="docx")
            export_project(loaded, pdf, format="pdf")
            self.assertEqual(loaded.report, unchanged)
            word_text = "\n".join(p.text for p in Document(word).paragraphs)
            self.assertIn("1.1 Ispezione", word_text)
            self.assertIn("Controllo concluso", word_text)
            pdf_text = "\n".join(p.extract_text() or "" for p in PdfReader(pdf).pages)
            self.assertIn("Ispezione", pdf_text)
            self.assertIn("Controllo concluso", pdf_text)

            second = folder / "saved-again.rmproj"
            save_project(loaded, second)
            reloaded = load_project(second)
            self.assertEqual(reloaded.report, loaded.report)
            self.assertEqual(reloaded.media_library, loaded.media_library)
            self.assertEqual(reloaded.assets, loaded.assets)
            self.assertEqual(original.read_bytes(), before_original)


if __name__ == "__main__":
    unittest.main()
