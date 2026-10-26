import unittest
from datetime import date

from reportmaker.model import (
    LocalizedText, ParagraphBlock, PhotoBlock, Module, NestedModuleBlock,
    Report, TableBlock, validate_language_tag,
)


def local(s="Example", language="en"):
    return LocalizedText(language, s)


def make_report(**kwargs):
    args = dict(
        customer_id="synthetic-customer",
        start_date=date(2026, 5, 20),
        end_date=date(2026, 5, 22),
        primary_language="en",
        output_languages=["en", "zh-Hant-TW", "de"],
        conclusion=Module(local("Conclusions")),
    )
    args.update(kwargs)
    return Report(**args)


class ContractModelTests(unittest.TestCase):
    def test_arbitrary_languages_not_enum(self):
        self.assertEqual(validate_language_tag("pt-BR"), "pt-BR")
        self.assertEqual(validate_language_tag("zh-Hant-TW"), "zh-Hant-TW")
        self.assertEqual(validate_language_tag("en"), "en")
        with self.assertRaises(ValueError):
            validate_language_tag("../../secret")

    def test_translation_updates_mark_existing_translations_stale(self):
        text = LocalizedText("it", "Controllato")
        text.set_translation("en", "Inspected")
        text.set_translation("fr", "Inspecté")
        text.update_original("Controllato di nuovo")
        self.assertEqual(text.stale_languages, {"en", "fr"})
        text.set_translation("en", "Inspected again")
        self.assertEqual(text.stale_languages, {"fr"})
        self.assertEqual(text.original, "Controllato di nuovo")

    def test_duplicate_languages_rejected(self):
        with self.assertRaises(ValueError):
            make_report(output_languages=["en", "EN"])
        # Writing language need not be one of the selected output languages.
        report = make_report(primary_language="it", output_languages=["en", "de"])
        self.assertEqual(report.ordered_sections()[-1], report.conclusion)
        with self.assertRaises(ValueError):
            LocalizedText("en", "text", {"EN": "should not overwrite"})

    def test_date_validation_and_customer_required(self):
        with self.assertRaises(ValueError):
            make_report(start_date=date(2026, 5, 23))
        with self.assertRaises(ValueError):
            make_report(customer_id=" ")

    def test_flexible_nested_blocks_and_photos_stay_in_parent(self):
        photo = PhotoBlock("asset-1", local("Bearing closeup"))
        child = Module(local("Bearings"), blocks=[
            ParagraphBlock(local("Initial inspection")),
            photo,
            ParagraphBlock(local("After adjustment")),
            TableBlock([[local("Condition"), local("Acceptable")]]),
        ])
        parent = Module(local("Spiral inspection"), blocks=[
            ParagraphBlock(local("Spiral opened")),
            NestedModuleBlock(child),
            ParagraphBlock(local("Work complete")),
        ])
        r = make_report(modules=[parent])
        self.assertIs(r.modules[0].blocks[1].module.blocks[1], photo)
        r.modules.insert(0, Module(local("Pre-check")))
        self.assertIs(r.modules[1].blocks[1].module.blocks[1], photo)

    def test_conclusion_always_last(self):
        r = make_report(modules=[Module(local("First")), Module(local("Second"))])
        self.assertIs(r.ordered_sections()[-1], r.conclusion)
        r.modules.reverse()
        self.assertIs(r.ordered_sections()[-1], r.conclusion)
        r.modules.append(r.conclusion)
        with self.assertRaises(ValueError):
            r.ordered_sections()


if __name__ == "__main__":
    unittest.main()
