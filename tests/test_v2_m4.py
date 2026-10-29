"""M4 photo transactions and guarded native Qt entry points (synthetic only)."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from reportmaker.model import LocalizedText, PhotoBlock, PhotoMark, PhotoVisual
from reportmaker.project_io import ReportProject, load_project, save_project
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress, find_node, project_branch
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError
from test_v2_inline import sample


def png(color=(90, 25, 160)):
    output = BytesIO()
    Image.new("RGB", (10, 6), color).save(output, "PNG")
    return output.getvalue()


def fixture():
    report, title, para = sample()
    session = ReportSession(ReportProject(report))
    return session, CommandGateway(session), title, para


class PhotoCoreTests(unittest.TestCase):
    def setUp(self):
        self.session, self.gateway, self.title, self.para = fixture()
        self.drafts = DraftCoordinator(self.session, self.gateway)
        self.owner = NodeAddress(self.para.report_id, self.para.module_id)

    def command(self, kind, address=None, *, rev=None, gen=None, **args):
        return self.gateway.execute(CommandIntent(
            kind, address or self.owner, args,
            self.session.revision if rev is None else rev,
            self.session.generation if gen is None else gen))

    def block(self, identifier):
        return find_node(self.session.report_snapshot(), NodeAddress(
            self.para.report_id, self.para.module_id, identifier, "photo"))

    def test_import_is_one_atomic_undo_step_including_project_owned_bytes(self):
        before = self.session.project_snapshot()
        image = png()
        change = self.command("import_photo", image_bytes=image, name="Working image", index=0)
        identifier = next(iter(change.changed_ids))
        block = self.block(identifier)
        self.assertIsInstance(block, PhotoBlock)
        self.assertEqual(self.session.assets[block.asset_id], image)
        self.assertEqual(self.session.media_library[block.asset_id], "Working image")
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.project_snapshot().assets, before.assets)
        self.assertEqual(self.session.project_snapshot().media_library, before.media_library)
        self.assertEqual(self.session.report_snapshot(), before.report)
        self.assertTrue(self.gateway.redo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.assets[block.asset_id], image)
        self.assertEqual(self.block(identifier), block)

    def test_mixed_batch_rejects_invalid_without_orphans_or_history(self):
        baseline = self.session.project_snapshot()
        with self.assertRaises(ValueError):
            self.command("import_photos", photos=[("ok", png()), ("bad", b"not image")])
        self.assertEqual(self.session.project_snapshot(), baseline)
        self.assertEqual(self.session.revision, 0)
        self.assertFalse(self.session._editor.can_undo)
        with self.assertRaises(ValueError):
            self.command("import_photos", photos=[])
        self.assertEqual(dict(self.session.assets), {})

    def test_two_photo_batch_atomic_single_undo_and_mixed_order(self):
        change = self.command("import_photos",
                              photos=(("first", png()), ("second", png((30, 80, 70)))),
                              index=0)
        self.assertEqual(len(change.changed_ids), 2)
        blocks = find_node(self.session.report_snapshot(), self.owner).blocks
        self.assertEqual([type(b).__name__ for b in blocks[:3]],
                         ["PhotoBlock", "PhotoBlock", "ParagraphBlock"])
        self.assertEqual(len(self.session.assets), 2)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(len(self.session.assets), 0)
        self.gateway.redo(self.session.generation, self.session.revision)
        self.assertEqual(len(self.session.assets), 2)
        self.assertEqual([b.asset_id for b in find_node(
            self.session.report_snapshot(), self.owner).blocks[:2]],
            [b.asset_id for b in blocks[:2]])

    def test_save_reload_original_working_bytes_unchanged_and_independent_visuals(self):
        image = png()
        first = self.command("import_photo", image_bytes=image, name="Original").changed_ids
        first_id = next(iter(first))
        asset = self.block(first_id).asset_id
        second_id = next(iter(self.command("add_photo", asset_id=asset).changed_ids))
        visual = PhotoVisual(rotation=90, width_pct=65,
                             marks=[PhotoMark("arrow", .1, .2, .6, .8)])
        self.command("set_photo_visual", NodeAddress(
            self.para.report_id, self.para.module_id, first_id, "photo"), visual=visual)
        self.assertEqual(self.block(second_id).visual, PhotoVisual())
        self.assertEqual(self.session.assets[asset], image)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "m4.rmproj"
            save_project(self.session.project_snapshot(), path)
            loaded = load_project(path)
            self.assertEqual(loaded.assets[asset], image)
            module = find_node(loaded.report, self.owner)
            self.assertEqual(module.blocks[-2].visual, visual)
            self.assertEqual(module.blocks[-1].visual, PhotoVisual())
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.block(first_id).visual, PhotoVisual())
        self.gateway.redo(self.session.generation, self.session.revision)
        self.assertEqual(self.block(first_id).visual, visual)

    def test_replace_existing_and_new_import_resets_only_that_visual(self):
        image = png()
        photo_id = next(iter(self.command(
            "import_photo", image_bytes=image, name="Original").changed_ids))
        other = next(iter(self.command(
            "import_photo", image_bytes=png((1, 2, 3)), name="Alternate").changed_ids))
        asset = self.block(photo_id).asset_id
        other_asset = self.block(other).asset_id
        photo_addr = NodeAddress(self.para.report_id, self.para.module_id, photo_id, "photo")
        self.command("set_photo_visual", photo_addr, visual=PhotoVisual(flip_h=True))
        self.command("replace_photo", photo_addr, asset_id=other_asset)
        self.assertEqual(self.block(photo_id).visual, PhotoVisual())
        self.assertEqual(self.block(photo_id).asset_id, other_asset)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.block(photo_id).asset_id, asset)
        self.assertTrue(self.block(photo_id).visual.flip_h)
        change = self.command("replace_photo_import", photo_addr,
                              image_bytes=png((22, 45, 66)), name="Fresh")
        self.assertTrue(change.assets_changed)
        new_asset = self.block(photo_id).asset_id
        self.assertNotIn(new_asset, {asset, other_asset})
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertNotIn(new_asset, self.session.assets)
        self.assertEqual(self.block(photo_id).asset_id, asset)

    def test_replacing_with_same_asset_resets_layers_and_preserves_undo(self):
        photo_id = next(iter(self.command(
            "import_photo", image_bytes=png(), name="Reusable").changed_ids))
        photo_addr = NodeAddress(self.para.report_id, self.para.module_id, photo_id, "photo")
        asset_id = self.block(photo_id).asset_id
        visual = PhotoVisual(rotation=90, width_pct=65, flip_h=True)
        self.command("set_photo_visual", photo_addr, visual=visual)
        original_bytes = self.session.assets[asset_id]
        before_revision = self.session.revision

        # Explicitly replacing an edited placement with its *same* project
        # image must clear its layers, not silently treat the action as a no-op.
        change = self.command("replace_photo", photo_addr, asset_id=asset_id)
        self.assertIsNotNone(change)
        self.assertTrue(change.assets_changed)
        self.assertEqual(self.session.revision, before_revision + 1)
        self.assertEqual(self.block(photo_id).asset_id, asset_id)
        self.assertEqual(self.block(photo_id).visual, PhotoVisual())
        self.assertEqual(self.session.assets[asset_id], original_bytes)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.block(photo_id).visual, visual)
        self.gateway.redo(self.session.generation, self.session.revision)
        self.assertEqual(self.block(photo_id).visual, PhotoVisual())

        # The same replacement without edits remains a genuine no-op.
        before_revision = self.session.revision
        self.assertIsNone(self.command("replace_photo", photo_addr, asset_id=asset_id))
        self.assertEqual(self.session.revision, before_revision)

    def test_caption_changes_translation_provenance_and_draft_ownership(self):
        photo_id = next(iter(self.command(
            "import_photo", image_bytes=png(), name="Caption").changed_ids))
        addr = NodeAddress(self.para.report_id, self.para.module_id, photo_id, "caption")
        page = self.drafts.for_editor("page-editor")
        page.stage_text(addr, "First 🛠️")
        with self.assertRaises(PendingDraftError):
            self.drafts.update(addr, "Branch takeover")
        with self.assertRaises(PendingDraftError):
            self.command("set_photo_visual", NodeAddress(
                self.para.report_id, self.para.module_id, photo_id, "photo"),
                visual=PhotoVisual(rotation=90))
        self.assertIsNotNone(page.apply(addr))
        self.assertFalse(self.drafts.pending)
        self.assertEqual(self.block(photo_id).caption.original, "First 🛠️")
        # A real localized caption imported from a legacy file keeps language
        # provenance when edited; no new hard-coded language enum.
        self.command("set_photo_caption", NodeAddress(
            self.para.report_id, self.para.module_id, photo_id, "photo"),
            text="Caption final")
        self.assertEqual(self.block(photo_id).caption.original, "Caption final")
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.block(photo_id).caption.original, "First 🛠️")

    def test_caption_translation_stale_markers_survive_save_reopen(self):
        report, title, para = sample()
        caption = LocalizedText("en", "Before repair",
                                {"fr-CA": "Avant réparation", "de": "Vor Reparatur"})
        original = PhotoBlock("project-image", caption)
        find_node(report, NodeAddress(report.id, para.module_id)).blocks.append(original)
        session = ReportSession(ReportProject(
            report, {"project-image": png()},
            {"project-image": "Machine inspection"}))
        gateway = CommandGateway(session)
        coordinator = DraftCoordinator(session, gateway)
        addr = NodeAddress(report.id, para.module_id, original.id, "caption")
        coordinator.update(addr, "After repair")
        coordinator.commit(addr)
        updated = find_node(session.report_snapshot(), NodeAddress(
            report.id, para.module_id, original.id, "photo")).caption
        self.assertEqual(updated.translations, caption.translations)
        self.assertEqual(updated.stale_languages, {"fr-CA", "de"})
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "translations.rmproj"
            save_project(session.project_snapshot(), path)
            loaded = load_project(path)
            reopened = find_node(loaded.report, NodeAddress(
                report.id, para.module_id, original.id, "photo"))
            self.assertEqual(reopened.caption.stale_languages, {"fr-CA", "de"})
            self.assertEqual(reopened.caption.original, "After repair")

    def test_malformed_visual_does_not_touch_redo_or_revision(self):
        photo_id = next(iter(self.command(
            "import_photo", image_bytes=png(), name="Valid").changed_ids))
        photo_addr = NodeAddress(self.para.report_id, self.para.module_id, photo_id, "photo")
        before = self.session.project_snapshot()
        with self.assertRaises(ValueError):
            self.command("set_photo_visual", photo_addr, visual=PhotoVisual(rotation=45))
        self.assertEqual(self.session.project_snapshot(), before)
        with self.assertRaises(ValueError):
            self.command("replace_photo", photo_addr, asset_id="../escape")
        self.assertEqual(self.session.project_snapshot(), before)
        with self.assertRaises(ValueError):
            self.command("set_photo_caption", photo_addr, text=123)

    def test_stale_generation_and_revision_cannot_import_or_replace(self):
        rev, gen = self.session.revision, self.session.generation
        change = self.command("import_photo", image_bytes=png(), name="First")
        block_id = next(iter(change.changed_ids))
        with self.assertRaises(StaleIntentError):
            self.command("import_photo", rev=rev, gen=gen,
                         image_bytes=png(), name="Stale")
        with self.assertRaises(StaleIntentError):
            self.command("replace_photo", NodeAddress(
                self.para.report_id, self.para.module_id, block_id, "photo"),
                rev=rev, gen=gen, asset_id=self.block(block_id).asset_id)
        self.assertEqual(len(self.session.assets), 1)
        self.assertEqual(self.session.revision, 1)

    def test_asset_history_tracks_interleaved_non_media_commands_and_saved_dirty(self):
        change = self.command("import_photo", image_bytes=png(), name="Photo")
        self.command("add_paragraph", text="Another")
        asset = self.block(next(iter(change.changed_ids))).asset_id
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertIn(asset, self.session.assets)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertNotIn(asset, self.session.assets)
        self.gateway.redo(self.session.generation, self.session.revision)
        self.assertIn(asset, self.session.assets)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "project.rmproj"
            save_project(self.session.project_snapshot(), path)
            self.session._mark_saved(path, self.session.revision)
            self.assertFalse(self.session.dirty)
            self.gateway.undo(self.session.generation, self.session.revision)
            self.assertTrue(self.session.dirty)
            self.gateway.redo(self.session.generation, self.session.revision)
            self.assertFalse(self.session.dirty)


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Qt offscreen required")
class PhotoQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        project, self.title, self.para, self.media = self.make_project()
        self.win = V2MainWindow(project=project)
        self.win.show()
        self.app.processEvents()

    def make_project(self):
        report, title, para = sample()
        image = png()
        return ReportProject(report, {"m4-synthetic": image},
                             {"m4-synthetic": "Synthetic"}), title, para, image

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.app.processEvents()

    def test_thumbnail_caption_and_natural_width_geometry(self):
        from PySide6.QtCore import Qt
        from reportmaker.v2.branch.canvas import PhotoThumbnail
        self.assertTrue(self.win.branch.add_photo(
            module_id=self.para.module_id, asset_id="m4-synthetic"))
        thumb = self.win.branch.findChild(PhotoThumbnail, "v2PhotoThumbnail")
        self.assertIsNotNone(thumb)
        self.assertFalse(thumb._image.isNull())
        # Small synthetic thumbnails display at natural pixel size without
        # artificial stretch; larger images remeasure with the card width.
        from reportmaker.v2.branch.canvas import PhotoThumbnail as Thumb
        from PySide6.QtGui import QImage
        large = Thumb(QImage(800, 480, QImage.Format.Format_RGB32), 100, "center")
        self.assertGreater(large.heightForWidth(450), large.heightForWidth(190))
        self.assertEqual(thumb.heightForWidth(450), thumb.heightForWidth(190))
        self.assertEqual(self.win.branch.verticalScrollBarPolicy(),
                         Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(thumb.verticalScrollBarPolicy()
                         if hasattr(thumb, "verticalScrollBarPolicy") else None, None)
        blocks = find_node(self.win.session.report_snapshot(), NodeAddress(
            self.para.report_id, self.para.module_id)).blocks
        photo = blocks[-1]
        addr = NodeAddress(self.para.report_id, self.para.module_id, photo.id, "caption")
        editor = self.win.branch.editor_for(addr)
        self.assertEqual(editor.verticalScrollBarPolicy(),
                         Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setPlainText("Machine inspection photo\nSecond line")
        self.assertTrue(self.win.branch.apply_draft(addr))
        self.assertEqual(find_node(self.win.session.report_snapshot(), NodeAddress(
            self.para.report_id, self.para.module_id, photo.id, "photo")).caption.original,
            "Machine inspection photo\nSecond line")

    def test_import_via_explicit_paths_preserves_external_original(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "synthetic.png"
            source.write_bytes(png())
            self.assertTrue(self.win.branch.import_photo_paths(
                [source], module_id=self.para.module_id, index=0))
            self.assertEqual(source.read_bytes(), png())
            self.assertEqual(len(self.win.session.assets), 2)
            self.assertEqual(len(self.win.session.media_library), 2)
            self.assertTrue(self.win.branch.undo())
            self.assertEqual(len(self.win.session.assets), 1)
            self.assertTrue(self.win.branch.redo())
            self.assertEqual(len(self.win.session.assets), 2)

    def test_clipboard_image_and_untrusted_html_rejection(self):
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QImage
        canvas = self.win.branch
        clipboard = self.app.clipboard()
        clipboard.setMimeData(QMimeData())
        self.assertFalse(canvas.paste_photo(module_id=self.para.module_id))
        clipboard.setText('<img src="https://example.test/secret">')
        self.assertFalse(canvas.paste_photo(module_id=self.para.module_id))
        clipboard.setImage(QImage.fromData(png()))
        self.assertTrue(canvas.paste_photo(module_id=self.para.module_id))
        self.assertEqual(len(self.win.session.assets), 2)

    def test_photo_visual_edit_and_preview_render_share_project_bytes(self):
        from reportmaker.v2.branch.canvas import PhotoThumbnail
        photo_id = next(iter(self.win.gateway.execute(CommandIntent(
            "add_photo", NodeAddress(self.para.report_id, self.para.module_id),
            {"asset_id": "m4-synthetic"},
            self.win.session.revision, self.win.session.generation)).changed_ids))
        photo_addr = NodeAddress(self.para.report_id, self.para.module_id, photo_id, "photo")
        original = self.win.session.assets["m4-synthetic"]
        with patch("reportmaker.v2.branch.canvas.PictureEditorDialog") as dialog:
            from PySide6.QtWidgets import QDialog
            instance = dialog.return_value
            instance.exec.return_value = QDialog.DialogCode.Accepted
            instance.visual = PhotoVisual(rotation=90, flip_h=True)
            self.assertTrue(self.win.branch.edit_photo(photo_addr))
        self.assertEqual(self.win.session.assets["m4-synthetic"], original)
        self.assertEqual(find_node(self.win.session.report_snapshot(),
                                  photo_addr).visual.rotation, 90)
        thumbs = self.win.branch.findChildren(PhotoThumbnail, "v2PhotoThumbnail")
        self.assertGreater(len(thumbs), 0)
        self.win.branch.undo()
        self.assertEqual(find_node(self.win.session.report_snapshot(),
                                  photo_addr).visual.rotation, 0)

    def test_toolbar_tools_expose_all_modes_with_visible_active_selection(self):
        from reportmaker.v2.branch.photo_tools import V2PictureEditorDialog
        from reportmaker.photo_editor import TOOLS
        from reportmaker.v2.branch.canvas import PictureEditorDialog
        self.assertIs(PictureEditorDialog, V2PictureEditorDialog)
        dialog = V2PictureEditorDialog(self.win, png(), PhotoVisual(), "en")
        dialog.show()
        self.app.processEvents()
        self.assertTrue(dialog.tool_choice.isHidden())
        self.assertEqual(len(dialog.tool_buttons.buttons()), len(TOOLS))
        for index, kind in enumerate(TOOLS):
            button = dialog.tool_buttons.button(index)
            self.assertEqual(button.objectName(), "v2PhotoTool_" + kind)
            self.assertTrue(button.toolTip())
            button.click()
            self.assertTrue(button.isChecked())
            self.assertEqual(dialog.canvas.tool, kind)
            self.assertEqual(sum(b.isChecked() for b in dialog.tool_buttons.buttons()), 1)
        dialog.close()

    def test_reopen_project_in_v2_preserves_captions_and_image_layers(self):
        from reportmaker.v2.app import V2MainWindow
        from reportmaker.v2.branch.canvas import PhotoThumbnail
        photo = self.win.gateway.execute(CommandIntent(
            "add_photo", NodeAddress(self.para.report_id, self.para.module_id),
            {"asset_id": "m4-synthetic"},
            self.win.session.revision, self.win.session.generation))
        block_id = next(iter(photo.changed_ids))
        self.win.gateway.execute(CommandIntent(
            "set_photo_caption", NodeAddress(
                self.para.report_id, self.para.module_id, block_id, "photo"),
            {"text": "Drive side inspection"}, self.win.session.revision,
            self.win.session.generation))
        self.win.gateway.execute(CommandIntent(
            "set_photo_visual", NodeAddress(
                self.para.report_id, self.para.module_id, block_id, "photo"),
            {"visual": PhotoVisual(rotation=90, width_pct=70)},
            self.win.session.revision, self.win.session.generation))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "v2-photo-test.rmproj"
            save_project(self.win.session.project_snapshot(), path)
            reopened = V2MainWindow(project=load_project(path))
            reopened.show()
            self.app.processEvents()
            try:
                photo_addr = NodeAddress(self.para.report_id, self.para.module_id,
                                         block_id, "photo")
                restored = find_node(reopened.session.report_snapshot(), photo_addr)
                self.assertEqual(restored.caption.original, "Drive side inspection")
                self.assertEqual(restored.visual.rotation, 90)
                self.assertEqual(restored.visual.width_pct, 70)
                thumbnail = reopened.branch.findChild(PhotoThumbnail, "v2PhotoThumbnail")
                self.assertFalse(thumbnail._image.isNull())
            finally:
                reopened._confirm_transition = lambda: False
                reopened.close()
                self.app.processEvents()

    def test_stale_external_drop_never_imports(self):
        from PySide6.QtCore import QMimeData, QPoint, QUrl, Qt
        from PySide6.QtGui import QDragEnterEvent, QDropEvent
        from reportmaker.v2.branch.canvas import DropRow
        rows = self.win.branch.findChildren(DropRow)
        target = next(row for row in rows if row.address.module_id == self.para.module_id
                      and row.kind == "module")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "from-explorer.png"
            path.write_bytes(png())
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))])
            actions = Qt.DropAction.CopyAction
            point = QPoint(12, target.height() // 2)
            enter = QDragEnterEvent(point, actions, mime,
                                    Qt.MouseButton.NoButton,
                                    Qt.KeyboardModifier.NoModifier)
            self.win.branch._preview_external_drop(target, enter)
            self.assertTrue(enter.isAccepted())
            self.assertIsNotNone(self.win.branch._external_drag)
            self.win.gateway.execute(CommandIntent(
                "add_page_break", NodeAddress(self.para.report_id, self.para.module_id),
                {}, self.win.session.revision, self.win.session.generation))
            drop = QDropEvent(point.toPointF(), actions, mime,
                              Qt.MouseButton.NoButton,
                              Qt.KeyboardModifier.NoModifier)
            self.win.branch._commit_external_drop(target, drop)
            self.app.processEvents()
            self.assertEqual(len(self.win.session.assets), 1)

    def test_reject_remote_and_html_url_drop(self):
        from PySide6.QtCore import QMimeData, QUrl
        from reportmaker.photo_gallery import local_picture_paths
        mime = QMimeData()
        mime.setUrls([QUrl("https://example.test/a.png")])
        paths, errors = local_picture_paths(mime)
        self.assertFalse(paths)
        self.assertTrue(errors)
        mime.setHtml("<img src='file:///etc/passwd'>")
        paths, _ = local_picture_paths(mime)
        self.assertFalse(paths)


if __name__ == "__main__":
    unittest.main()
