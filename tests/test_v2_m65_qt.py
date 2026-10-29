"""Offscreen Qt M6.5 UI and proof integration on fabricated report data."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

from reportmaker.v2.localized_export import localized_fields
from test_v2_m65_integration import locale_project, approve_all


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Run on GitHub-hosted Windows Qt offscreen gate")
class M65QtIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_applies_metadata_command_and_prevents_draft_loss(self):
        from reportmaker.v2.commands import CommandGateway
        from reportmaker.v2.metadata_translation_dialog import MetadataTranslationDialog
        from reportmaker.v2.session import ReportSession
        session = ReportSession(locale_project())
        gateway = CommandGateway(session)
        dialog = MetadataTranslationDialog(session, gateway)
        try:
            index = dialog._keys.index("field.customer")
            dialog.fields.setCurrentRow(index)
            dialog.language.setCurrentIndex(dialog.language.findData("de"))
            self.app.processEvents()
            self.assertEqual(dialog._key, "field.customer")
            dialog.translation.setPlainText("Kunde")
            self.assertTrue(dialog._has_draft())
            dialog.fields.setCurrentRow(dialog._keys.index("field.created"))
            self.assertEqual(dialog._key, "field.customer")
            self.assertEqual(dialog.fields.currentRow(), index)
            self.assertTrue(dialog.apply_field())
            self.assertEqual(session.revision, 1)
            self.assertEqual(session.report_snapshot().localization_ledger[
                "field.customer"]["de"]["text"], "Kunde")
            self.assertFalse(dialog._has_draft())
            self.assertTrue(gateway.undo(session.generation, session.revision))
            self.assertEqual(session.report_snapshot().localization_ledger, {})
        finally:
            dialog.close()

    def test_preview_shows_same_localized_heading_and_page_proof(self):
        from PySide6.QtWidgets import QLabel
        from reportmaker.v2.preview_tab import PreviewTab
        from reportmaker.v2.session import ReportSession
        project = locale_project()
        for _, value in localized_fields(project.report):
            if value.original.strip():
                value.set_translation("de", "Translated " + value.original)
        approve_all(project.report, "de", preview=True)
        preview = PreviewTab(ReportSession(project))
        try:
            index = preview.language.findData("de")
            self.assertGreaterEqual(index, 0)
            preview.language.setCurrentIndex(index)
            preview.refresh()
            self.app.processEvents()
            texts = [label.text() for label in preview.scroll.widget().findChildren(QLabel)]
            self.assertIn("Translated Report information", texts)
            self.assertIn(
                "Translated Summary · Translated derived from the report hierarchy",
                texts)
            with TemporaryDirectory() as directory:
                path = Path(directory) / "de.pdf"
                self.assertTrue(preview.export_to(path, "pdf"),
                                preview.notice.text())
                self.assertTrue(path.read_bytes().startswith(b"%PDF"))
                self.assertTrue(preview.show_pdf_proof(),
                                preview.notice.text())
                self.assertTrue(preview.proof.is_current)
                self.assertGreater(preview.proof.page_count, 0)
        finally:
            preview.close()


if __name__ == "__main__":
    unittest.main()
