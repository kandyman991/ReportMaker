"""M6.5 v5 persistence, atomic approvals and localized export gates.

Synthetic inputs only. No customer reports, external translation or browser.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
import json
import os
import unittest

from reportmaker.export import ExportStyle, prepare_export, export_project
from reportmaker.project_io import VERSION, load_project, save_project
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.language_bundle import export_language_bundle
from reportmaker.v2.localized_export import localized_fields, localized_project
from reportmaker.v2.metadata_locale import (
    ENGLISH_LABELS, MetadataLocale, MetadataTranslationRequiredError,
    resolve_export_metadata, source_digest, visible_metadata_keys,
)
from reportmaker.v2.session import ReportSession, StaleIntentError
from test_v2_m6 import synthetic_project


def locale_project(language="de"):
    project = synthetic_project()
    report = project.report
    report.output_languages = [report.primary_language, language]
    return project


def approve_all(report, language, *, preview=False):
    locale = MetadataLocale(report)
    for key in visible_metadata_keys(report, preview=preview):
        original, original_language = locale.source(key)
        if original_language.casefold() == language.casefold() or not original.strip():
            continue
        record = locale.approve(key, language, "Translated " + original)
        report.localization_ledger.setdefault(key, {})[language] = {
            "text": record.text, "source_sha256": record.source_sha256,
        }


def rewrite_manifest(source: Path, target: Path, edit):
    with ZipFile(source) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assets = {item.filename: archive.read(item.filename)
                  for item in archive.infolist() if item.filename != "manifest.json"}
    edit(manifest)
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, data in assets.items():
            archive.writestr(name, data)


class M65IntegrationTests(unittest.TestCase):
    def test_v5_roundtrip_preserves_detached_provenance_and_source(self):
        project = locale_project()
        source = deepcopy(project.report)
        record = MetadataLocale(project.report).approve(
            "field.customer", "de", "Kunde")
        project.report.localization_ledger = {
            record.key: {record.language: {
                "text": record.text, "source_sha256": record.source_sha256,
            }}
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "native.rmproj"
            save_project(project, path)
            with ZipFile(path) as archive:
                wire = json.loads(archive.read("manifest.json"))
            self.assertEqual(VERSION, 5)
            self.assertEqual(wire["version"], 5)
            self.assertEqual(
                wire["report"]["localization_ledger"]["field.customer"]["de"],
                {"text": "Kunde", "source_sha256": record.source_sha256})
            loaded = load_project(path)
            self.assertEqual(loaded.loaded_version, 5)
            self.assertEqual(loaded.report.localization_ledger,
                             project.report.localization_ledger)
            self.assertEqual(loaded.report.modules, source.modules)
            self.assertEqual(loaded.report.customer_snapshot, source.customer_snapshot)
            self.assertEqual(loaded.assets, project.assets)

    def test_v4_rich_archive_load_save_as_v5_leaves_v4_byte_identical(self):
        project = locale_project()
        with TemporaryDirectory() as directory:
            base = Path(directory) / "v5.rmproj"
            legacy = Path(directory) / "v4.rmproj"
            migrated = Path(directory) / "migrated.rmproj"
            save_project(project, base)
            rewrite_manifest(base, legacy, lambda m: (
                m.__setitem__("version", 4),
                m["report"].pop("localization_ledger")))
            original_bytes = legacy.read_bytes()
            old = load_project(legacy)
            self.assertEqual(old.loaded_version, 4)
            self.assertEqual(old.report.localization_ledger, {})
            self.assertEqual(old.report.modules, project.report.modules)
            with self.assertRaisesRegex(ValueError, "Save As"):
                save_project(old, legacy)
            save_project(old, migrated)
            upgraded = load_project(migrated)
            self.assertEqual(upgraded.loaded_version, 5)
            self.assertEqual(upgraded.report, old.report)
            self.assertEqual(upgraded.assets, project.assets)
            self.assertEqual(legacy.read_bytes(), original_bytes)

    def test_strict_v5_records_unknown_keys_and_old_schema_shape_rejected(self):
        project = locale_project()
        with TemporaryDirectory() as directory:
            base = Path(directory) / "base.rmproj"
            save_project(project, base)
            for i, alter in enumerate((
                lambda m: m["report"]["localization_ledger"].update({
                    "branding.footer_note": {"de": {
                        "text": "Not persistent", "source_sha256": "0" * 64}}}),
                lambda m: m["report"]["localization_ledger"].update({
                    "field.customer": {"de": {
                        "text": "Kunde", "source_sha256": "invalid"}}}),
                lambda m: m["report"]["localization_ledger"].update({
                    "field.customer": {"de": {
                        "text": "Kunde", "source_sha256": "0" * 64,
                        "secret": "unexpected"}}}),
                lambda m: (m.__setitem__("version", 4),
                           m["report"]["localization_ledger"].update({
                               "field.customer": {}})),
                lambda m: m["report"].pop("localization_ledger"),
            )):
                target = Path(directory) / f"invalid{i}.rmproj"
                rewrite_manifest(base, target, alter)
                with self.subTest(i=i), self.assertRaises(ValueError):
                    load_project(target)

    def test_command_requires_current_source_digest_and_undo_redo(self):
        session = ReportSession(locale_project())
        gateway = CommandGateway(session)
        original = session.report_snapshot()
        key, language = "field.customer", "de"
        source, lang = MetadataLocale(original).source(key)
        digest = source_digest(key, lang, source)
        args = {"key": key, "language": language, "text": "Kunde",
                "expected_source_sha256": digest}
        with self.assertRaises(StaleIntentError):
            gateway.execute(CommandIntent(
                "set_metadata_translation", None,
                dict(args, expected_source_sha256="0" * 64),
                session.revision, session.generation))
        self.assertEqual(session.revision, 0)
        self.assertEqual(session.report_snapshot(), original)
        gateway.execute(CommandIntent(
            "set_metadata_translation", None, args,
            session.revision, session.generation))
        self.assertEqual(session.revision, 1)
        self.assertEqual(MetadataLocale(session.report_snapshot()).resolve(key, language),
                         "Kunde")
        self.assertTrue(gateway.undo(session.generation, session.revision))
        self.assertEqual(session.report_snapshot(), original)
        self.assertTrue(gateway.redo(session.generation, session.revision))
        self.assertEqual(MetadataLocale(session.report_snapshot()).resolve(key, language),
                         "Kunde")

    def test_primary_language_preview_labels_without_extra_export_language(self):
        from test_m2_project import example
        project = example()  # authored in it; requested outputs are de/zh only
        self.assertEqual(project.report.primary_language, "it")
        self.assertNotIn("it", project.report.output_languages)
        session = ReportSession(project)
        gateway = CommandGateway(session)
        key = "heading.summary"
        source, src_lang = MetadataLocale(session.report_snapshot()).source(key)
        gateway.execute(CommandIntent(
            "set_metadata_translation", None,
            {"key": key, "language": "it", "text": "Sommario",
             "expected_source_sha256": source_digest(key, src_lang, source)},
            session.revision, session.generation))
        self.assertEqual(
            MetadataLocale(session.report_snapshot()).resolve(key, "it"), "Sommario")
        self.assertNotIn("it", session.report_snapshot().output_languages)

    def test_translated_other_metadata_and_boilerplate_in_render_plan(self):
        project = locale_project()
        report = project.report
        report.intervention_types = ["supervision", "other"]
        report.other_intervention_detail = "Synthetic repair"
        approve_all(report, "de", preview=True)
        labels = resolve_export_metadata(report, "de", preview=True)
        projected = localized_project_with_filled_content(project, "de")
        plan = prepare_export(projected, locale_labels=labels)
        names = dict(plan.info)
        self.assertIn("Translated Intervention types", names)
        self.assertIn("Translated Supervision", names["Translated Intervention types"])
        self.assertIn("Translated Other", names["Translated Intervention types"])
        self.assertEqual(names["Translated Other intervention details"],
                         "Translated Synthetic repair")
        self.assertEqual(plan.locale_labels["heading.summary"],
                         "Translated Summary")
        self.assertEqual(report.other_intervention_detail, "Synthetic repair")

    def test_language_bundle_rolls_back_on_metadata_gap(self):
        project = locale_project()
        for _key, localized in localized_fields(project.report):
            if localized.original.strip():
                localized.set_translation("de", "Translated " + localized.original)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "report.zip"
            target.write_bytes(b"EXISTING ARCHIVE")
            with self.assertRaises(MetadataTranslationRequiredError):
                export_language_bundle(project, target, formats=("docx",))
            self.assertEqual(target.read_bytes(), b"EXISTING ARCHIVE")

    def test_complete_metadata_bundle_emits_translated_labels(self):
        project = locale_project()
        for _key, localized in localized_fields(project.report):
            if localized.original.strip():
                localized.set_translation("de", "Translated " + localized.original)
        approve_all(project.report, "de")
        with TemporaryDirectory() as directory:
            target = Path(directory) / "all.zip"
            export_language_bundle(project, target, formats=("docx",))
            with ZipFile(target) as archive:
                files = archive.namelist()
                self.assertIn("report_de.docx", files)
                manifest = json.loads(archive.read("manifest.json"))
                self.assertIn("Strict approved", manifest["metadata_localization"])
                with ZipFile(__import__("io").BytesIO(
                        archive.read("report_de.docx"))) as doc:
                    xml = doc.read("word/document.xml").decode("utf-8")
                    self.assertIn("Translated Report information", xml)
                    self.assertIn("Translated Summary", xml)

    def test_transient_footer_approvals_cannot_replace_report_ledger(self):
        project = locale_project()
        report = project.report
        approve_all(report, "de")
        report.localization_ledger.pop("field.customer")
        forged = MetadataLocale(report).approve("field.customer", "de", "Kunde")
        # A crafted ExportStyle is presentation data, not a canonical
        # metadata-approval command. Before this guard the forged approval
        # could satisfy a missing report-owned translation during export.
        style = ExportStyle(footer_locale_approvals=(forged,))
        with self.assertRaisesRegex(ValueError, "only the footer"):
            resolve_export_metadata(report, "de", style=style)
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "field.customer"):
            resolve_export_metadata(report, "de")
        self.assertNotIn("field.customer", report.localization_ledger)

    def test_transient_footer_source_language_is_never_inferred(self):
        project = locale_project()
        approve_all(project.report, "de")
        style = ExportStyle(footer_note="Synthetic legal wording")
        with self.assertRaisesRegex(ValueError, "source language"):
            resolve_export_metadata(project.report, "de", style=style)
        from dataclasses import replace
        style = replace(style, footer_source_language="en")
        with self.assertRaises(MetadataTranslationRequiredError):
            resolve_export_metadata(project.report, "de", style=style)
        record = MetadataLocale(
            project.report, [], footer_note=style.footer_note,
            footer_source_language="en").approve(
                "branding.footer_note", "de", "Deutscher Testhinweis")
        style = replace(style, footer_locale_approvals=(record,))
        values = resolve_export_metadata(project.report, "de", style=style)
        self.assertEqual(values["branding.footer_note"], "Deutscher Testhinweis")
        self.assertNotIn("branding.footer_note", project.report.localization_ledger)


def localized_project_with_filled_content(project, language):
    copy = deepcopy(project)
    for _key, localized in localized_fields(copy.report):
        if localized.original.strip():
            localized.set_translation(language, "Translated " + localized.original)
    return localized_project(copy, language)


if __name__ == "__main__":
    unittest.main()
