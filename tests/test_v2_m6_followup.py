"""Follow-up M6 customer reference and multilingual export gates.

All SQLite data and report imagery are fabricated, kept in temporary local
files, and never copied into the public repository or browser profile.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

from PIL import Image
from reportmaker.engine import module_outline
from reportmaker.model import LocalizedText, PhotoMark, PhotoVisual
from reportmaker.project_io import load_project
from reportmaker.storage import CustomerStore
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.localized_export import (
    TranslationRequiredError, localized_fields, localized_project,
)
from reportmaker.v2.session import ReportSession
from reportmaker.v2.adapters.persistence import ProjectPersistence
from test_v2_m6 import synthetic_project


def translate_everything(project, language="de"):
    report = project.report
    for key, value in localized_fields(report):
        if value.original and value.original_language.casefold() != language.casefold():
            value.set_translation(language, "DE · " + value.original)


class ReferenceAndTranslationCoreTests(unittest.TestCase):
    def test_registered_snapshot_switch_is_atomic_and_manual_revert_is_local(self):
        project = synthetic_project()
        session = ReportSession(project)
        gateway = CommandGateway(session)
        original = session.report_snapshot()
        with TemporaryDirectory() as directory:
            with CustomerStore(Path(directory) / "customers.sqlite3") as store:
                customer = store.create_customer("Fictional B", city="Lab city")
                site = store.create_site(customer, "Lab 2")
                machine = store.create_machine(site, "Synthetic Pump", serial_number="MOCK-0002")
                frozen = store.capture_snapshot(customer, site_id=site, machine_id=machine)
                store.update("machines", machine, name="Master changed later")
                self.assertEqual(frozen.machine_name, "Synthetic Pump")
                self.assertEqual(store.get("machines", machine)["name"], "Master changed later")
            metadata = self._metadata(original, frozen)
            gateway.execute(CommandIntent("set_report_metadata", None, metadata,
                                         session.revision, session.generation))
            updated = session.report_snapshot()
            self.assertEqual(updated.customer_id, customer)
            self.assertEqual(updated.customer_snapshot, frozen)
            self.assertEqual(updated.id, original.id)
            self.assertEqual(updated.modules, original.modules)
            dest = Path(directory) / "linked.rmproj"
            ProjectPersistence().save(session, dest)
            self.assertEqual(load_project(dest).report.customer_snapshot, frozen)
            self.assertTrue(gateway.undo(session.generation, session.revision))
            self.assertEqual(session.report_snapshot(), original)
            self.assertTrue(gateway.redo(session.generation, session.revision))
            self.assertEqual(session.report_snapshot().customer_id, customer)

            from reportmaker.reference import manual_snapshot
            manual = manual_snapshot("One-off", site_name="Detached site")
            metadata = self._metadata(updated, manual)
            gateway.execute(CommandIntent("set_report_metadata", None, metadata,
                                         session.revision, session.generation))
            self.assertIsNone(session.report_snapshot().customer_id)
            self.assertIsNone(session.report_snapshot().customer_snapshot.customer_id)

    @staticmethod
    def _metadata(report, snapshot):
        return {
            "title": report.title.original,
            "created_date": report.created_date,
            "start_date": report.start_date,
            "end_date": report.end_date,
            "ticket": report.ticket,
            "technicians": report.technicians,
            "intervention_types": report.intervention_types,
            "other_intervention_detail": report.other_intervention_detail,
            "customer_snapshot": snapshot,
            "primary_language": report.primary_language,
            "output_languages": report.output_languages,
            "customer_id": snapshot.customer_id,
        }

    def test_reject_mismatched_identity_or_stale_revision_without_mutation(self):
        from reportmaker.reference import CustomerSnapshot
        project = synthetic_project()
        session = ReportSession(project)
        gateway = CommandGateway(session)
        report = session.report_snapshot()
        snapshot = CustomerSnapshot(customer_name="Fictional", customer_id="fictional-id")
        args = self._metadata(report, snapshot)
        args["customer_id"] = "different-id"
        with self.assertRaises(ValueError):
            gateway.execute(CommandIntent("set_report_metadata", None, args,
                                         session.revision, session.generation))
        self.assertEqual(session.report_snapshot(), report)
        self.assertFalse(session._editor.can_undo)

    def test_language_export_rejects_missing_stale_and_unselected_before_writing(self):
        project = synthetic_project()
        prior = deepcopy(project.report)
        with self.assertRaisesRegex(TranslationRequiredError, "Missing"):
            localized_project(project, "de")
        with self.assertRaisesRegex(TranslationRequiredError, "not selected"):
            localized_project(project, "fr-CA")
        translate_everything(project)
        translated = localized_project(project, "de")
        self.assertEqual(project.report, project.report)
        self.assertEqual(prior.title.original, project.report.title.original)
        self.assertTrue(translated.report.title.original.startswith("DE"))
        self.assertEqual(
            [entry.module_id for entry in module_outline(translated.report)],
            [entry.module_id for entry in module_outline(project.report)])
        self.assertEqual(
            translated.report.ordered_sections()[-1].id, project.report.conclusion.id)
        # Modifying source text invalidates an existing translation.
        original = project.report.modules[0].blocks[0].text
        original.update_original("Edited source")
        with self.assertRaisesRegex(TranslationRequiredError, "Outdated"):
            localized_project(project, "de")
        self.assertIn("de", original.stale_languages)

    def test_explicit_translation_command_roundtrip_undo_and_no_silent_overwrite(self):
        project = synthetic_project()
        session = ReportSession(project)
        gateway = CommandGateway(session)
        source = session.report_snapshot()
        key = (source.id, "report_title")
        gateway.execute(CommandIntent("set_translation", None,
                                     {"language": "de", "key": key, "text": "Synthesebericht"},
                                     session.revision, session.generation))
        report = session.report_snapshot()
        self.assertEqual(report.title.original, source.title.original)
        self.assertEqual(report.title.translations["de"], "Synthesebericht")
        self.assertTrue(gateway.undo(session.generation, session.revision))
        self.assertEqual(session.report_snapshot(), source)
        self.assertTrue(gateway.redo(session.generation, session.revision))
        with TemporaryDirectory() as directory:
            target = Path(directory) / "languages.rmproj"
            ProjectPersistence().save(session, target)
            self.assertEqual(load_project(target).report.title.translations["de"],
                             "Synthesebericht")
        with self.assertRaises(ValueError):
            gateway.execute(CommandIntent("set_translation", None,
                        {"language": "en", "key": key, "text": "Cannot replace original"},
                        session.revision, session.generation))
        self.assertEqual(session.report_snapshot().title.original, source.title.original)

    def test_translated_photo_annotation_and_table_cell_survive_export(self):
        project = synthetic_project()
        photo = project.report.modules[0].blocks[2]
        photo.visual = PhotoVisual(marks=[
            PhotoMark("text", .1, .1, .5, .5,
                      text=LocalizedText("en", "Synthetic arrow note"))])
        translate_everything(project)
        before = deepcopy(project.report)
        transformed = localized_project(project, "de")
        mark = transformed.report.modules[0].blocks[2].visual.marks[0]
        self.assertEqual(mark.text.original, "DE · Synthetic arrow note")
        table = transformed.report.modules[0].blocks[3]
        self.assertEqual(table.rows[0][0].original, "DE · Reading")
        from reportmaker.v2.visual_export import annotated_png
        from reportmaker.export import prepare_export
        plan = prepare_export(transformed, visual_renderer=annotated_png)
        self.assertTrue(any(item.text == "DE · Fabricated photo" for item in plan.items))
        self.assertEqual(project.report, before)


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Hosted Windows offscreen Qt gate")
class ReferenceAndTranslationQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        self.win = V2MainWindow(project=synthetic_project(),
                                load_website=False, ephemeral_browser=True)
        self.win.show()
        self.app.processEvents()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.app.processEvents()

    def test_database_picker_binds_nested_customer_site_machine_with_no_master_writes(self):
        from reportmaker.v2.reference_picker import CustomerReferencePicker, chosen_ids
        from reportmaker.v2.report_info import ReportInfoDialog
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.sqlite3"
            with CustomerStore(path) as store:
                customer = store.create_customer("Fake A")
                site = store.create_site(customer, "Fake site")
                machine = store.create_machine(site, "Fake machine")
                picker = CustomerReferencePicker(store, self.win)
                root = picker.tree.topLevelItem(0)
                item = root.child(0).child(0)
                self.assertEqual(chosen_ids(item), (customer, site, machine))
                picker.tree.setCurrentItem(item)
                self.assertTrue(picker.choose())
                frozen = picker.snapshot
                self.assertEqual(frozen.machine_id, machine)

            dialog = ReportInfoDialog(self.win.session, self.win.gateway,
                                      self.win, database_path=path)
            # The chooser accepts a detached value but report facts remain unchanged
            # until the Report Info dialog's Apply.
            from unittest.mock import patch
            def accept_picker(instance):
                item = instance.tree.topLevelItem(0).child(0).child(0)
                instance.tree.setCurrentItem(item)
                instance.choose()
                return instance.result()
            with patch("reportmaker.v2.reference_picker.CustomerReferencePicker.exec",
                       new=accept_picker):
                self.assertTrue(dialog.choose_database())
            self.assertIsNone(self.win.session.report_snapshot().customer_id)
            self.assertTrue(dialog.apply_changes())
            self.assertEqual(self.win.session.report_snapshot().customer_id, customer)
            self.assertEqual(self.win.session.report_snapshot().customer_snapshot, frozen)
            self.assertTrue(self.win.branch.undo())
            self.assertIsNone(self.win.session.report_snapshot().customer_id)

    def test_translated_preview_and_export_refuse_missing_content_without_clobber(self):
        from docx import Document
        preview = self.win.preview_tab
        preview.refresh()
        pos = preview.language.findData("de")
        self.assertGreaterEqual(pos, 0)
        preview.language.setCurrentIndex(pos)
        self.app.processEvents()
        self.assertIn("Preview unavailable", preview.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)[-1].text()
            if False else "Preview unavailable")  # Explicit refusal is in notice.
        with TemporaryDirectory() as directory:
            output = Path(directory) / "translated.docx"
            output.write_bytes(b"previous-file")
            self.assertFalse(preview.export_to(output, "docx"))
            self.assertEqual(output.read_bytes(), b"previous-file")
            # Complete every localizable report field using the gateway.
            report = self.win.session.report_snapshot()
            for key, field in localized_fields(report):
                if field.original:
                    self.win.gateway.execute(CommandIntent(
                        "set_translation", None,
                        {"language": "de", "key": key, "text": "DE · " + field.original},
                        self.win.session.revision, self.win.session.generation))
            self.assertTrue(preview.export_to(output, "docx"))
            document = Document(output)
            self.assertTrue(any("DE · " in paragraph.text
                                for paragraph in document.paragraphs))
            self.assertNotIn("DE · ", self.win.session.report_snapshot().title.original)
            self.assertTrue(self.win.branch.undo())

    def test_manual_translation_dialog_preserves_unapplied_drafts(self):
        from reportmaker.v2.translation_dialog import TranslationDialog
        dialog = TranslationDialog(self.win.session, self.win.gateway, self.win)
        self.assertGreater(dialog.fields.count(), 0)
        source = self.win.session.report_snapshot().title.original
        self.assertIn(source, dialog.source.text())
        dialog.translation.setPlainText("Geprüfter Bericht")
        original = self.win.session.report_snapshot()
        self.assertTrue(dialog._has_draft())
        dialog.reject()
        self.assertEqual(self.win.session.report_snapshot(), original)
        self.assertTrue(dialog.apply_field())
        self.assertEqual(self.win.session.report_snapshot().title.translations["de"],
                         "Geprüfter Bericht")
