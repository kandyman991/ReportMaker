"""M2.1 structural placement: pure model + offline Qt regression tests.

All examples are fabricated. No customer media, browser data or live files.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportmaker.engine import module_outline
from reportmaker.model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, ParagraphBlock,
    PhotoBlock, Report, TableBlock,
)
from reportmaker.project_io import ReportProject, load_project
from reportmaker.reference import manual_snapshot
from reportmaker.v2.adapters.persistence import ProjectPersistence
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.projections import NodeAddress, project_branch
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError
from reportmaker.v2.structure import plan_drop


def fixture() -> ReportProject:
    translated = LocalizedText("en", "Torque checked")
    translated.set_translation("de", "Drehmoment geprüft")
    child = Module(LocalizedText("en", "Child"), [ParagraphBlock(translated)])
    first = Module(LocalizedText("en", "A"), [
        HeadingBlock(LocalizedText("en", "Before")),
        NestedModuleBlock(child),
        PhotoBlock("synthetic_photo", LocalizedText("en", "Fabricated photo")),
        TableBlock([[LocalizedText("en", "Reading")]]),
    ])
    second = Module(LocalizedText("en", "B"), [
        ParagraphBlock(LocalizedText("en", "Synthetic B text")),
    ])
    report = Report(
        customer_id=None,
        customer_snapshot=manual_snapshot("Fabricated structural customer"),
        start_date=date(2026, 10, 28), end_date=date(2026, 10, 28),
        primary_language="en", output_languages=["en", "de"],
        modules=[first, second],
        conclusion=Module(LocalizedText("en", "Conclusions")),
    )
    # An unlisted legacy-style placed asset is valid and must remain reachable
    # through moves and be stored without changing its bytes.
    return ReportProject(report, {"synthetic_photo": b"synthetic-photo-bytes"})


def addr(report, module_id, block_id=None):
    return NodeAddress(report.id, module_id, block_id,
                       "text" if block_id else "title")


class StructuralPlacementTests(unittest.TestCase):
    def setUp(self):
        self.session = ReportSession(fixture())
        self.gateway = CommandGateway(self.session)
        self.report = self.session.report_snapshot()
        self.a, self.b = self.report.modules
        self.child = self.a.blocks[1].module
        self.photo = self.a.blocks[2]
        self.heading = self.a.blocks[0]

    def move(self, source, anchor, position):
        return self.gateway.execute(CommandIntent(
            "move_node", source, {"anchor": anchor, "position": position},
            self.session.revision, self.session.generation,
        ))

    def test_before_after_reorders_mixed_siblings_without_rebuilding(self):
        old_wrapper_id = self.a.blocks[1].id
        result = self.move(addr(self.report, self.child.id),
                           addr(self.report, self.a.id, self.photo.id), "after")
        self.assertTrue(result.structure_changed)
        after = self.session.report_snapshot()
        self.assertEqual([type(b).__name__ for b in after.modules[0].blocks],
                         ["HeadingBlock", "PhotoBlock", "NestedModuleBlock", "TableBlock"])
        self.assertEqual(after.modules[0].blocks[2].id, old_wrapper_id)
        self.assertEqual(after.modules[0].blocks[2].module.id, self.child.id)
        self.assertEqual([e.module_id for e in module_outline(after) if not e.is_conclusion],
                         [self.a.id, self.child.id, self.b.id])
        self.assertEqual(after.ordered_sections()[-1].id, self.report.conclusion.id)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.report_snapshot(), self.report)
        self.assertTrue(self.gateway.redo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.report_snapshot(), after)

    def test_reparent_module_inside_and_promote_to_root_before_conclusions(self):
        self.move(addr(self.report, self.b.id), addr(self.report, self.child.id), "inside")
        nested = self.session.report_snapshot()
        promoted_parent = nested.modules[0].blocks[1].module
        self.assertEqual(promoted_parent.blocks[-1].module.id, self.b.id)
        wrapper_id = promoted_parent.blocks[-1].id
        self.assertEqual(len(nested.modules), 1)
        self.move(addr(nested, self.b.id), addr(nested, nested.id), "inside")
        restored = self.session.report_snapshot()
        self.assertEqual([m.id for m in restored.modules], [self.a.id, self.b.id])
        self.assertEqual(restored.modules[1].blocks[0].text.original, "Synthetic B text")
        self.assertEqual(restored.ordered_sections()[-1].id, self.report.conclusion.id)
        self.assertNotIn(wrapper_id, {m.id for m in restored.modules})
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.report_snapshot(), nested)

    def test_move_photo_cross_parent_retains_asset_and_translations_after_save(self):
        photo_before = deepcopy(self.photo)
        result = self.move(addr(self.report, self.a.id, self.photo.id),
                           addr(self.report, self.b.id), "inside")
        self.assertTrue(result.structure_changed)
        after = self.session.report_snapshot()
        self.assertEqual(after.modules[1].blocks[-1], photo_before)
        self.assertEqual(self.session.assets["synthetic_photo"], b"synthetic-photo-bytes")
        translated = after.modules[0].blocks[1].module.blocks[0].text
        self.assertEqual(translated.translations["de"], "Drehmoment geprüft")
        with TemporaryDirectory() as folder:
            target = Path(folder) / "moved.rmproj"
            ProjectPersistence().save(self.session, target)
            reloaded = load_project(target)
            self.assertEqual(reloaded.report, after)
            self.assertEqual(reloaded.assets["synthetic_photo"], b"synthetic-photo-bytes")

    def test_before_and_after_accept_nonmodule_content_anchors(self):
        table = self.a.blocks[3]
        self.move(addr(self.report, self.a.id, self.heading.id),
                  addr(self.report, self.a.id, table.id), "after")
        ids = [block.id for block in self.session.report_snapshot().modules[0].blocks]
        self.assertEqual(ids, [self.a.blocks[1].id, self.photo.id, table.id, self.heading.id])
        self.move(addr(self.report, self.a.id, self.heading.id),
                  addr(self.report, self.child.id), "before")
        ids = [block.id for block in self.session.report_snapshot().modules[0].blocks]
        self.assertEqual(ids, [self.heading.id, self.a.blocks[1].id, self.photo.id, table.id])

    def test_noop_does_not_touch_revision_or_redo(self):
        self.move(addr(self.report, self.a.id), addr(self.report, self.b.id), "after")
        self.gateway.undo(self.session.generation, self.session.revision)
        rev = self.session.revision
        notice = []
        self.session.subscribe(notice.append)
        self.assertIsNone(self.move(addr(self.report, self.b.id),
                                    addr(self.report, self.a.id), "after"))
        self.assertEqual(self.session.revision, rev)
        self.assertEqual(notice, [])
        self.assertIsNotNone(self.gateway.redo(self.session.generation, self.session.revision))

    def test_invalid_targets_preserve_data_history_and_revision(self):
        self.move(addr(self.report, self.a.id), addr(self.report, self.b.id), "after")
        changed = self.session.report_snapshot()
        rev = self.session.revision
        wrong_owner = addr(self.report, self.b.id, self.photo.id)
        cases = [
            (addr(self.report, self.a.id), addr(self.report, self.child.id), "inside"),
            (addr(self.report, self.a.id), addr(self.report, self.a.id), "inside"),
            (addr(self.report, self.a.id), addr(self.report, self.child.id), "before"),
            (addr(self.report, self.a.id), addr(self.report, self.report.conclusion.id), "after"),
            (addr(self.report, self.b.id), addr(self.report, self.report.conclusion.id), "inside"),
            (addr(self.report, self.a.id, self.heading.id),
             addr(self.report, self.report.conclusion.id), "inside"),
            (addr(self.report, self.a.id, self.photo.id),
             addr(self.report, self.report.id), "inside"),
            (addr(self.report, self.a.id), addr(self.report, self.a.id, self.photo.id), "inside"),
            (wrong_owner, addr(self.report, self.b.id), "inside"),
            (addr(self.report, self.a.id), addr(self.report, self.b.id), "merge"),
            (addr(self.report, self.report.conclusion.id),
             addr(self.report, self.a.id), "before"),
            (addr(self.report, self.report.id),
             addr(self.report, self.a.id), "before"),
        ]
        for source, anchor, position in cases:
            with self.subTest(position=position, source=source, anchor=anchor):
                with self.assertRaises((LookupError, ValueError)):
                    self.move(source, anchor, position)
                self.assertEqual(self.session.report_snapshot(), changed)
                self.assertEqual(self.session.revision, rev)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.report_snapshot(), self.report)

    def test_no_drop_before_or_after_conclusions_content(self):
        project = fixture()
        conclusion_block = ParagraphBlock(LocalizedText("en", "Final notes"))
        project.report.conclusion.blocks.append(conclusion_block)
        session = ReportSession(project)
        gateway = CommandGateway(session)
        before = session.report_snapshot()
        source = before.modules[0].blocks[0]
        for position in ("before", "after"):
            with self.subTest(position=position):
                with self.assertRaises(ValueError):
                    gateway.execute(CommandIntent(
                        "move_node", addr(before, before.modules[0].id, source.id),
                        {"anchor": addr(before, before.conclusion.id, conclusion_block.id),
                         "position": position}, session.revision, session.generation))
                self.assertEqual(session.report_snapshot(), before)
                self.assertEqual(session.revision, 0)
                self.assertFalse(session._editor.can_undo)

    def test_stale_revision_generation_and_pending_draft_rejected(self):
        s = self.session
        intent = CommandIntent("move_node", addr(self.report, self.b.id),
                               {"anchor": addr(self.report, self.a.id),
                                "position": "before"}, 99, s.generation)
        with self.assertRaises(StaleIntentError):
            self.gateway.execute(intent)
        with self.assertRaises(StaleIntentError):
            self.gateway.execute(CommandIntent(
                intent.kind, intent.target, intent.args, s.revision, "old-generation"))
        s.set_draft_guard(lambda: False)
        with self.assertRaises(PendingDraftError):
            self.move(addr(self.report, self.b.id), addr(self.report, self.a.id), "before")
        self.assertEqual(s.revision, 0)
        self.assertEqual(s.report_snapshot(), self.report)

    def test_plan_is_read_only_and_supports_before_conclusions(self):
        before = self.session.report_snapshot()
        plan = plan_drop(before, addr(before, self.a.id),
                         addr(before, before.conclusion.id), "before")
        self.assertTrue(plan.noop is False)
        self.assertEqual(plan.destination_parent_id, None)
        self.assertEqual(plan.destination_index, 2)
        self.assertEqual(before, self.session.report_snapshot())
        self.move(addr(before, self.a.id), addr(before, before.conclusion.id), "before")
        self.assertEqual([m.id for m in self.session.report_snapshot().modules],
                         [self.b.id, self.a.id])


@unittest.skipUnless(os.getenv("QT_QPA_PLATFORM") == "offscreen",
                     "offline Qt Windows CI")
class StructuralQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_toolbar_move_up_down_and_undo(self):
        from PySide6.QtGui import QAction
        from reportmaker.v2.app import V2MainWindow
        win = V2MainWindow(project=fixture())
        try:
            win.show()
            self.app.processEvents()
            before = win.session.report_snapshot()
            win.branch._selected_module_id = before.modules[1].id
            up = win.findChild(QAction, "v2MoveUp")
            down = win.findChild(QAction, "v2MoveDown")
            self.assertIsInstance(up, QAction)
            self.assertIsInstance(down, QAction)
            win.branch._refresh()
            self.assertTrue(up.isEnabled())
            self.assertFalse(down.isEnabled())
            self.assertTrue(win.branch.move_selected_up())
            self.app.processEvents()
            self.assertEqual(win.session.report_snapshot().modules[0].id,
                             before.modules[1].id)
            self.assertFalse(up.isEnabled())
            self.assertTrue(down.isEnabled())
            self.assertFalse(win.branch.move_selected_up())
            self.assertTrue(win.branch.move_selected_down())
            self.assertEqual(win.session.report_snapshot().modules[0].id,
                             before.modules[0].id)
            self.assertTrue(up.isEnabled())
            self.assertFalse(down.isEnabled())
            self.assertTrue(win.branch.undo())
            self.assertEqual(win.session.report_snapshot().modules[0].id,
                             before.modules[1].id)
        finally:
            win._confirm_transition = lambda: False
            win.close()
            self.app.processEvents()

    def test_toolbar_moves_nested_module_across_mixed_content(self):
        from PySide6.QtGui import QAction
        from reportmaker.v2.app import V2MainWindow
        win = V2MainWindow(project=fixture())
        try:
            initial = win.session.report_snapshot()
            child_id = initial.modules[0].blocks[1].module.id
            win.branch._selected_module_id = child_id
            win.branch._refresh()
            up = win.findChild(QAction, "v2MoveUp")
            down = win.findChild(QAction, "v2MoveDown")
            self.assertTrue(up.isEnabled())
            self.assertTrue(down.isEnabled())
            self.assertTrue(win.branch.move_selected_up())
            self.assertEqual(win.session.report_snapshot().modules[0].blocks[0].module.id, child_id)
            self.assertFalse(up.isEnabled())
            self.assertTrue(down.isEnabled())
            self.assertTrue(win.branch.move_selected_down())
            self.assertEqual(win.session.report_snapshot(), initial)
        finally:
            win._confirm_transition = lambda: False
            win.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
