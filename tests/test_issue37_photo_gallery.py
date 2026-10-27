"""Synthetic Qt gallery/drop regressions for issue #37 (no customer photos)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
import unittest

from PIL import Image

from reportmaker.model import LocalizedText, Module, NestedModuleBlock, PhotoBlock
from reportmaker.photo_gallery import PHOTO_MIME, PictureDropZone, ProjectPictureList
from reportmaker.project_io import load_project
from reportmaker.reference import manual_snapshot
from reportmaker.visual_editor import VisualReportEditor, new_report


class FakeDragEvent:
    """Exercise Qt's actual drop handlers without a screen-dependent mouse."""
    def __init__(self, source, mime, position=None):
        from PySide6.QtCore import QPointF
        self._source = source
        self._mime = mime
        self._position = position or QPointF(5, 5)
        self.accepted = False
        self.ignored = False

    def source(self):
        return self._source

    def mimeData(self):
        return self._mime

    def position(self):
        return self._position

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


class ProjectGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget
        self.folder = TemporaryDirectory()
        root = Path(self.folder.name)
        self.owner = QMainWindow()
        self.owner.settings = QSettings(str(root / "gallery.ini"), QSettings.Format.IniFormat)
        widget = QWidget()
        self.owner.setCentralWidget(widget)
        row = QHBoxLayout(widget)
        left, center = QVBoxLayout(), QVBoxLayout()
        row.addLayout(left)
        row.addLayout(center)
        self.editor = VisualReportEditor(self.owner, left, center)
        self.editor.editor.apply(lambda report: setattr(
            report, "customer_snapshot", manual_snapshot("Synthetic test customer")))
        self.editor.refresh()
        self.owner.show()
        self.app.processEvents()

    def tearDown(self):
        if self.editor._picture_gallery:
            self.editor._picture_gallery.close()
        self.owner.close()
        self.app.processEvents()
        self.folder.cleanup()

    def add_images(self, count):
        keys = []
        original = dict(self.editor.assets)
        for i in range(count):
            blob = BytesIO()
            Image.new("RGB", (72, 42), (i * 31 % 255, i * 67 % 255,
                                        i * 109 % 255)).save(blob, "PNG")
            key = "media-" + uuid4().hex
            self.editor.media_library[key] = "Synthetic tile %03d" % i
            self.editor.assets[key] = blob.getvalue()
            keys.append(key)
        self.assertEqual(len(self.editor.assets), len(original) + count)
        return keys

    def open_gallery(self):
        self.assertTrue(self.editor.manage_pictures())
        self.app.processEvents()
        gallery = self.editor._picture_gallery
        pictures = gallery.findChild(ProjectPictureList, "projectPictureLibrary")
        self.assertIsNotNone(pictures)
        return gallery, pictures

    @staticmethod
    def mime_for(key):
        from PySide6.QtCore import QByteArray, QMimeData
        data = QMimeData()
        data.setData(PHOTO_MIME, QByteArray(key.encode("utf-8")))
        return data

    def test_gallery_nonmodal_grid_lazily_decoded_and_drag_contains_only_id(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel, QSlider
        keys = self.add_images(110)
        gallery, pictures = self.open_gallery()
        self.assertTrue(gallery.isVisible())
        self.assertFalse(gallery.isModal())
        self.assertEqual(pictures.count(), 110)
        for _ in range(4):
            self.app.processEvents()
        self.assertTrue(pictures.item(0).icon().isNull() is False)
        self.assertLessEqual(len(pictures._cached), 80)
        self.assertFalse(gallery.findChild(QLabel, "pictureGalleryEmptyState").isVisible())
        zoom = gallery.findChild(QSlider, "pictureThumbnailZoom")
        zoom.setValue(180)
        self.app.processEvents()
        self.assertEqual(pictures.iconSize().width(), 180)
        for index in range(0, pictures.count(), 10):
            pictures.scrollToItem(pictures.item(index))
            self.app.processEvents()
        pictures.scrollToItem(pictures.item(pictures.count() - 1))
        self.app.processEvents()
        self.assertLessEqual(len(pictures._cached), 80)
        # QIcons must also be evicted from the list items, not just the LRU.
        self.assertLessEqual(
            sum(not pictures.item(i).icon().isNull() for i in range(pictures.count())), 80)
        self.assertEqual(self.editor.manage_pictures(), True)
        self.assertIs(self.editor._picture_gallery, gallery)

        pictures.setCurrentRow(0)
        with patch("reportmaker.photo_gallery.QDrag") as drag:
            pictures.startDrag(Qt.DropAction.CopyAction)
            payload = drag.return_value.setMimeData.call_args.args[0]
        self.assertEqual(payload.formats(), [PHOTO_MIME])
        self.assertFalse(payload.hasUrls())
        self.assertFalse(payload.hasText())
        self.assertEqual(bytes(payload.data(PHOTO_MIME)).decode("utf-8"), keys[0])

    def test_drop_block_list_exact_order_reuse_save_and_history(self):
        from PySide6.QtCore import QPointF, Qt
        keys = self.add_images(3)
        gallery, pictures = self.open_gallery()
        before = [block.id for block in self.editor.report.modules[0].blocks]
        target = self.editor.blocks.item(0)
        rect = self.editor.blocks.visualItemRect(target)
        drop = FakeDragEvent(
            pictures, self.mime_for(keys[0]), QPointF(8, rect.top() + 1))
        self.editor.blocks.dragEnterEvent(drop)
        self.editor.blocks.dragMoveEvent(drop)
        self.assertTrue(drop.accepted)
        self.assertEqual(self.editor.blocks._photo_drop_index, 0)
        self.editor.blocks.dropEvent(drop)
        self.app.processEvents()
        blocks = self.editor.report.modules[0].blocks
        self.assertEqual([b.id for b in blocks[1:]], before)
        self.assertIsInstance(blocks[0], PhotoBlock)
        self.assertEqual(blocks[0].asset_id, keys[0])
        self.assertEqual(len(self.editor.assets), 3)
        self.assertEqual(self.editor._edit_block_id, blocks[0].id)

        # Reuse the same optimized project bytes at a different position.
        self.assertTrue(self.editor._insert_project_photo(
            self.editor.report.modules[0].id, 2, keys[0]))
        blocks = self.editor.report.modules[0].blocks
        self.assertEqual([b.asset_id for b in blocks if isinstance(b, PhotoBlock)],
                         [keys[0], keys[0]])
        self.assertNotEqual(blocks[0].id, blocks[2].id)
        self.assertEqual(len(self.editor.assets), 3)
        self.assertEqual(len(self.editor.media_library), 3)
        self.editor.undo()
        self.assertEqual(len([b for b in self.editor.report.modules[0].blocks
                              if isinstance(b, PhotoBlock)]), 1)
        self.editor.redo()
        self.assertEqual(len([b for b in self.editor.report.modules[0].blocks
                              if isinstance(b, PhotoBlock)]), 2)

        target_path = Path(self.folder.name) / "photo-project.rmproj"
        self.assertTrue(self.editor.save_to_path(target_path))
        recovered = load_project(target_path)
        self.assertEqual([b.asset_id for b in recovered.report.modules[0].blocks
                          if isinstance(b, PhotoBlock)], [keys[0], keys[0]])
        self.assertEqual(recovered.assets[keys[0]], self.editor.assets[keys[0]])
        self.assertTrue(self.editor.open_from_path(target_path))
        self.assertIsNone(self.editor._picture_gallery)
        self.assertFalse(gallery.isVisible())

    def test_page_drop_zones_nested_module_and_draft_resolution(self):
        from PySide6.QtWidgets import QMessageBox
        keys = self.add_images(2)
        child = Module(LocalizedText("en", "Nested mechanical inspection"))
        module_id = self.editor.report.modules[0].id
        self.editor.editor.add_block(module_id, NestedModuleBlock(child))
        self.editor.refresh()
        gallery, pictures = self.open_gallery()
        zones = self.editor.page.findChildren(PictureDropZone)
        nested_first = next(zone for zone in zones
                            if zone.module_id == child.id and zone.index == 0)
        self.editor.text_edit.insertPlainText("Synthetic pending paragraph draft")
        self.assertTrue(self.editor._block_pending)
        # Direct page drop is explicitly structural: field widgets still block all drops.
        self.assertFalse(self.editor.page.fields[(
            module_id, self.editor.report.modules[0].blocks[0].id, "text")].acceptDrops())
        event = FakeDragEvent(pictures, self.mime_for(keys[0]))
        nested_first.dragEnterEvent(event)
        nested_first.dropEvent(event)
        self.app.processEvents()
        self.assertTrue(event.accepted)
        nested_blocks = next(b.module.blocks for b in self.editor.report.modules[0].blocks
                             if isinstance(b, NestedModuleBlock))
        self.assertEqual(len(nested_blocks), 1)
        self.assertIsInstance(nested_blocks[0], PhotoBlock)
        self.assertEqual(nested_blocks[0].asset_id, keys[0])
        self.assertTrue(any("Synthetic pending paragraph draft" in b.text.original
                            for b in self.editor.report.modules[0].blocks
                            if hasattr(b, "text")))
        self.assertFalse(self.editor._block_pending)
        self.assertEqual(self.editor._module_id, child.id)

        # A competing page draft must not be silently discarded.
        self.editor._module_id = module_id
        self.editor.refresh()
        current = self.editor.blocks.currentItem()
        block_id = self.editor.report.modules[0].blocks[0].id
        page_key = (module_id, block_id, "text")
        self.editor.page.fields[page_key].setPlainText("Pending page draft")
        self.editor.text_edit.setPlainText("Competing block draft")
        prior_count = len(self.editor.report.modules[0].blocks)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.editor._insert_project_photo(module_id, 0, keys[1]))
        self.assertEqual(len(self.editor.report.modules[0].blocks), prior_count)
        self.assertIn(page_key, self.editor.page.pending)
        self.assertTrue(self.editor._block_pending)

    def test_reject_external_fake_stale_wrong_project_and_empty_gallery(self):
        from PySide6.QtCore import QMimeData
        _, empty = self.open_gallery()
        self.assertEqual(empty.count(), 0)
        keys = self.add_images(2)
        self.editor._gallery_populate()
        source = self.editor._picture_list
        valid = self.mime_for(keys[0])
        self.assertEqual(self.editor._resolve_project_photo_drag(source, valid), keys[0])
        for other_source, mime in [
            (None, valid),
            (object(), valid),
            (source, self.mime_for("unknown-asset")),
            (source, self.mime_for("x" * 200)),
            (source, QMimeData()),
        ]:
            self.assertIsNone(self.editor._resolve_project_photo_drag(other_source, mime))
        forged = self.mime_for(keys[0])
        forged.setText("outside payload")
        self.assertIsNone(self.editor._resolve_project_photo_drag(source, forged))
        malicious = QMimeData()
        malicious.setUrls([])
        self.assertIsNone(self.editor._resolve_project_photo_drag(source, malicious))
        before = len(self.editor.report.modules[0].blocks)
        zone = next(x for x in self.editor.page.findChildren(PictureDropZone)
                    if x.module_id == self.editor.report.modules[0].id and x.index == 0)
        invalid = FakeDragEvent(object(), valid)
        zone.dragEnterEvent(invalid)
        zone.dropEvent(invalid)
        self.app.processEvents()
        self.assertTrue(invalid.ignored)
        self.assertEqual(len(self.editor.report.modules[0].blocks), before)
        self.assertFalse(self.editor._insert_project_photo(None, 0, "nonexistent"))
        original_source = source
        self.editor._replace(new_report(), None)
        self.assertIsNone(self.editor._resolve_project_photo_drag(original_source, valid))
        self.assertFalse(self.editor._insert_project_photo(None, 0, keys[0]))


if __name__ == "__main__":
    unittest.main()
