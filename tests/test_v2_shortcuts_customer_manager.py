"""V2 shortcut policy, plain-text paste and the ported customer manager.

Synthetic data only. Widget tests run under offscreen Qt and are not a
substitute for the physical Windows acceptance cases.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import os
import subprocess
import sys
import unittest

from reportmaker.v2.projections import NodeAddress


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offline Qt CI")
class ShortcutAndCustomerManagerQtTests(TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from reportmaker.v2.app import V2MainWindow, blank_report
        from reportmaker.v2.presentation import PresentationStore
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        settings = QSettings(str(self.folder / "view.ini"), QSettings.Format.IniFormat)
        self.database = self.folder / "customers.sqlite3"
        self.win = V2MainWindow(
            blank_report("Shortcut test customer", today=date(2026, 10, 29)),
            presentation=PresentationStore(settings), load_website=False,
            ephemeral_browser=True, customer_database_path=self.database)
        self.win.show()
        self.pump()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.pump()

    def pump(self):
        for _ in range(4):
            self.app.processEvents()

    def action(self, name):
        from PySide6.QtGui import QAction
        found = self.win.findChild(QAction, name)
        self.assertIsNotNone(found, name)
        return found

    def v2_actions(self):
        from PySide6.QtGui import QAction
        return [a for a in self.win.findChildren(QAction) if a.objectName().startswith("v2")]

    # ------------------------------------------------------- shortcut policy
    def test_every_declared_shortcut_is_a_valid_key_sequence(self):
        # Ctrl+PageUp/PageDown were once silently parsed as an unknown key, so
        # Previous/Next window had no working shortcut. An unparsable chord
        # reports a non-empty sequence whose text is empty.
        with_shortcut = [a for a in self.v2_actions() if not a.shortcut().isEmpty()]
        self.assertGreater(len(with_shortcut), 25)
        for action in with_shortcut:
            self.assertEqual(action.shortcut().count(), 1, action.objectName())
            self.assertNotEqual(action.shortcut().toString(), "", action.objectName())
        self.assertEqual(self.action("v2PrevWindow").shortcut().toString(), "Ctrl+PgUp")
        self.assertEqual(self.action("v2NextWindow").shortcut().toString(), "Ctrl+PgDown")

    def test_no_shortcut_is_shared_and_paste_chords_are_left_alone(self):
        shortcuts = Counter(a.shortcut().toString() for a in self.v2_actions()
                            if not a.shortcut().isEmpty())
        self.assertEqual([k for k, n in shortcuts.items() if n > 1], [])
        # Ctrl+Shift+V is paste-as-plain-text; Ctrl+Shift+Esc belongs to Windows.
        for reserved in ("Ctrl+Shift+V", "Ctrl+Shift+Esc", "Ctrl+Shift+Escape", "Ctrl+V"):
            self.assertNotIn(reserved, shortcuts)
        self.assertEqual(self.action("v2PastePhoto").shortcut().toString(), "Ctrl+Alt+V")
        self.assertEqual(self.action("v2ExitFocus").shortcut().toString(), "Alt+Shift+F")

    # -------------------------------------------------- Ctrl+Shift+V pasting
    def _chord(self):
        from PySide6.QtCore import Qt
        return Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier

    def _key(self, widget, key, modifiers):
        from PySide6.QtTest import QTest
        QTest.keyClick(widget, key, modifiers)
        self.pump()

    def _paragraph_address(self):
        self.win.branch.add_paragraph()
        self.pump()
        report = self.win.session.report_snapshot()
        module = report.modules[0]
        return report, module, NodeAddress(report.id, module.id, module.blocks[-1].id, "text")

    def test_ctrl_shift_v_pastes_plain_text_in_branch_editors(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit
        report, module, address = self._paragraph_address()

        paragraph = self.win.branch.editor_for(address)
        self.assertIsInstance(paragraph, QPlainTextEdit)
        paragraph.setFocus()
        QApplication.clipboard().setText("Corrected by the assistant")
        self._key(paragraph, Qt.Key.Key_V, self._chord())
        self.assertIn("Corrected by the assistant", paragraph.toPlainText())

        title = self.win.branch.editor_for(NodeAddress(report.id, module.id))
        self.assertIsInstance(title, QLineEdit)
        title.clear()
        title.setFocus()
        QApplication.clipboard().setText("Pasted title")
        self._key(title, Qt.Key.Key_V, self._chord())
        self.assertEqual(title.text(), "Pasted title")

    def test_ctrl_shift_v_with_text_never_reaches_the_image_import(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        _report, _module, address = self._paragraph_address()
        editor = self.win.branch.editor_for(address)
        editor.setFocus()
        QApplication.clipboard().setText("plain words")
        self.win.statusBar().clearMessage()
        with mock.patch.object(self.win.branch, "paste_photo") as paste_photo:
            self._key(editor, Qt.Key.Key_V, self._chord())
            paste_photo.assert_not_called()
        self.assertNotIn("Image paste rejected", self.win.statusBar().currentMessage())
        self.assertIn("plain words", editor.toPlainText())

    def test_ctrl_shift_v_pastes_plain_text_in_the_page_editor(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        _report, _module, address = self._paragraph_address()
        self.win.tabs.setCurrentWidget(self.win.editor_tab)
        self.pump()
        editor = self.win.editor_tab._editors[address]
        editor.setFocus()
        QApplication.clipboard().setText("page editor paste")
        self._key(editor, Qt.Key.Key_V, self._chord())
        self.assertIn("page editor paste", editor.toPlainText())

    def test_paste_image_still_imports_a_clipboard_picture_via_its_action(self):
        # Only the chord moved (Ctrl+Shift+V -> Ctrl+Alt+V); the command works.
        from PySide6.QtGui import QColor, QImage
        from PySide6.QtWidgets import QApplication
        picture = QImage(24, 16, QImage.Format.Format_RGB32)
        picture.fill(QColor(30, 90, 160))
        QApplication.clipboard().setImage(picture)
        before = len(self.win.session.assets)
        self.action("v2PastePhoto").trigger()
        self.pump()
        self.assertEqual(len(self.win.session.assets), before + 1)

    # --------------------------------------------------- customer manager
    def test_customer_manager_is_reachable_from_the_project_menu(self):
        from PySide6.QtWidgets import QToolButton
        menu = self.win.findChild(QToolButton, "v2ProjectMenu").menu()
        self.assertIn(self.action("v2CustomerManager"), menu.actions())

    def test_customer_manager_action_opens_the_dialog_on_the_chosen_database(self):
        seen = {}

        def fake_exec(dialog):
            seen["store_path"] = Path(dialog.store.path)
            seen["title"] = dialog.windowTitle()
            return 0

        with mock.patch("reportmaker.v2.customer_manager.CustomerManagerDialog.exec",
                        fake_exec):
            self.action("v2CustomerManager").trigger()
        self.assertEqual(seen["store_path"], self.database)
        self.assertEqual(seen["title"], "Customers, sites and machines")
        self.assertTrue(self.database.exists())

    def test_preview_explains_current_v2_report_workflow(self):
        from reportmaker.reference import manual_snapshot
        from reportmaker.storage import CustomerStore
        from reportmaker.v2.customer_manager import CustomerManagerDialog
        with CustomerStore(self.database) as store:
            dialog = CustomerManagerDialog(store, self.win)
            with mock.patch("reportmaker.v2.customer_manager.QMessageBox") as message:
                dialog._show_snapshot(manual_snapshot("Synthetic customer"))
                text = message.return_value.setText.call_args.args[0]
                self.assertIn("Report info", text)
                self.assertIn("frozen customer details", text)
                self.assertNotIn("M2", text)
                message.return_value.exec.assert_called_once()

    def test_customer_manager_reports_an_unavailable_database(self):
        self.win.customer_database_path = self.folder  # a directory, not a database
        with mock.patch("reportmaker.v2.app.QMessageBox.critical") as critical:
            self.assertFalse(self.win.open_customer_manager())
            critical.assert_called_once()
            self.assertEqual(critical.call_args.args[1], "Customer database unavailable")

    def test_report_info_uses_the_same_customer_database(self):
        seen = {}

        def fake_exec(dialog):
            seen["path"] = dialog.database_path
            return 0

        with mock.patch("reportmaker.v2.report_info.ReportInfoDialog.exec", fake_exec):
            self.win.edit_report_info()
        self.assertEqual(seen["path"], self.database)


class CustomerManagerPortTests(TestCase):
    def test_legacy_import_path_still_resolves_to_the_v2_classes(self):
        from reportmaker import customer_ui
        from reportmaker.v2 import customer_manager
        for name in ("CustomerManagerDialog", "HistoryDialog", "ManualReferenceForm",
                     "RecordForm", "LABELS"):
            self.assertIs(getattr(customer_ui, name), getattr(customer_manager, name))

    def test_v2_manager_does_not_import_the_v1_shell(self):
        # A fresh interpreter: other tests in this process may import the V1 UI.
        import reportmaker
        source = str(Path(reportmaker.__file__).resolve().parent.parent)
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "import reportmaker.v2.customer_manager;"
            "bad = {'reportmaker.ui', 'reportmaker.visual_editor'} & set(sys.modules);"
            "sys.exit(1 if bad else 0)")
        result = subprocess.run([sys.executable, "-I", "-c", code, source],
                                capture_output=True, text=True, timeout=120,
                                env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
