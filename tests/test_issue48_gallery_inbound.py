"""Issue #48: synthetic Explorer/clipboard inbound imports, no customer data."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from PIL import Image
from PySide6.QtCore import QByteArray, QMimeData, QSettings, Qt, QUrl
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                               QMainWindow, QPushButton, QVBoxLayout, QWidget)

from reportmaker.media_import import PictureImportError, convert_picture_bytes
from reportmaker.photo_gallery import (PHOTO_MIME, ProjectPictureList,
                                       can_paste_picture, clipboard_image_png,
                                       local_picture_urls)
from reportmaker.project_io import load_project
from reportmaker.reference import manual_snapshot
from reportmaker.visual_editor import VisualReportEditor


class FakeDrop:
    def __init__(self, mime, source=None):
        self._mime = mime
        self._source = source
        self.accepted = self.ignored = False
        self.action = None

    def mimeData(self):
        return self._mime

    def source(self):
        return self._source

    def possibleActions(self):
        return Qt.DropAction.CopyAction | Qt.DropAction.MoveAction

    def setDropAction(self, action):
        self.action = action

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


class InboundGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.owner = QMainWindow()
        self.owner.settings = QSettings(str(self.root / "inbound.ini"), QSettings.Format.IniFormat)
        container = QWidget()
        self.owner.setCentralWidget(container)
        sides = QHBoxLayout(container)
        left, center = QVBoxLayout(), QVBoxLayout()
        sides.addLayout(left)
        sides.addLayout(center)
        self.editor = VisualReportEditor(self.owner, left, center)
        self.editor.editor.apply(lambda report: setattr(
            report, "customer_snapshot", manual_snapshot("Synthetic customer")))
        self.editor.refresh()
        self.owner.show()
        self.app.processEvents()
        self.assertTrue(self.editor.manage_pictures())
        self.gallery = self.editor._picture_gallery
        self.pictures = self.gallery.findChild(ProjectPictureList, "projectPictureLibrary")
        self.paste = self.gallery.findChild(QPushButton, "pasteProjectPictureAction")
        self.status = self.gallery.findChild(QLabel, "pictureImportStatus")
        self.app.processEvents()

    def tearDown(self):
        QApplication.clipboard().clear()
        if self.editor._picture_gallery:
            self.editor._picture_gallery.close()
        self.owner.close()
        self.app.processEvents()
        self.folder.cleanup()

    def png(self, name="synthetic.png", color="green"):
        file = self.root / name
        Image.new("RGB", (85, 49), color).save(file)
        return file

    @staticmethod
    def url_mime(*urls):
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(p)) if isinstance(p, Path)
                      else QUrl(str(p)) for p in urls])
        return data

    def drop(self, mime):
        event = FakeDrop(mime)
        self.pictures.dragEnterEvent(event)
        if event.accepted:
            self.pictures.dropEvent(event)
            self.app.processEvents()  # queued callback; preview dialog is mocked
        return event

    def test_explorer_drop_single_import_save_reopen_preserves_original(self):
        source = self.png()
        original = source.read_bytes()
        before_blocks = len(self.editor.report.modules[0].blocks)
        self.editor.text_edit.setPlainText("Pending report draft must survive import")
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            event = self.drop(self.url_mime(source))
        self.assertTrue(event.accepted)
        self.assertEqual(event.action, Qt.DropAction.CopyAction)
        self.assertEqual(self.pictures.count(), 1)
        self.assertTrue(self.pictures.acceptDrops())
        self.assertEqual(len(self.editor.media_library), 1)
        self.assertEqual(len(self.editor.report.modules[0].blocks), before_blocks)
        self.assertEqual(self.editor.report.modules[0].blocks[0].text.original,
                         "Pending report draft must survive import")
        self.assertEqual(source.read_bytes(), original)
        target = self.root / "synthetic.rmproj"
        self.assertTrue(self.editor.save_to_path(target))
        restored = load_project(target)
        self.assertEqual(len(restored.media_library), 1)
        self.assertEqual(restored.assets, self.editor.assets)
        self.assertNotIn(str(self.root).encode(), target.read_bytes())
        self.assertTrue(self.editor.open_from_path(target))
        self.assertEqual(len(self.editor.media_library), 1)

    def test_mixed_drop_imports_valid_once_reports_bad_and_no_report_block(self):
        first = self.png("a.png")
        second = self.png("b.png", "purple")
        invalid = self.root / "notes.txt"
        invalid.write_text("not a picture")
        corrupt = self.root / "corrupt.jpg"
        corrupt.write_bytes(b"not a jpeg")
        before = len(self.editor.report.modules[0].blocks)
        errors = []
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
             patch.object(self.editor, "_warn", side_effect=lambda _title, reason: errors.append(str(reason))):
            event = self.drop(self.url_mime(first, first, invalid, corrupt,
                                                 "https://host.invalid/remote.png", second))
        self.assertTrue(event.accepted)
        self.assertEqual(self.pictures.count(), 2)
        self.assertEqual(len(self.editor.report.modules[0].blocks), before)
        self.assertIn("Imported 2", self.status.text())
        self.assertTrue(any("corrupt.jpg" in text for text in errors))
        self.assertTrue(any("Rejected remote" in text for text in errors))
        self.assertTrue(any("notes.txt" in text for text in errors))
        self.assertEqual(len(self.editor.media_library), 2)

    def test_drag_direction_and_untrusted_mime_are_separate(self):
        source = self.png()
        valid = self.url_mime(source)
        fake = self.url_mime(source)
        fake.setData(PHOTO_MIME, QByteArray(b"spoofed-id"))
        html = self.url_mime(source)
        html.setHtml('<img src="file:///synthetic.png">')
        with patch.object(self.editor, "_warn"):
            for bad in [fake, html, self.url_mime("https://example.com/image.png"),
                        self.url_mime("file://network-host/shared/test.png"),
                        QMimeData()]:
                event = self.drop(bad)
                self.assertEqual(event.accepted, bool(local_picture_urls(bad)[1]))
        self.assertEqual(len(self.editor.assets), 0)
        self.assertEqual(local_picture_urls(fake), ([], []))
        self.assertFalse(can_paste_picture(fake))
        self.assertTrue(local_picture_urls(valid)[0])

    def test_clipboard_bitmap_precedence_and_explicit_paste(self):
        source = self.png("on-disk.png")
        data = self.url_mime(source)
        image = QImage(44, 28, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.red)
        data.setImageData(image)
        data.setHtml("<img src=\"https://example.invalid/should-not-fetch.png\">")
        QApplication.clipboard().setMimeData(data)
        self.app.processEvents()
        self.assertTrue(self.paste.isEnabled())
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            self.paste.click()
        self.assertEqual(len(self.editor.media_library), 1)  # no URL double-import
        self.assertEqual(next(iter(self.editor.media_library.values()))[:12], "Pasted image")
        self.assertIn("Imported 1", self.status.text())
        target = self.root / "clipboard.rmproj"
        self.assertTrue(self.editor.save_to_path(target))
        self.assertEqual(len(load_project(target).media_library), 1)

    def test_clipboard_file_references_and_ctrl_v(self):
        source = self.png("file-copy.png")
        QApplication.clipboard().setMimeData(self.url_mime(source))
        self.app.processEvents()
        self.assertTrue(self.paste.isEnabled())
        self.gallery.activateWindow()
        self.pictures.setFocus()
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            QTest.keyClick(self.pictures, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
            self.app.processEvents()
        self.assertEqual(self.pictures.count(), 1)
        self.assertIn("file-copy", self.editor.media_library.values())
        self.assertEqual(len(self.editor.report.modules[0].blocks), 1)

    def test_explorer_move_only_action_is_rejected(self):
        event = FakeDrop(self.url_mime(self.png()))
        event.possibleActions = lambda: Qt.DropAction.MoveAction
        self.pictures.dragEnterEvent(event)
        self.assertTrue(event.ignored)
        self.assertFalse(event.accepted)
        self.assertEqual(len(self.editor.media_library), 0)

    def test_source_orientation_uses_shared_decoder(self):
        from reportmaker.media_import import convert_picture
        path = self.root / "rotated.jpg"
        Image.new("RGB", (120, 80), "blue").save(path, exif=Image.Exif())
        img = Image.open(path)
        exif = img.getexif()
        exif[274] = 6
        img.save(path, exif=exif)
        converted = convert_picture(path)
        self.assertEqual((converted.width, converted.height), (80, 120))
        self.assertEqual((converted.original_width, converted.original_height), (120, 80))

    def test_empty_html_and_bad_clipboard_no_import(self):
        for mime in [QMimeData(), self.url_mime("https://example.com/img.jpg")]:
            QApplication.clipboard().setMimeData(mime)
            self.app.processEvents()
            self.assertFalse(self.paste.isEnabled())
        html = QMimeData()
        html.setHtml('<img src="https://example.com/tracker">')
        QApplication.clipboard().setMimeData(html)
        self.app.processEvents()
        self.assertFalse(self.paste.isEnabled())
        bad = QMimeData()
        bad.setImageData(QImage())
        with self.assertRaises(PictureImportError):
            clipboard_image_png(bad)
        self.assertEqual(len(self.editor.media_library), 0)
        with self.assertRaises(PictureImportError):
            convert_picture_bytes(b"fake pixels")
        with patch("reportmaker.photo_gallery.MAX_CLIPBOARD_PIXELS", 10):
            large = QMimeData()
            image = QImage(4, 4, QImage.Format.Format_RGB32)
            large.setImageData(image)
            with self.assertRaises(PictureImportError):
                clipboard_image_png(large)

    def test_unresolved_page_draft_aborts_import_atomically(self):
        source = self.png()
        block = self.editor.report.modules[0].blocks[0]
        key = (self.editor.report.modules[0].id, block.id, "text")
        self.editor.page.fields[key].setPlainText("Pending unsaved page")
        self.assertIn(key, self.editor.page.pending)
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
             patch.object(self.editor, "_flush_page", return_value=False):
            self.drop(self.url_mime(source))
        self.assertEqual(len(self.editor.media_library), 0)
        self.assertIn(key, self.editor.page.pending)
        self.assertIn("pending", self.status.text())


if __name__ == "__main__":
    unittest.main()
