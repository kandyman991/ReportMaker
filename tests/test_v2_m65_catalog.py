"""M6.5 pre-schema localization contract tests (synthetic reports only).

These gates do not claim v5 persistence, UI translation or DOCX/PDF wiring.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportmaker.model import NestedModuleBlock, PageBreakBlock, Module, LocalizedText
from reportmaker.project_io import VERSION, load_project, save_project
from reportmaker.v2.metadata_locale import (
    ALL_KEYS, ENGLISH_LABELS, PERSISTABLE_KEYS, TRANSIENT_EXPORT_KEYS,
    LocaleApproval, MetadataLocale,
    MetadataTranslationRequiredError, source_digest, visible_metadata_keys,
)
from test_v2_m6 import synthetic_project


class MetadataLocaleContractTests(unittest.TestCase):
    def setUp(self):
        self.project = synthetic_project()
        self.report = self.project.report

    def test_generated_label_source_is_english_even_in_nonenglish_report(self):
        self.report.primary_language = "it"
        locale = MetadataLocale(self.report)
        self.assertEqual(locale.source("heading.summary"), ("Summary", "en"))
        self.assertEqual(locale.resolve("heading.summary", "en"), "Summary")
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Missing"):
            locale.resolve("heading.summary", "it")
        saved = locale.approve("heading.summary", "it", "Sommario")
        self.assertEqual(MetadataLocale(self.report, [saved]).resolve(
            "heading.summary", "IT"), "Sommario")

    def test_open_ended_language_and_unicode_preserve_source(self):
        baseline = deepcopy(self.report)
        builder = MetadataLocale(self.report)
        language = "fr-CA-1996"
        record = builder.approve("field.customer", language, "Clientèle — 漢字")
        locale = MetadataLocale(self.report, [record])
        self.assertEqual(locale.resolve("field.customer", "FR-ca-1996"),
                         "Clientèle — 漢字")
        self.assertEqual(self.report, baseline)
        self.assertEqual(record.source_sha256, source_digest(
            "field.customer", "en", "Customer"))

    def test_stale_metadata_does_not_silently_reuse_old_translation(self):
        self.report.intervention_types = ["other"]
        self.report.other_intervention_detail = "Replace worn synthetic seal"
        record = MetadataLocale(self.report).approve(
            "metadata.other_intervention_detail", "de",
            "Ersetze die synthetische Dichtung")
        old = deepcopy(self.report)
        locale = MetadataLocale(self.report, [record])
        self.assertEqual(locale.resolve("metadata.other_intervention_detail", "de"),
                         "Ersetze die synthetische Dichtung")
        self.assertEqual(self.report, old)
        self.report.other_intervention_detail = "Inspect valve before replacement"
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Outdated"):
            locale.resolve("metadata.other_intervention_detail", "de")
        self.assertEqual(locale.resolve("metadata.other_intervention_detail", "en"),
                         "Inspect valve before replacement")

    def test_relabelled_source_language_stales_metadata_translation(self):
        self.report.intervention_types = ["other"]
        self.report.other_intervention_detail = "Checked"
        record = MetadataLocale(self.report).approve(
            "metadata.other_intervention_detail", "de", "Geprüft")
        self.report.primary_language = "it"
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Outdated"):
            MetadataLocale(self.report, [record]).resolve(
                "metadata.other_intervention_detail", "de")
        # English generated labels stay English after changing report language.
        self.assertEqual(MetadataLocale(self.report).resolve("label.page", "en"),
                         "Page")

    def test_missing_blank_and_malformed_provenance_fail_closed(self):
        locale = MetadataLocale(self.report)
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Missing"):
            locale.resolve("heading.report_information", "de")
        value = locale.approve("heading.report_information", "de", "Berichtsdaten")
        with self.assertRaisesRegex(ValueError, "nonblank"):
            locale.approve("heading.report_information", "de", " \t ")
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Blank"):
            MetadataLocale(self.report, [LocaleApproval(
                value.key, value.language, " ", value.source_sha256)]).resolve(
                    "heading.report_information", "de")
        with self.assertRaisesRegex(ValueError, "digest"):
            MetadataLocale(self.report, [LocaleApproval(
                value.key, value.language, value.text, "not-hex")])

    def test_unknown_keys_source_collision_and_duplicate_casing_rejected(self):
        locale = MetadataLocale(self.report)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            locale.source("unknown.secret")
        with self.assertRaisesRegex(ValueError, "canonical source"):
            locale.approve("heading.summary", "en", "Override")
        valid = locale.approve("heading.summary", "de", "Zusammenfassung")
        variants = [valid, LocaleApproval(valid.key, "DE", "Andere",
                                           valid.source_sha256)]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            MetadataLocale(self.report, variants)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            MetadataLocale(self.report, [LocaleApproval(
                "arbitrary.key", "de", "abc", valid.source_sha256)])
        with self.assertRaises(ValueError):
            locale.resolve("heading.summary", "../de")

    def test_label_registry_is_immutable_and_not_hardcoded_to_locales(self):
        self.assertIn("field.intervention_types", ENGLISH_LABELS)
        self.assertIn("intervention.extraordinary_maintenance", ENGLISH_LABELS)
        self.assertIn("branding.footer_note", ALL_KEYS)
        self.assertIn("branding.footer_note", TRANSIENT_EXPORT_KEYS)
        self.assertNotIn("branding.footer_note", PERSISTABLE_KEYS)
        self.assertIn("metadata.other_intervention_detail", PERSISTABLE_KEYS)
        self.assertTrue(PERSISTABLE_KEYS.isdisjoint(TRANSIENT_EXPORT_KEYS))
        with self.assertRaises(TypeError):
            ENGLISH_LABELS["field.customer"] = "changed"

    def test_visible_keys_are_derived_from_report_and_selected_type(self):
        names = visible_metadata_keys(self.report)
        self.assertEqual(names[:3], (
            "heading.report_information", "heading.summary", "label.page"))
        self.assertNotIn("metadata.other_intervention_detail", names)
        self.assertNotIn("field.ticket", names)  # empty row omitted by exporter
        self.report.intervention_types = ["supervision", "other"]
        self.report.other_intervention_detail = "Synthetic remark"
        names = visible_metadata_keys(
            self.report, preview=True, footer_note="Private source footer")
        self.assertIn("heading.report_content", names)
        self.assertIn("field.intervention_types", names)
        self.assertIn("intervention.supervision", names)
        self.assertIn("intervention.other", names)
        self.assertIn("metadata.other_intervention_detail", names)
        self.assertIn("branding.footer_note", names)
        self.assertIn("preview.footer_prefix", names)
        self.assertIn("preview.summary_detail", names)
        self.assertNotIn("preview.manual_page_break", names)
        self.assertEqual(len(names), len(set(names)))

    def test_export_info_preflight_matches_visible_rows_and_omits_empty_ones(self):
        from reportmaker.export import prepare_export
        plan = prepare_export(self.project)
        self.assertNotIn(("Ticket", ""), plan.info)
        required = visible_metadata_keys(self.report)
        emitted = set()
        for label, _value in plan.info:
            semantic_keys = [
                key for key, english in ENGLISH_LABELS.items()
                if english == label
            ]
            self.assertEqual(len(semantic_keys), 1, label)
            self.assertIn(semantic_keys[0], required)
            emitted.add(semantic_keys[0])
        self.assertEqual(
            {key for key in required if key.startswith("field.")}, emitted)
        self.assertNotIn("field.ticket", required)

        # A missing translation for a *visible* row must still fail closed,
        # while hidden/empty rows do not impose extraneous locale approvals.
        builder = MetadataLocale(self.report)
        approvals = [
            builder.approve(key, "fr", f"Label {i}")
            for i, key in enumerate(required)
            if key in ENGLISH_LABELS and key != "field.customer"
        ]
        with self.assertRaisesRegex(MetadataTranslationRequiredError,
                                    "field.customer"):
            MetadataLocale(self.report, approvals).resolve_many(required, "fr")
        self.report.ticket = "FAKE-123"
        self.assertIn(("Ticket", "FAKE-123"), prepare_export(self.project).info)
        self.assertIn("field.ticket", visible_metadata_keys(self.report))

    def test_absent_footer_must_not_borrow_report_writing_language(self):
        with self.assertRaisesRegex(ValueError, "not declared"):
            MetadataLocale(self.report).source("branding.footer_note")
        with self.assertRaisesRegex(ValueError, "not declared"):
            MetadataLocale(self.report).resolve("branding.footer_note", "en")

    def test_footer_note_is_translatable_but_company_identity_is_not(self):
        builder = MetadataLocale(self.report, footer_note="Synthetic care notice",
                                 footer_source_language="en")
        self.assertEqual(builder.source("branding.footer_note"),
                         ("Synthetic care notice", "en"))
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Missing"):
            builder.resolve("branding.footer_note", "it")
        approved = builder.approve("branding.footer_note", "it", "Avviso sintetico")
        locale = MetadataLocale(self.report, [approved],
                                footer_note="Synthetic care notice",
                                footer_source_language="en")
        self.assertEqual(locale.resolve("branding.footer_note", "it"),
                         "Avviso sintetico")
        changed_footer = MetadataLocale(self.report, [approved],
                                        footer_note="Different private warning",
                                        footer_source_language="en")
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Outdated"):
            changed_footer.resolve("branding.footer_note", "it")

    def test_empty_free_text_does_not_create_a_translated_value(self):
        builder = MetadataLocale(self.report)
        self.assertEqual(builder.resolve("metadata.other_intervention_detail", "de"), "")
        with self.assertRaisesRegex(ValueError, "invent"):
            builder.approve("metadata.other_intervention_detail", "de",
                            "Fabricated target-only metadata")

    def test_atomic_many_resolution_rejects_any_missing_key(self):
        base = MetadataLocale(self.report)
        one = base.approve("heading.summary", "it", "Sommario")
        locale = MetadataLocale(self.report, [one])
        self.assertEqual(locale.resolve_many(["heading.summary"], "it"),
                         {"heading.summary": "Sommario"})
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Missing"):
            locale.resolve_many(["heading.summary", "field.customer"], "it")
        with self.assertRaises(ValueError):
            locale.resolve_many(("heading.summary", "unapproved.label"), "it")

    def test_approval_shape_round_trip_without_persisting_v5(self):
        original = deepcopy(self.project.report)
        approval = MetadataLocale(self.report).approve(
            "field.machine", "de", "Maschine")
        replay = LocaleApproval(**asdict(approval))
        self.assertEqual(MetadataLocale(self.report, [replay]).resolve(
            "field.machine", "de"), "Maschine")
        # No v5 JSON keys may sneak into current project persistence.
        self.assertEqual(VERSION, 5)
        with TemporaryDirectory() as d:
            path = Path(d) / "existing-format.rmproj"
            save_project(self.project, path)
            reopened = load_project(path)
            self.assertEqual(reopened.report, original)
            self.assertEqual(reopened.loaded_version, 5)

    def test_source_digest_binds_semantic_identity(self):
        self.assertNotEqual(source_digest("heading.summary", "en", "Same"),
                            source_digest("heading.report_information", "en", "Same"))
        self.assertNotEqual(source_digest("heading.summary", "en", "Same"),
                            source_digest("heading.summary", "it", "Same"))
        self.assertEqual(source_digest("field.customer", "EN", "Customer"),
                         source_digest("field.customer", "en", "Customer"))

    def test_source_digest_rejects_oversized_untrusted_source(self):
        with self.assertRaisesRegex(ValueError, "source"):
            source_digest("field.ticket", "en", "x" * 321)
        with self.assertRaisesRegex(ValueError, "source"):
            source_digest("metadata.other_intervention_detail", "en",
                          "x" * 10001)

    def test_reject_excessive_entry_count_and_overlong_labels(self):
        record = MetadataLocale(self.report).approve(
            "field.customer", "de", "Kunde")
        with self.assertRaisesRegex(ValueError, "number"):
            MetadataLocale(self.report, [record] * 4097)
        with self.assertRaisesRegex(ValueError, "nonblank"):
            MetadataLocale(self.report).approve("field.customer", "de", "x" * 321)

    def test_untrusted_approvals_reject_xml_invalid_codepoints(self):
        builder = MetadataLocale(self.report)
        good = builder.approve("field.customer", "de", "Kunde")
        for invalid in ("K\\x00unde", "K\\ud800unde", "K\\ufffeunde"):
            # Decode escapes inside the test: GitHub source stays UTF-8.
            value = invalid.encode("ascii").decode("unicode_escape")
            with self.subTest(character=repr(value)):
                with self.assertRaisesRegex(ValueError, "nonblank|length"):
                    builder.approve("field.customer", "de", value)
                with self.assertRaisesRegex(ValueError, "length"):
                    MetadataLocale(self.report, [LocaleApproval(
                        good.key, good.language, value, good.source_sha256)])
        with self.assertRaises(ValueError):
            source_digest("heading.summary", "en", None)
        with self.assertRaises(ValueError):
            builder.resolve([], "de")

    def test_forged_target_only_free_text_is_never_resolved(self):
        builder = MetadataLocale(self.report)
        key = "metadata.other_intervention_detail"
        empty = builder.source(key)
        self.assertFalse(empty[0])
        forged = LocaleApproval(key, "de", "Fabricated only in German",
                                source_digest(key, empty[1], empty[0]))
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Fabricated"):
            MetadataLocale(self.report, [forged]).resolve(key, "de")
        # Whitespace-only source is not meaningful customer prose either.
        foot = MetadataLocale(self.report, footer_note="   ",
                              footer_source_language="en")
        with self.assertRaisesRegex(ValueError, "invent"):
            foot.approve("branding.footer_note", "de", "Invented")

    def test_branding_source_language_must_be_declared_independently(self):
        self.report.primary_language = "it"
        with self.assertRaisesRegex(ValueError, "explicit source language"):
            MetadataLocale(self.report, footer_note="English legal note")
        builder = MetadataLocale(self.report, footer_note="English legal note",
                                 footer_source_language="en")
        self.assertEqual(builder.source("branding.footer_note"),
                         ("English legal note", "en"))
        record = builder.approve("branding.footer_note", "it", "Nota legale")
        self.assertEqual(MetadataLocale(
            self.report, [record], footer_note="English legal note",
            footer_source_language="en").resolve("branding.footer_note", "it"),
            "Nota legale")
        with self.assertRaisesRegex(MetadataTranslationRequiredError, "Outdated"):
            MetadataLocale(
                self.report, [record], footer_note="English legal note",
                footer_source_language="de").resolve("branding.footer_note", "it")

    def test_preview_localization_follows_nested_manual_page_break(self):
        self.assertNotIn("preview.manual_page_break",
                         visible_metadata_keys(self.report, preview=True))
        nested = Module(LocalizedText(self.report.primary_language, "Nested"),
                        blocks=[PageBreakBlock()])
        self.report.modules[0].blocks.append(NestedModuleBlock(nested))
        keys = visible_metadata_keys(self.report, preview=True)
        self.assertIn("preview.manual_page_break", keys)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertNotIn("preview.manual_page_break",
                         visible_metadata_keys(self.report, preview=False))

    def test_invisible_only_approval_and_oversized_resolution_fail_closed(self):
        builder = MetadataLocale(self.report)
        approved = builder.approve("field.customer", "de", "Kunde")
        for invisible in ("\\u200b", "\\u2060", "\\u0301"):
            value = invisible.encode("ascii").decode("unicode_escape")
            with self.subTest(text=repr(value)):
                with self.assertRaisesRegex(ValueError, "nonblank"):
                    builder.approve("field.customer", "de", value)
                record = LocaleApproval(approved.key, approved.language,
                                        value, approved.source_sha256)
                with self.assertRaisesRegex(
                        MetadataTranslationRequiredError, "Blank"):
                    MetadataLocale(self.report, [record]).resolve("field.customer", "de")
        with self.assertRaisesRegex(ValueError, "sequence"):
            builder.resolve_many(["heading.summary", "heading.summary"], "en")
        with self.assertRaisesRegex(ValueError, "sequence"):
            builder.resolve_many(["heading.summary"] * 1000, "en")
        with self.assertRaisesRegex(ValueError, "footer text"):
            visible_metadata_keys(self.report, footer_note="x" * 10001)

    def test_malformed_customer_free_text_fails_before_source_export(self):
        self.report.intervention_types = ["other"]
        self.report.other_intervention_detail = "Invalid\\x00source".encode("ascii").decode("unicode_escape")
        with self.assertRaisesRegex(ValueError, "metadata source"):
            MetadataLocale(self.report).resolve("metadata.other_intervention_detail", "en")
        self.report.other_intervention_detail = "x" * 10001
        with self.assertRaisesRegex(ValueError, "metadata source"):
            MetadataLocale(self.report).source("metadata.other_intervention_detail")
