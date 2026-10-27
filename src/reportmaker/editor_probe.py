"""Offline M3 Windows GUI smoke with synthetic reports only."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
import json
import faulthandler
import os
import threading
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QIODevice, QSettings, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QFileDialog, QListWidget, QPushButton, QMessageBox, QWidget

from .engine import module_outline
from .model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, PhotoBlock, PhotoMark, TableBlock
from .project_io import load_project
from .reference import manual_snapshot
from .ui import MainWindow


def run() -> int:
    # On a blocking Qt dialog/reentrant rich-text event, dump the CI Python
    # stack and exit. A never-ending GUI probe must not exhaust Windows runners.
    def report_hang():
        faulthandler.dump_traceback(all_threads=True)
        os._exit(62)
    watchdog = threading.Timer(60, report_hang)
    watchdog.daemon = True
    watchdog.start()
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
        # Catch accidental blocking alert dialogs in CI instead of hanging indefinitely.
        unforeseen_warning = patch.object(QMessageBox, "warning",
                                         side_effect=AssertionError("Unexpected Qt warning during rich-editor smoke"))
        unforeseen_warning.start()
        try:
            # RC1 installed-Windows finding: native dark theme used near-black
            # report text over a near-black QTextBrowser background.
            assert "background-color: #ffffff" in doc.preview.styleSheet()
            assert doc.preview.findChild(QPushButton, "previewZoomIn") is None  # sibling controls
            assert doc.owner.findChild(QPushButton, "previewZoomIn") is not None
            # Qt normalizes HTML and may omit the inline body style from toHtml().
            # The actual viewport-pixel assertion below is the reliable contract.
            app.processEvents()
            captured = doc.preview.viewport().grab().toImage()
            paper = captured.pixelColor(captured.width() - 5, captured.height() - 5)
            assert min(paper.red(), paper.green(), paper.blue()) >= 230, paper.name()
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

            # M4.5.2: invoke native PictureEditorDialog through the selected
            # PhotoBlock. It edits only placement instructions, never bytes.
            from .photo_editor import PictureEditorDialog, render_photo
            current_photo = next(b for b in doc.report.modules[0].blocks
                                 if isinstance(b, PhotoBlock))
            doc._module_id = doc.report.modules[0].id
            doc._edit_block_id = current_photo.id
            original_bytes = doc.assets["synthetic-image"]
            def accept_visual(dialog):
                assert isinstance(dialog, PictureEditorDialog)
                assert dialog.findChild(QWidget, "pictureEditorCanvas") is not None
                dialog.change_property("rotation", 90)
                dialog.change_property("width_pct", 70)
                dialog.visual.marks.append(PhotoMark("arrow", .1,.1,.8,.8))
                dialog.changed()
                return QDialog.DialogCode.Accepted
            with patch.object(PictureEditorDialog, "exec", accept_visual):
                assert doc.edit_picture()
            assert doc.assets["synthetic-image"] == original_bytes
            edited = next(b for b in doc.report.modules[0].blocks
                          if isinstance(b, PhotoBlock))
            assert edited.visual.rotation == 90
            assert len(edited.visual.marks) == 1
            assert not render_photo(original_bytes, edited.visual).isNull()
            assert doc.save_to_path(path)
            assert next(b for b in load_project(path).report.modules[0].blocks
                        if isinstance(b, PhotoBlock)).visual.rotation == 90
            doc.undo()
            assert next(b for b in doc.report.modules[0].blocks
                        if isinstance(b, PhotoBlock)).visual.rotation == 0
            doc.redo()
            assert next(b for b in doc.report.modules[0].blocks
                        if isinstance(b, PhotoBlock)).visual.rotation == 90

            # M4.5: exercise the real picture manager offline with a synthetic
            # import, confirm external source bytes are never changed, and
            # verify unplaced library pictures survive project Save/Open.
            from PIL import Image as PILImage
            source = root / "synthetic-external.jpg"
            PILImage.new("RGB", (100, 60), "blue").save(source)
            source_bytes = source.read_bytes()
            def drive_picture_dialog(dialog):
                if dialog.objectName() == "pictureImportComparisonDialog":
                    assert dialog.findChild(QComboBox, "pictureComparisonSelector") is not None
                    return QDialog.DialogCode.Accepted
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
            assert len(doc.media_library) == 1
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

            # M45-F02: a genuine v1 file stays byte-identical after the
            # native editor refuses Save; Save As creates an independent v2.
            legacy = root / "legacy-v1.rmproj"
            with ZipFile(path) as bundle:
                original_manifest = json.loads(bundle.read("manifest.json"))
                blobs = {name: bundle.read(name) for name in bundle.namelist()
                         if name.startswith("assets/")}
            original_manifest["version"] = 1
            original_manifest.pop("media_library")
            # Simulate a historical v1 file accurately, removing all v3
            # visual-layer keys rather than only changing the version tag.
            def strip_visuals(module):
                for entry in module["blocks"]:
                    if entry["kind"] in ("paragraph", "heading"):
                        entry.pop("rich", None)
                    if entry["kind"] == "photo":
                        entry.pop("visual", None)
                    elif entry["kind"] == "module":
                        strip_visuals(entry["module"])
            for module in (*original_manifest["report"]["modules"],
                           original_manifest["report"]["conclusion"]):
                strip_visuals(module)
            with ZipFile(legacy, "w", ZIP_DEFLATED) as bundle:
                bundle.writestr("manifest.json", json.dumps(original_manifest))
                for name, blob in blobs.items():
                    bundle.writestr(name, blob)
            original_v1 = legacy.read_bytes()
            assert doc.open_from_path(legacy)
            with patch.object(QMessageBox, "warning",
                              return_value=QMessageBox.StandardButton.Ok):
                assert not doc.save_to_path(legacy)
            assert legacy.read_bytes() == original_v1
            upgraded = root / "independent-upgraded-copy.rmproj"
            assert doc.save_to_path(upgraded)
            assert legacy.read_bytes() == original_v1
            assert load_project(upgraded).loaded_version == 4
        finally:
            unforeseen_warning.stop()
            doc.dirty = False
            window.close()
            app.processEvents()
    watchdog.cancel()
    return 0
