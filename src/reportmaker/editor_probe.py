"""Offline M3 Windows GUI smoke with synthetic reports only."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QIODevice, QSettings, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QListWidget, QPushButton, QMessageBox

from .engine import module_outline
from .model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, PhotoBlock, TableBlock
from .project_io import load_project
from .reference import manual_snapshot
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

            # M4.5: exercise the real picture manager offline with a synthetic
            # import, confirm external source bytes are never changed, and
            # verify unplaced library pictures survive project Save/Open.
            from PIL import Image as PILImage
            source = root / "synthetic-external.jpg"
            PILImage.new("RGB", (100, 60), "blue").save(source)
            source_bytes = source.read_bytes()
            def drive_picture_dialog(dialog):
                import_button = dialog.findChild(QPushButton, "importProjectPicturesAction")
                assert import_button is not None
                import_button.click()
                library = dialog.findChild(QListWidget, "projectPictureLibrary")
                assert library is not None and library.count() == 1
                return QDialog.DialogCode.Accepted
            with patch.object(QFileDialog, "getOpenFileNames",
                              return_value=([str(source)], "")), \
                 patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Yes), \
                 patch.object(QDialog, "exec", drive_picture_dialog):
                assert doc.manage_pictures()
            assert source.read_bytes() == source_bytes
            assert len(doc.media_library) == 1
            assert doc.dirty
            assert doc.save_to_path(path)
            assert load_project(path).media_library == doc.media_library

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

            # M3-F01: real typed information must survive history navigation.
            doc._change(lambda: doc.editor.add_module(
                Module(LocalizedText("en", "History sentinel"))))
            assert len(doc.report.modules) == 2
            doc.tabs.setCurrentIndex(1)  # Report Information
            ticket = doc.info["ticket"]
            ticket.setFocus()
            QTest.keyClicks(ticket, "DRAFT-UNDO")
            assert doc._info_pending
            doc.undo()
            # Undo applies to the just-flushed ticket edit, not the module.
            assert doc.report.ticket == ""
            assert ticket.text() == ""
            assert len(doc.report.modules) == 2
            doc.redo()
            assert doc.report.ticket == "DRAFT-UNDO"
            doc.undo()
            assert doc.editor.can_redo
            ticket.setFocus()
            QTest.keyClicks(ticket, "DRAFT-REDO")
            assert doc._info_pending
            doc.redo()
            # A new pending edit invalidates redo, but cannot be lost.
            assert doc.report.ticket == "DRAFT-REDO"
            assert not doc.editor.can_redo

            # M3-F02: a pending *invalid* draft (even with dirty=False) can
            # always be discarded when closing/opening/creating a project.
            assert doc.save_to_path(path)
            assert not doc.dirty
            doc.types["other"].setChecked(True)
            assert doc._info_pending
            with patch.object(QMessageBox, "warning",
                              side_effect=AssertionError("Discard must not validate")), \
                 patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Discard) as question:
                assert doc._confirm_discard()
                assert question.call_count == 1
            assert doc.report.other_intervention_detail == ""
            doc._load_info()  # Discarded draft; reset widgets from current report.

            # M3-F03: hidden supplementary data must not cross manual
            # customer/site/machine identity changes.
            doc.editor.apply(lambda report: setattr(report, "customer_snapshot",
                manual_snapshot(
                    "Old Example Customer", customer_address="Old Example Address",
                    customer_email="old@example.invalid", site_name="Old Example Site",
                    site_contact="Old Example Contact", machine_name="Old Machine",
                    machine_serial="OLD-123")))
            doc.dirty = True
            doc.refresh()
            doc.info["customer"].setText("New Example Customer")
            doc._set_info_pending()
            assert doc.apply_info()
            snapshot = doc.report.customer_snapshot
            assert snapshot.customer_name == "New Example Customer"
            assert snapshot.customer_address == ""
            assert snapshot.customer_email == ""
            assert snapshot.site_contact == ""
            assert snapshot.machine_serial == ""

            doc.editor.apply(lambda report: setattr(report, "customer_snapshot",
                manual_snapshot(
                    "Keep Customer", customer_address="Preserved Address",
                    site_name="Old Site", site_contact="Do not retain",
                    machine_name="Old Machine", machine_serial="OLD-SERIAL")))
            doc.refresh()
            doc.info["site"].setText("New Site")
            doc._set_info_pending()
            assert doc.apply_info()
            snapshot = doc.report.customer_snapshot
            assert snapshot.customer_address == "Preserved Address"
            assert snapshot.site_contact == ""
            assert snapshot.machine_serial == ""

            doc.editor.apply(lambda report: setattr(report, "customer_snapshot",
                manual_snapshot(
                    "Keep Customer", customer_address="Preserved Address",
                    site_name="Keep Site", site_contact="Preserved Contact",
                    machine_name="Old Machine", machine_serial="OLD-SERIAL")))
            doc.refresh()
            doc.info["machine"].setText("New Machine")
            doc._set_info_pending()
            assert doc.apply_info()
            snapshot = doc.report.customer_snapshot
            assert snapshot.site_contact == "Preserved Contact"
            assert snapshot.machine_serial == ""
            assert doc.save_to_path(path)
            reopened = load_project(path)
            assert reopened.report.customer_snapshot.machine_serial == ""
            assert reopened.report.customer_snapshot.site_contact == "Preserved Contact"

            # M3-F04: the preview must display the Other type's specification.
            doc.types["other"].setChecked(True)
            doc.info["other"].setText("Synthetic operator verification")
            doc._set_info_pending()
            assert doc.apply_info()
            assert "Other intervention details: Synthetic operator verification" \
                in doc.preview.toPlainText()
            assert doc.save_to_path(path)
            assert load_project(path).report.other_intervention_detail == \
                "Synthetic operator verification"
        finally:
            doc.dirty = False
            window.close()
            app.processEvents()
    return 0
