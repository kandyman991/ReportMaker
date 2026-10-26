"""M2 acceptance tests. Entirely synthetic data, no private report materials."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
import json
import os
import unittest

from reportmaker.engine import ProjectEditor, module_outline, validate_report_tree
from reportmaker.model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, Report, TableBlock,
)
from reportmaker.project_io import ReportProject, load_project, save_project
from reportmaker.reference import manual_snapshot


def loc(source, translation=None):
    result = LocalizedText("it", source)
    if translation is not None:
        result.set_translation("de", translation)
    return result


def example():
    grandchild = Module(loc("Cuscinetti", "Lager"), [
        ParagraphBlock(loc("Ispezione", "Inspektion")),
        PhotoBlock("photo-1", loc("Prima", "Vorher")),
        TableBlock([[loc("Posizione"), loc("OK")]]),
    ])
    parent = Module(loc("Linea", "Linie"), [
        HeadingBlock(loc("Controllo"), 2),
        NestedModuleBlock(grandchild),
        PageBreakBlock(),
        ParagraphBlock(loc("Completato")),
    ])
    report = Report(
        customer_id=None, customer_snapshot=manual_snapshot(
            "Synthetic Example", site_name="Demo Factory", machine_serial="SAMPLE-123"),
        created_date=date(2026, 10, 26), title=loc("Intervento", "Einsatz"),
        start_date=date(2026, 10, 25), end_date=date(2026, 10, 26),
        primary_language="it", output_languages=["de", "zh-Hant-TW"],
        technicians=["Test Technician", "Example Colleague"],
        ticket="SYN-777", intervention_types=["supervision", "other"],
        other_intervention_detail="Fictitious custom work",
        modules=[parent], conclusion=Module(loc("Conclusioni", "Fazit"),
            [ParagraphBlock(loc("Verificato", "Geprüft"))]),
    )
    return ReportProject(report, {"photo-1": b"\x89PNG\r\n\x1a\nSYNTHETIC-FAKE-IMAGE"})


class M2ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.rmproj"

    def test_complete_local_project_roundtrip(self):
        project = example()
        path = save_project(project, self.path)
        self.assertTrue(path.exists())
        loaded = load_project(path)
        self.assertEqual(loaded.report.id, project.report.id)
        self.assertEqual(loaded.report.customer_snapshot.customer_name, "Synthetic Example")
        self.assertIsNone(loaded.report.customer_snapshot.customer_id)
        self.assertEqual(loaded.report.created_date, date(2026, 10, 26))
        self.assertEqual(loaded.report.intervention_types, ["supervision", "other"])
        self.assertEqual(loaded.report.other_intervention_detail, "Fictitious custom work")
        self.assertEqual(loaded.report.ticket, "SYN-777")
        self.assertEqual(loaded.report.technicians, ["Test Technician", "Example Colleague"])
        self.assertEqual(loaded.report.output_languages, ["de", "zh-Hant-TW"])
        self.assertEqual(loaded.assets, project.assets)
        self.assertEqual(loaded.report.modules[0].blocks[1].module.blocks[1].caption.translations["de"], "Vorher")
        self.assertIs(loaded.report.ordered_sections()[-1], loaded.report.conclusion)
        with ZipFile(path) as bundle:
            self.assertEqual(set(bundle.namelist()), {"manifest.json", "assets/photo-1"})
            self.assertNotIn("summary", json.loads(bundle.read("manifest.json"))["report"])

    def test_stale_translation_survives_save(self):
        project = example()
        text = project.report.modules[0].title
        text.update_original("Nuova linea")
        self.assertEqual(text.stale_languages, {"de"})
        save_project(project, self.path)
        self.assertEqual(load_project(self.path).report.modules[0].title.stale_languages, {"de"})

    def test_single_hierarchy_outline_and_reordering(self):
        e = ProjectEditor(example().report)
        a = Module(loc("A"))
        b = Module(loc("B"))
        e.add_module(a, index=0)
        e.add_module(b, parent_id=a.id)
        entries = module_outline(e.report)
        self.assertEqual([(x.number, x.title) for x in entries],
                         [("1", "A"), ("1.1", "B"), ("2", "Linea"), ("2.1", "Cuscinetti"), ("", "Conclusioni")])
        e.rename_module(b.id, "Renamed")
        self.assertEqual(module_outline(e.report)[1].title, "Renamed")
        e.move_module(b.id, index=0)
        self.assertEqual([(x.number, x.title) for x in module_outline(e.report)],
                         [("1", "Renamed"), ("2", "A"), ("3", "Linea"), ("3.1", "Cuscinetti"), ("", "Conclusioni")])
        self.assertEqual(len(e.report.modules), 3)
        self.assertIs(e.report.ordered_sections()[-1], e.report.conclusion)

    def test_move_parent_keeps_children_photo_table_and_translations(self):
        e = ProjectEditor(example().report)
        second = Module(loc("Second"))
        e.add_module(second, index=0)
        parent_id = e.report.modules[1].id
        e.move_module(parent_id, parent_id=second.id)
        nested = e.report.modules[0].blocks[0].module
        self.assertEqual(nested.title.translations["de"], "Linie")
        grandchild = nested.blocks[1].module
        self.assertEqual(grandchild.blocks[1].asset_id, "photo-1")
        self.assertIsInstance(grandchild.blocks[2], TableBlock)
        before = module_outline(e.report)
        with self.assertRaises(ValueError):
            e.move_module(second.id, parent_id=grandchild.id)
        self.assertEqual(module_outline(e.report), before)

    def test_duplication_fresh_ids_and_undo_redo(self):
        e = ProjectEditor(example().report)
        original = e.report.modules[0]
        duplicate_id = e.duplicate_module(original.id)
        self.assertEqual(len(e.report.modules), 2)
        self.assertNotEqual(duplicate_id, original.id)
        duplicated = e.report.modules[1]
        self.assertNotEqual(duplicated.blocks[1].module.id, original.blocks[1].module.id)
        self.assertEqual(duplicated.blocks[1].module.blocks[1].asset_id, "photo-1")
        validate_report_tree(e.report)
        self.assertTrue(e.undo())
        self.assertEqual(len(e.report.modules), 1)
        self.assertTrue(e.redo())
        self.assertEqual(len(e.report.modules), 2)
        e.remove_module(duplicate_id)
        self.assertFalse(e.can_redo)
        with self.assertRaises(ValueError):
            e.remove_module(e.report.conclusion.id)
        self.assertEqual(len(e.report.modules), 1)

    def test_block_actions_and_failed_change_are_atomic(self):
        e = ProjectEditor(example().report)
        target = e.report.modules[0].id
        new = ParagraphBlock(loc("Manual approved notes"))
        e.add_block(target, new, index=0)
        self.assertEqual(e.report.modules[0].blocks[0].id, new.id)
        e.move_block(target, new.id, e.report.conclusion.id)
        self.assertEqual(e.report.conclusion.blocks[-1].id, new.id)
        e.remove_block(e.report.conclusion.id, new.id)
        before = module_outline(e.report)
        with self.assertRaises(ValueError):
            e.add_module(Module(loc("Duplicate ID"), id=target))
        self.assertEqual(module_outline(e.report), before)

    def test_missing_asset_and_bad_ids_rejected_without_partial_write(self):
        project = example()
        project.assets.clear()
        with self.assertRaises(ValueError):
            save_project(project, self.path)
        self.assertFalse(self.path.exists())
        project = example()
        project.assets["../unsafe"] = b"bad"
        with self.assertRaises(ValueError):
            save_project(project, self.path)
        self.assertFalse(self.path.exists())

    def test_failed_resave_preserves_existing_contents(self):
        project = example()
        save_project(project, self.path)
        original = self.path.read_bytes()
        project.assets["photo-1"] = "not bytes"
        with self.assertRaises(ValueError):
            save_project(project, self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_future_schema_rejected_and_never_rewritten(self):
        save_project(example(), self.path)
        with ZipFile(self.path) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            image = bundle.read("assets/photo-1")
        manifest["version"] = 999
        with ZipFile(self.path, "w", ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest))
            bundle.writestr("assets/photo-1", image)
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            load_project(self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_corrupt_asset_or_unlisted_path_rejected(self):
        save_project(example(), self.path)
        with ZipFile(self.path) as bundle:
            manifest = bundle.read("manifest.json")
        for name, payload in (("assets/photo-1", b"tampered"), ("../escape.txt", b"bad")):
            with self.subTest(name=name):
                with ZipFile(self.path, "w", ZIP_DEFLATED) as bundle:
                    bundle.writestr("manifest.json", manifest)
                    bundle.writestr("assets/photo-1", b"\x89PNG\r\n\x1a\nSYNTHETIC-FAKE-IMAGE")
                    if name != "assets/photo-1":
                        bundle.writestr(name, payload)
                    else:
                        # Deliberately replace the expected asset with wrong bytes.
                        pass
                if name == "assets/photo-1":
                    with ZipFile(self.path, "w", ZIP_DEFLATED) as bundle:
                        bundle.writestr("manifest.json", manifest)
                        bundle.writestr(name, payload)
                with self.assertRaises(ValueError):
                    load_project(self.path)

    def test_invalid_archive_and_symlink_protection(self):
        self.path.write_bytes(b"not a project")
        with self.assertRaises(ValueError):
            load_project(self.path)
        if hasattr(os, "symlink"):
            link = Path(self.tmp.name) / "linked.rmproj"
            try:
                os.symlink(self.path, link)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(ValueError):
                save_project(example(), link)
            with self.assertRaises(ValueError):
                load_project(link)


    def test_conclusions_cannot_hide_intervention_submodules(self):
        project = example()
        editor = ProjectEditor(project.report)
        before = module_outline(editor.report)
        with self.assertRaises(ValueError):
            editor.add_module(Module(loc("Forbidden")), parent_id=editor.report.conclusion.id)
        self.assertEqual(module_outline(editor.report), before)
        forbidden = NestedModuleBlock(Module(loc("Hidden intervention")))
        with self.assertRaises(ValueError):
            editor.add_block(editor.report.conclusion.id, forbidden)
        self.assertEqual(module_outline(editor.report), before)

    def test_malformed_snapshot_and_duplicate_json_keys_rejected(self):
        save_project(example(), self.path)
        with ZipFile(self.path) as bundle:
            raw = bundle.read("manifest.json")
            photo = bundle.read("assets/photo-1")

        tampered = json.loads(raw)
        tampered["report"]["customer_snapshot"]["customer_city"] = ["not text"]
        with ZipFile(self.path, "w", ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", json.dumps(tampered))
            bundle.writestr("assets/photo-1", photo)
        with self.assertRaises(ValueError):
            load_project(self.path)

        # Duplicate field names are ambiguous and must fail closed.
        duplicated = b'{"format":"reportmaker.project",' + raw[1:]
        with ZipFile(self.path, "w", ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", duplicated)
            bundle.writestr("assets/photo-1", photo)
        with self.assertRaises(ValueError):
            load_project(self.path)

    def test_database_snapshot_remains_frozen_in_reopened_project(self):
        from reportmaker.storage import CustomerStore
        db_path = Path(self.tmp.name) / "customers.sqlite3"
        with CustomerStore(db_path) as store:
            customer_id = store.create_customer("Original Synthetic Co")
            snapshot = store.capture_snapshot(customer_id)
            project = example()
            project.report.customer_id = customer_id
            project.report.customer_snapshot = snapshot
            save_project(project, self.path)
            store.update("customers", customer_id, name="Renamed Master Record")
        reopened = load_project(self.path)
        self.assertEqual(reopened.report.customer_id, customer_id)
        self.assertEqual(reopened.report.customer_snapshot.customer_name, "Original Synthetic Co")



if __name__ == "__main__":
    unittest.main()
