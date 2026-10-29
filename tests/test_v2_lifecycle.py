"""M1.4 Project Lifecycle / Checkpoint A integration regression suite.

All test archives/settings are synthetic and temporary. Qt runs offscreen;
hosted Windows CI is not the user-installed Windows/DPI acceptance gate.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from reportmaker.model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, Report
from reportmaker.project_io import ReportProject, load_project, save_project
from reportmaker.reference import manual_snapshot
from reportmaker.v2.app import blank_report
from reportmaker.v2.commands import CommandIntent
from reportmaker.v2.projections import NodeAddress
from reportmaker.v2.session import ReportSession, UnsavedChangesError


class NewReportTests(unittest.TestCase):
    def test_new_report_has_fresh_ids_real_manual_snapshot_and_conclusions_last(self):
        a = blank_report("Synthetically named customer", today=date(2026, 10, 28))
        b = blank_report("Synthetically named customer", today=date(2026, 10, 28))
        self.assertNotEqual(a.id, b.id)
        self.assertNotEqual(a.modules[0].id, b.modules[0].id)
        self.assertIsNone(a.customer_id)
        self.assertEqual(a.customer_snapshot.customer_name, "Synthetically named customer")
        self.assertEqual(a.ordered_sections()[-1].id, a.conclusion.id)
        self.assertIsInstance(a.created_date, date)
        self.assertEqual(a.start_date, a.end_date)

    def test_blank_manual_customer_name_rejected(self):
        with self.assertRaises(ValueError):
            blank_report("  ")


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offline Qt CI")
class ProjectLifecycleQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from reportmaker.v2.app import V2MainWindow
        from reportmaker.v2.presentation import PresentationStore
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.settings = QSettings(
            str(self.folder / "canvas-settings.ini"), QSettings.Format.IniFormat
        )
        self.store = PresentationStore(self.settings)
        self.report = blank_report("Test customer M1.4", today=date(2026, 10, 28))
        self.win = V2MainWindow(self.report, presentation=self.store)
        self.win.show()
        self.app.processEvents()
        self._windows = [self.win]

    def tearDown(self):
        for win in self._windows:
            # Do not trigger interactive close dialogs from fixture teardown.
            win._confirm_transition = lambda: False
            win.close()
        self.app.processEvents()

    def _assert_no_legacy_views(self, win):
        from PySide6.QtWidgets import QSplitter, QTreeWidget
        self.assertFalse(win.findChildren(QSplitter))
        self.assertFalse(win.findChildren(QTreeWidget))
        self.assertIs(win.centralWidget(), win.tabs)
        self.assertIs(win.tabs.currentWidget(), win.branch)
        self.assertIs(win.tabs.widget(0), win.branch)

    def _rename(self, title):
        report = self.win.session.report_snapshot()
        address = NodeAddress(report.id, report.modules[0].id)
        self.win.gateway.execute(CommandIntent(
            "rename_module", address, {"title": title},
            self.win.session.revision, self.win.session.generation,
        ))
        self.app.processEvents()

    def test_full_edit_save_reopen_undo_redo_and_canonical_order(self):
        from reportmaker.v2.app import V2MainWindow
        target = self.folder / "round-trip.rmproj"
        self._assert_no_legacy_views(self.win)
        self.assertTrue(self.win.branch.add_nested_module())
        self.app.processEvents()
        self.assertTrue(self.win.branch.add_paragraph())
        self.app.processEvents()
        report = self.win.session.report_snapshot()
        child = report.modules[0].blocks[-1].module
        block = child.blocks[-1]
        address = NodeAddress(report.id, child.id, block.id, "text")
        widget = self.win.branch.editor_for(address)
        widget.setPlainText("Replaced bearing 🛠️\n完了")
        self.assertTrue(self.win.branch.drafts.pending)
        self.assertTrue(self.win.branch.apply_draft(address))
        self.app.processEvents()
        self.assertTrue(self.win.branch.undo())
        self.assertTrue(self.win.branch.redo())
        self.app.processEvents()
        expected = self.win.session.report_snapshot()
        self.assertEqual(
            expected.modules[0].blocks[-1].module.blocks[-1].text.original,
            "Replaced bearing 🛠️\n完了"
        )
        self.assertTrue(self.win.save_project(target))
        self.assertFalse(self.win.session.dirty)
        self.assertEqual(load_project(target).report, expected)
        self.assertEqual(load_project(target).report.ordered_sections()[-1].id,
                         expected.conclusion.id)

        reopened = V2MainWindow(project=load_project(target), presentation=self.store)
        self._windows.append(reopened)
        reopened.show()
        self.app.processEvents()
        self._assert_no_legacy_views(reopened)
        self.assertEqual(reopened.session.report_snapshot(), expected)
        self.assertTrue(reopened.branch.visible_nodes[-1][1] == "conclusion")
        addr = NodeAddress(expected.id, expected.modules[0].id)
        reopened.gateway.execute(CommandIntent(
            "rename_module", addr, {"title": "After reopening"},
            reopened.session.revision, reopened.session.generation,
        ))
        self.assertTrue(reopened.branch.undo())
        self.assertEqual(reopened.session.report_snapshot(), expected)
        self.assertTrue(reopened.branch.redo())
        self.assertEqual(reopened.session.report_snapshot().modules[0].title.original,
                         "After reopening")

    def test_first_save_save_as_migrates_settings_and_keeps_original(self):
        from reportmaker.v2.app import V2MainWindow
        first = self.folder / "first.rmproj"
        second = self.folder / "second.rmproj"
        first_module = self.win.session.report_snapshot().modules[0].id
        self.win.branch._selected_module_id = first_module
        unsaved_identity = self.store.key_for(self.win.session)
        self.assertTrue(self.win.save_project(first))
        first_identity = self.store.key_for(self.win.session)
        self.assertNotEqual(first_identity, unsaved_identity)
        self.assertTrue(self.settings.contains(unsaved_identity))
        self.assertTrue(self.settings.contains(first_identity))
        self.assertTrue(self.win.save_project_as(second))
        second_identity = self.store.key_for(self.win.session)
        self.assertNotEqual(second_identity, first_identity)
        self.assertTrue(self.settings.contains(first_identity))
        self.assertTrue(self.settings.contains(second_identity))
        self.assertEqual(load_project(first).report.id, load_project(second).report.id)
        reopened = V2MainWindow(project=load_project(second), presentation=self.store)
        self._windows.append(reopened)
        self.assertEqual(reopened.branch._selected_module_id, first_module)

    def test_cancelled_and_failed_save_as_preserve_file_identity_and_settings(self):
        first = self.folder / "first.rmproj"
        self.assertTrue(self.win.save_project(first))
        old_key = self.store.key_for(self.win.session)
        old_bytes = first.read_bytes()
        self._rename("Unsaved chapter")
        blocked = self.folder / "existing.rmproj"
        blocked.write_bytes(b"unchanged")
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No):
            self.assertFalse(self.win.save_project_as(blocked))
        self.assertEqual(blocked.read_bytes(), b"unchanged")
        occupied = self.folder / "parent-file"
        occupied.write_bytes(b"not a directory")
        failure = occupied / "cannot-create.rmproj"
        with patch.object(QMessageBox, "critical"):
            self.assertFalse(self.win.save_project_as(failure))
        self.assertEqual(self.win.session.path, first)
        self.assertEqual(self.store.key_for(self.win.session), old_key)
        self.assertFalse(self.settings.contains(self.store.identity(
            self.win.session.report_snapshot().id, failure)))
        self.assertEqual(first.read_bytes(), old_bytes)
        self.assertTrue(self.win.session.dirty)

    def test_save_as_same_destination_does_not_prompt_for_overwrite(self):
        from PySide6.QtWidgets import QMessageBox
        target = self.folder / "current.rmproj"
        self.assertTrue(self.win.save_project(target))
        original_bytes = target.read_bytes()
        with patch.object(QMessageBox, "question") as confirm, \
             patch.object(QMessageBox, "warning") as warn:
            self.assertFalse(self.win.save_project_as(target))
        confirm.assert_not_called()
        warn.assert_called_once()
        self.assertEqual(target.read_bytes(), original_bytes)
        self.assertEqual(self.win.session.path, target)

    def _stage_title_draft(self, text="Typed but not applied"):
        original = self.win.session.report_snapshot()
        address = NodeAddress(original.id, original.modules[0].id)
        editor = self.win.branch.editor_for(address)
        editor.setText(text)
        editor.textEdited.emit(editor.text())
        self.assertTrue(self.win.branch.drafts.pending)
        return original, address

    def test_save_applies_pending_drafts_instead_of_refusing(self):
        from PySide6.QtWidgets import QMessageBox
        original, address = self._stage_title_draft()
        target = self.folder / "autosaved.rmproj"
        with patch.object(QMessageBox, "warning") as warn:
            self.assertTrue(self.win.save_project(target))
            warn.assert_not_called()
        self.assertFalse(self.win.branch.drafts.pending)
        saved = load_project(target).report
        self.assertEqual(saved.modules[0].title.original, "Typed but not applied")
        self.assertEqual(self.win.session.report_snapshot().modules[0].title.original,
                         "Typed but not applied")
        # The applied text is one ordinary undoable step.
        self.assertTrue(self.win.branch.undo())
        self.assertEqual(self.win.session.report_snapshot().modules[0].title.original,
                         original.modules[0].title.original)

    def test_save_as_also_applies_pending_drafts(self):
        self._stage_title_draft("Applied by Save As")
        target = self.folder / "saveas.rmproj"
        self.assertTrue(self.win.save_project_as(target))
        self.assertEqual(load_project(target).report.modules[0].title.original,
                         "Applied by Save As")

    def test_new_open_and_close_apply_drafts_then_ask_before_discarding(self):
        from PySide6.QtWidgets import QMessageBox
        existing = self.folder / "existing.rmproj"
        save_project(ReportProject(blank_report("Other synthetic customer")), existing)
        original, address = self._stage_title_draft()
        generation = self.win.session.generation
        cancel = QMessageBox.StandardButton.Cancel
        with patch.object(QMessageBox, "warning") as warn, \
                patch.object(QMessageBox, "question", return_value=cancel) as ask:
            self.assertFalse(self.win.open_project(existing))
            self.assertFalse(self.win.new_project("Different customer"))
            self.assertFalse(self.win.close())
            warn.assert_not_called()
            # The edit was applied, so the usual Save/Discard/Cancel question
            # protects it; cancelling keeps the project and the typed text.
            self.assertGreaterEqual(ask.call_count, 3)
        self.assertFalse(self.win.branch.drafts.pending)
        self.assertEqual(self.win.session.generation, generation)
        self.assertEqual(self.win.session.report_snapshot().modules[0].title.original,
                         "Typed but not applied")

    def test_unappliable_draft_refuses_everything_and_is_kept(self):
        from PySide6.QtWidgets import QMessageBox
        from reportmaker.v2.session import StaleIntentError
        existing = self.folder / "existing.rmproj"
        save_project(ReportProject(blank_report("Other synthetic customer")), existing)
        original, address = self._stage_title_draft()
        generation = self.win.session.generation
        failure = StaleIntentError("Source changed since editing began; draft preserved")
        with patch.object(self.win.branch.drafts, "apply_all", side_effect=failure), \
                patch.object(QMessageBox, "warning") as warn:
            self.assertFalse(self.win.save_project(self.folder / "should-not-save.rmproj"))
            self.assertFalse(self.win.open_project(existing))
            self.assertFalse(self.win.new_project("Different customer"))
            self.assertFalse(self.win.close())
            self.assertGreaterEqual(warn.call_count, 4)
            self.assertIn("Source changed", warn.call_args.args[2])
        self.assertFalse((self.folder / "should-not-save.rmproj").exists())
        self.assertEqual(self.win.session.report_snapshot(), original)
        self.assertEqual(self.win.session.generation, generation)
        self.assertEqual(self.win.branch.drafts.text(address), "Typed but not applied")

    def test_open_cancel_discard_and_invalid_archive_keep_canonical_project(self):
        from PySide6.QtWidgets import QMessageBox
        valid = self.folder / "other.rmproj"
        invalid = self.folder / "invalid.rmproj"
        save_project(ReportProject(blank_report("Other synthetic customer")), valid)
        invalid.write_bytes(b"not an archive")
        self._rename("Keep unsaved content")
        old = deepcopy(self.win.session.report_snapshot())
        generation = self.win.session.generation
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.win.open_project(valid))
        self.assertEqual(self.win.session.report_snapshot(), old)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Discard):
            with patch.object(QMessageBox, "critical"):
                self.assertFalse(self.win.open_project(invalid))
        self.assertEqual(self.win.session.report_snapshot(), old)
        self.assertEqual(self.win.session.generation, generation)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.win.open_project(valid))
        self.assertNotEqual(self.win.session.generation, generation)
        self.assertEqual(self.win.session.path, valid)
        self.assertFalse(self.win.session.dirty)
        self.assertEqual(self.win.session.report_snapshot().customer_snapshot.customer_name,
                         "Other synthetic customer")

    def test_new_prompts_for_customer_and_preserves_unsaved_on_cancel(self):
        from PySide6.QtWidgets import QMessageBox, QInputDialog
        initial = self.win.session.report_snapshot()
        with patch.object(QInputDialog, "getText", return_value=("", False)):
            self.assertFalse(self.win.new_project())
        self.assertEqual(self.win.session.report_snapshot(), initial)
        with patch.object(QInputDialog, "getText", return_value=("New manual customer", True)):
            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Discard):
                self.assertTrue(self.win.new_project())
        after = self.win.session.report_snapshot()
        self.assertEqual(after.customer_snapshot.customer_name, "New manual customer")
        self.assertIsNone(after.customer_id)
        self.assertNotEqual(after.id, initial.id)
        self.assertEqual(after.ordered_sections()[-1].id, after.conclusion.id)

    def test_legacy_open_save_routes_to_save_as_without_overwriting_source(self):
        base = self.folder / "base.rmproj"
        source = self.folder / "legacy.rmproj"
        upgraded = self.folder / "upgraded.rmproj"
        save_project(ReportProject(blank_report("Legacy test customer")), base)
        with ZipFile(base) as archive:
            legacy = json.loads(archive.read("manifest.json"))
        legacy["version"] = 3
        legacy["report"].pop("localization_ledger")
        with ZipFile(source, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(legacy))
        original_bytes = source.read_bytes()
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.win.open_project(source))
        self.assertEqual(self.win.session.loaded_version, 3)
        # The pure adapter must enforce legacy protection even if called
        # without the toolbar/UI safeguards.
        with self.assertRaisesRegex(ValueError, "Legacy projects require Save As"):
            self.win.persistence.save(self.win.session)
        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertEqual(self.win.session.path, source)
        self.assertEqual(self.win.session.loaded_version, 3)
        with patch.object(self.win, "_choose_save_path", return_value=upgraded):
            self.assertTrue(self.win.save_project())
        self.assertEqual(self.win.session.loaded_version, 5)
        self.assertIn("schema v5", self.win.statusBar().currentMessage())
        self.assertIn("V1", self.win.statusBar().currentMessage())
        self.assertEqual(self.win.session.path, upgraded)
        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertEqual(load_project(upgraded).report.id,
                         load_project(source).report.id)

    def test_actions_and_basic_render_benchmark(self):
        from PySide6.QtGui import QAction
        from reportmaker.v2.app import V2MainWindow
        for name in ("v2NewProject", "v2OpenProject", "v2SaveProject",
                     "v2SaveProjectAs", "v2AddModule", "v2UndoChange"):
            self.assertIsInstance(self.win.findChild(QAction, name), QAction)
        report = blank_report("Large synthetic report")
        report.modules[0].blocks.extend(
            ParagraphBlock(LocalizedText("en", f"Synthetic paragraph {i}"))
            for i in range(80)
        )
        large = V2MainWindow(report, presentation=self.store)
        self._windows.append(large)
        started = time.perf_counter()
        large.show()
        self.app.processEvents()
        duration = time.perf_counter() - started
        print(f"M1.4 Windows offline 82-node initial render: {duration:.3f}s")
        self.assertEqual(len(large.branch.visible_nodes), 83)
        self.assertLess(duration, 20.0)


if __name__ == "__main__":
    unittest.main()
