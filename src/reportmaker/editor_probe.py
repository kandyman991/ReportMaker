"""Offline M3 Windows GUI smoke with synthetic reports only."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QIODevice, QSettings, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QApplication, QMessageBox

from .engine import module_outline
from .model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, PhotoBlock, TableBlock
from .project_io import load_project
from .ui import MainWindow


def run() -> int:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="reportmaker-m3-") as directory:
        root = Path(directory)
        window = MainWindow(
            load_website=False,
            settings=QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat),
            ephemeral_browser=True,
        )
        window.show()
        app.processEvents()
        doc = window.document
        try:
            report = doc.report
            parent_id = report.modules[0].id
            nested = Module(LocalizedText("en", "Nested synthetic inspection"), [
                ParagraphBlock(LocalizedText("en", "M3 nested paragraph")),
                TableBlock([[LocalizedText("en", "Cell")]]),
            ])
            doc._change(lambda: doc.editor.add_module(nested, parent_id=parent_id))
            entries = module_outline(doc.report)
            assert entries[1].number == "1.1"
            assert entries[-1].is_conclusion
            assert "Nested synthetic inspection" in doc.summary.toPlainText()
            assert "M3 nested paragraph" in doc.preview.toPlainText()

            # A mixed order of nested modules and other blocks remains intact.
            doc._change(lambda: doc.editor.move_module(nested.id, index=0))
            assert doc.report.modules[0].id == nested.id
            doc._change(lambda: doc.editor.move_module(nested.id, parent_id=parent_id))
            assert isinstance(doc.report.modules[0].blocks[-1], NestedModuleBlock)

            # Real synthetic PNG bytes, never customer or external photographs.
            image = QImage(2, 2, QImage.Format.Format_RGB32)
            image.fill(0x00FFAA)
            buffer = QBuffer()
            assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            assert image.save(buffer, "PNG")
            doc.assets["synthetic-image"] = bytes(buffer.data())
            doc._change(lambda: doc.editor.add_block(
                parent_id, PhotoBlock("synthetic-image",
                                      LocalizedText("en", "Synthetic photo"))))
            assert not doc.preview.document().resource(
                QTextDocument.ResourceType.ImageResource,
                QUrl("rmasset:synthetic-image")
            ) is None
            doc._module_id = parent_id
            doc.refresh()
            doc.add_paragraph()
            doc.text_edit.setPlainText("Approved synthetic field notes")
            assert doc.apply_block()
            assert "Approved synthetic field notes" in doc.preview.toPlainText()

            # Metadata edits are captured on Save, including multiple types.
            doc.info["customer"].setText("Sample Factory")
            doc._set_info_pending()
            doc.types["supervision"].setChecked(True)
            doc.types["extraordinary_maintenance"].setChecked(True)
            path = root / "project.rmproj"
            assert doc.save_to_path(path)
            saved = load_project(path)
            assert saved.report.customer_snapshot.customer_name == "Sample Factory"
            assert saved.report.intervention_types == [
                "supervision", "extraordinary_maintenance",
            ]
            assert saved.report.modules[0].blocks[-1].text.original == "Approved synthetic field notes"
            assert saved.assets["synthetic-image"] == bytes(buffer.data())
            assert not doc.dirty

            doc.editor.add_module(Module(LocalizedText("en", "Unsaved")))
            doc.dirty = True
            doc.refresh()
            assert doc.open_from_path(path)
            assert not doc.dirty
            assert len(doc.report.modules) == 1

            # Malformed file cannot replace existing work.
            broken = root / "broken.rmproj"
            broken.write_bytes(b"corrupted")
            stable_id = doc.report.id
            with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok):
                assert not doc.open_from_path(broken)
            assert doc.report.id == stable_id
            assert doc.path == path

            # Invalid metadata blocks Save; the original project bytes survive.
            existing = path.read_bytes()
            doc.types["other"].setChecked(True)
            with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok):
                assert not doc.save_to_path(path)
            assert path.read_bytes() == existing
            doc.types["other"].setChecked(False)
            assert doc.save_to_path(path)
        finally:
            doc.dirty = False
            window.close()
            app.processEvents()
    return 0
