"""Synthetic Explorer/clipboard photo import regressions for issue #48."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from PIL import Image
from PySide6.QtCore import QMimeData, QSettings, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from reportmaker.media_import import PictureImportError, convert_picture_bytes
from reportmaker.photo_gallery import (PHOTO_MIME, ProjectPictureList,
                                       local_picture_paths)
from reportmaker.project_io import load_project
from reportmaker.reference import manual_snapshot
from reportmaker.visual_editor import VisualReportEditor, new_report


class FakeDropEvent:
    def __init__(self, source, mime):
        self._source = source
        self._mime = mime
        self.accepted = False
        self.ignored = False

    def source(self):
        return self._source

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True

    def accept(self):
        self.accepted = True


class ExternalPhotoImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner = QMainWindow()
        self.owner.settings = QSettings(str(self.root / "prefs.ini"),
                                        QSettings.Format.IniFormat)
        host = QWidget()
        self.owner.setCentralWidget(host)
        horizontal = QHBoxLayout(host)
        left, center = QVBoxLayout(), QVBoxLayout()
        horizontal.addLayout(left)
        horizontal.addLayout(center)
        self.editor = VisualReportEditor(self.owner, left, center)
        self.editor.editor.apply(lambda report: setattr(
            report, "customer_snapshot", manual_snapshot("Synthetic customer")))
        self.editor.refresh()
        self.owner.show()
        self.assertTrue(self.editor.manage_pictures())
        self.app.processEvents()
        self.gallery = self.editor._picture_gallery
        self.pictures = self.gallery.findChild(ProjectPictureList, "projectPictureLibrary")
        self.paste = self.gallery.findChild(QPushButton, "pasteProjectPictureAction")
        self.status = self.gallery.findChild(QLabel, "pictureImportStatus")

    def tearDown(self):
        QApplication.clipboard().clear()
        if self.editor._picture_gallery:
            self.editor._picture_gallery.close()
        self.owner.close()
        self.app.processEvents()

    def image_file(self, name="synthetic.png"):
        path = self.root / name
        Image.new("RGB", (85, 49), (30, 120, 180)).save(path, "PNG")
        return path

    @staticmethod
    def url_mime(*paths):
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(x)) for x in paths])
        return data

    def test_mixed_explorer_drop_imports_valid_once_with_per_file_feedback(self):
        valid = self.image_file()
        duplicate = valid  # repeated OS file references are one import
        bad = self.root / "bad.png"
        bad.write_bytes(b"corrupt")
        unsupported = self.root / "notes.txt"
        unsupported.write_text("not an image")
        original = valid.read_bytes()
        mime = self.url_mime(valid, duplicate, bad, unsupported)
        with patch.object(QMessageBox, "warning") as warning:
            event = FakeDropEvent(None, mime)
            self.pictures.dragEnterEvent(event)
            self.assertTrue(event.accepted)
            self.pictures.dropEvent(event)
            self.app.processEvents()
            self.assertEqual(self.pictures.count(), 1)
            self.assertIn("Imported 1 picture", self.status.text())
            self.assertIn("2 failed", self.status.text())
            self.assertEqual(warning.call_count, 1)
            details = warning.call_args.args[-1]
            self.assertIn("bad.png", details)
            self.assertIn("notes.txt", details)
        self.assertEqual(valid.read_bytes(), original)
        self.assertEqual(len(self.editor.report.modules[0].blocks), 1)
        self.assertTrue(self.pictures.currentItem())
        key = self.pictures.currentItem().data(Qt.ItemDataRole.UserRole)
        self.assertIn(key, self.editor.media_library)
        dest = self.root / "portable.rmproj"
        self.assertTrue(self.editor.save_to_path(dest))
        valid.unlink()
        self.assertIn(key, load_project(dest).media_library)

    def test_clipboard_bitmap_paste_persists_without_report_insertion(self):
        shot = QImage(91, 47, QImage.Format.Format_ARGB32)
        shot.fill(QColor("#ff4488"))
        QApplication.clipboard().setImage(shot)
        self.app.processEvents()
        self.assertTrue(self.paste.isEnabled())
        self.paste.click()
        self.app.processEvents()
        self.assertEqual(self.pictures.count(), 1)
        self.assertEqual(len(self.editor.media_library), 1)
        self.assertEqual(len(self.editor.report.modules[0].blocks), 1)
        key = next(iter(self.editor.media_library))
        self.assertEqual(self.editor.media_library[key], "Clipboard image")
        dest = self.root / "clipboard.rmproj"
        self.assertTrue(self.editor.save_to_path(dest))
        loaded = load_project(dest)
        self.assertEqual(loaded.media_library[key], "Clipboard image")
        self.assertTrue(loaded.assets[key])
        self.assertTrue(self.gallery.findChildren(QShortcut))  # Ctrl+V discoverable

    def test_clipboard_file_list_takes_priority_over_attached_bitmap(self):
        file = self.image_file("explorer-image.png")
        mime = self.url_mime(file)
        shot = QImage(10, 10, QImage.Format.Format_RGB32)
        shot.fill(QColor("blue"))
        mime.setImageData(shot)
        QApplication.clipboard().setMimeData(mime)
        self.app.processEvents()
        self.assertTrue(self.paste.isEnabled())
        self.paste.click()
        self.app.processEvents()
        self.assertEqual(self.pictures.count(), 1)
        self.assertEqual(list(self.editor.media_library.values()), ["explorer-image"])

    def test_reject_web_urls_text_internal_ids_and_invalid_clipboard(self):
        valid = self.image_file()
        fake = self.url_mime(valid)
        fake.setData(PHOTO_MIME, b"forged-internal-asset")
        self.assertEqual(local_picture_paths(fake), ([], []))
        external = self.url_mime(valid)
        bad_event = FakeDropEvent(self.pictures, external)
        self.pictures.dragEnterEvent(bad_event)
        self.assertTrue(bad_event.ignored)
        self.pictures.dropEvent(bad_event)
        self.assertEqual(self.pictures.count(), 0)
        remote = QMimeData()
        remote.setUrls([QUrl("https://example.invalid/not-an-image.png")])
        self.assertEqual(local_picture_paths(remote)[0], [])
        self.pictures.dragEnterEvent(FakeDropEvent(None, remote))
        text = QMimeData()
        text.setHtml('<img src="https://example.invalid/x.png">')
        text.setText("https://example.invalid/x.png")
        QApplication.clipboard().setMimeData(text)
        self.app.processEvents()
        self.assertFalse(self.paste.isEnabled())
        self.assertEqual(self.pictures.count(), 0)

    def test_pending_edits_survive_import_and_stale_queued_drop_is_ignored(self):
        file = self.image_file()
        self.editor.text_edit.setPlainText("Pending synthetic paragraph")
        self.assertTrue(self.editor._block_pending)
        event = FakeDropEvent(None, self.url_mime(file))
        self.gallery.dragEnterEvent(event)
        self.assertTrue(event.accepted)
        self.gallery.dropEvent(event)
        self.app.processEvents()
        self.assertEqual(self.pictures.count(), 1)
        self.assertEqual(
            self.editor.report.modules[0].blocks[0].text.original,
            "Pending synthetic paragraph")
        self.assertFalse(self.editor._block_pending)

        # Even with a valid queued Explorer drop, switching projects wins.
        self.gallery.dropEvent(FakeDropEvent(None, self.url_mime(file)))
        self.editor._replace(new_report(), None)
        self.app.processEvents()
        self.assertEqual(self.editor.media_library, {})

    def test_encoded_clipboard_bytes_use_allowed_formats_and_decode_limits(self):
        png = BytesIO()
        Image.new("RGBA", (21, 19), (40, 80, 130, 120)).save(png, "PNG")
        converted = convert_picture_bytes(png.getvalue())
        self.assertEqual(converted.format, "png")
        self.assertEqual(converted.original_width, 21)
        self.assertEqual(converted.source_bytes, len(png.getvalue()))
        with self.assertRaises(PictureImportError):
            convert_picture_bytes(b"not an encoded image")
        with self.assertRaises(PictureImportError):
            convert_picture_bytes(b"x" * (64 * 1024 * 1024 + 1))
        tiff = BytesIO()
        Image.new("RGB", (12, 8)).save(tiff, "TIFF")
        with self.assertRaisesRegex(PictureImportError, "Unsupported image content"):
            convert_picture_bytes(tiff.getvalue())


if __name__ == "__main__":
    unittest.main()
