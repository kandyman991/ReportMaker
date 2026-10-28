"""M1.2 regression gates for pure session, typed transactions and v4 storage.

Only synthetic customers, text and temp files are used. No Qt, browser,
network or user document directory is accessed.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from reportmaker.engine import module_outline
from reportmaker.model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, Report, TableBlock,
)
from reportmaker.project_io import ReportProject, load_project, save_project
from reportmaker.reference import manual_snapshot
from reportmaker.rich_text import TextRun
from reportmaker.v2.adapters.persistence import ProjectPersistence
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.projections import NodeAddress, find_node, project_branch
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError


def sample() -> ReportProject:
    language = "it"
    text = LocalizedText(language, "Testo iniziale")
    text.set_translation("de", "Anfang")
    child = Module(LocalizedText(language, "Sottomodulo"), [ParagraphBlock(text)])
    parent = Module(LocalizedText(language, "Modulo"), [
        HeadingBlock(LocalizedText(language, "Prima")),
        NestedModuleBlock(child),
        TableBlock([[LocalizedText(language, "Cella")]]),
        PageBreakBlock(),
    ])
    report = Report(
        customer_id=None, customer_snapshot=manual_snapshot("Synthetic M1.2 customer"),
        start_date=date(2026, 10, 27), end_date=date(2026, 10, 28),
        primary_language=language, output_languages=[language, "de", "ja-JP"],
        title=LocalizedText(language, "Report sintetico"),
        technicians=["Synthetic technician"], ticket="SYN-M12",
        intervention_types=["ordinary_maintenance", "supervision"],
        modules=[parent],
        conclusion=Module(LocalizedText(language, "Conclusioni"),
                          [ParagraphBlock(LocalizedText(language, "Finale"))]),
    )
    return ReportProject(report)


def intent(session, kind, target=None, **args):
    return CommandIntent(kind, target, args, session.revision, session.generation)


def module_address(report, module_id):
    return NodeAddress(report.id, module_id)


def paragraph_address(report, module_id, block_id):
    return NodeAddress(report.id, module_id, block_id, "text")


class SessionGatewayTests(unittest.TestCase):
    def setUp(self):
        self.s = ReportSession(sample())
        self.g = CommandGateway(self.s)

    def test_mixed_order_and_outline_remain_canonical(self):
        before = self.s.report_snapshot()
        parent = before.modules[0]
        child = parent.blocks[1].module
        changes = []
        self.s.subscribe(changes.append)
        change = self.g.execute(intent(self.s, "add_paragraph",
                                       module_address(before, parent.id),
                                       text="Prima del sotto", index=1))
        self.assertTrue(change.structure_changed)
        self.assertEqual(change.revision, 1)
        created = next(iter(change.changed_ids))
        after = self.s.report_snapshot()
        self.assertEqual(after.modules[0].blocks[1].id, created)
        self.assertEqual(after.modules[0].blocks[2].module.id, child.id)
        rows = project_branch(after, revision=self.s.revision)
        self.assertEqual([r.kind for r in rows],
                         ["root", "module", "heading", "paragraph", "module",
                          "paragraph", "table", "page-break", "conclusion", "paragraph"])
        self.assertEqual([r.mixed_sibling_index for r in rows[2:8]],
                         [0, 1, 2, 0, 3, 4])
        self.assertEqual(rows[4].wrapper_id, parent.blocks[1].id)
        self.assertEqual(rows[-2].stable_id, after.conclusion.id)
        self.assertEqual([e.module_id for e in module_outline(after) if not e.is_conclusion],
                         [parent.id, child.id])
        self.assertEqual(changes, [change])
        self.assertEqual(rows[4].source_revision, self.s.revision)

    def test_add_nested_and_top_level_respect_ids_and_conclusions(self):
        report = self.s.report_snapshot()
        result = self.g.execute(intent(self.s, "add_module", title="Nuovo", index=0))
        new_id = next(iter(result.changed_ids))
        other = self.g.execute(intent(self.s, "add_nested_module",
                                      module_address(report, new_id),
                                      title="Figlio", index=0))
        child_id = next(iter(other.changed_ids))
        after = self.s.report_snapshot()
        self.assertEqual(after.modules[0].id, new_id)
        self.assertEqual(after.modules[0].blocks[0].module.id, child_id)
        self.assertEqual(after.ordered_sections()[-1].id, report.conclusion.id)
        with self.assertRaises(ValueError):
            self.g.execute(intent(self.s, "add_nested_module",
                                  module_address(report, report.conclusion.id),
                                  title="Forbidden"))
        self.assertEqual(self.s.revision, 2)
        self.assertTrue(self.s.dirty)

    def test_translations_and_unicode_undo_redo(self):
        report = self.s.report_snapshot()
        child = report.modules[0].blocks[1].module
        paragraph = child.blocks[0]
        address = paragraph_address(report, child.id, paragraph.id)
        new_value = "Riparato 🛠️ 東京"
        self.g.execute(intent(self.s, "set_paragraph", address, text=new_value))
        modified = find_node(self.s.report_snapshot(), address)
        self.assertEqual(modified.text.original, new_value)
        self.assertEqual(modified.text.translations["de"], "Anfang")
        self.assertEqual(modified.text.stale_languages, {"de"})
        self.assertIsNotNone(self.g.undo(self.s.generation))
        reverted = find_node(self.s.report_snapshot(), address)
        self.assertEqual(reverted.text.original, "Testo iniziale")
        self.assertEqual(reverted.text.stale_languages, set())
        self.assertIsNotNone(self.g.redo(self.s.generation))
        self.assertEqual(find_node(self.s.report_snapshot(), address).text.original, new_value)
        self.assertEqual(self.s.revision, 3)

    def test_invalid_stale_actions_keep_history_and_data(self):
        original = self.s.report_snapshot()
        address = module_address(original, original.modules[0].id)
        with self.assertRaises(StaleIntentError):
            self.g.execute(CommandIntent("rename_module", address, {"title": "wrong"},
                                         50, self.s.generation))
        with self.assertRaises(StaleIntentError):
            self.g.execute(CommandIntent("rename_module", address, {"title": "wrong"},
                                         0, "obsolete-generation"))
        for kind, args in (
            ("rename_module", {"title": "changed", "extra": 1}),
            ("add_paragraph", {"text": "bad", "index": True}),
            ("add_paragraph", {"text": "bad", "index": 999}),
        ):
            with self.subTest(kind=kind, args=args), self.assertRaises(ValueError):
                self.g.execute(intent(self.s, kind, address, **args))
        with self.assertRaises(LookupError):
            self.g.execute(intent(self.s, "rename_module",
                                  module_address(original, "missing-id"), title="X"))
        with self.assertRaises(ValueError):
            self.g.execute(intent(self.s, "set_paragraph", address, text="bad"))
        self.assertEqual(self.s.report_snapshot(), original)
        self.assertEqual(self.s.revision, 0)
        self.assertIsNone(self.g.undo(self.s.generation))
        self.assertIsNone(self.g.redo(self.s.generation))

    def test_existing_rich_ranges_are_never_silently_deleted(self):
        report = self.s.report_snapshot()
        paragraph = report.modules[0].blocks[1].module.blocks[0]
        paragraph.rich.runs = [TextRun(0, len(paragraph.text.original), bold=True)]
        self.s.replace_project(ReportProject(report))
        p = self.s.report_snapshot().modules[0].blocks[1].module.blocks[0]
        addr = paragraph_address(report, report.modules[0].blocks[1].module.id, p.id)
        with self.assertRaises(ValueError):
            self.g.execute(intent(self.s, "set_paragraph", addr, text="A"))
        self.assertEqual(self.s.revision, 0)
        self.assertEqual(find_node(self.s.report_snapshot(), addr).rich.runs,
                         p.rich.runs)

    def test_snapshot_and_asset_views_cannot_mutate_session(self):
        copied = self.s.report_snapshot()
        copied.modules[0].title.update_original("External edit")
        copied.modules.clear()
        another = self.s.report_snapshot()
        self.assertEqual(another.modules[0].title.original, "Modulo")
        with self.assertRaises(TypeError):
            self.s.assets["new"] = b"bytes"
        with self.assertRaises(TypeError):
            self.s.media_library["new"] = "name"
        branch = project_branch(another, expanded=frozenset())
        self.assertEqual([row.kind for row in branch],
                         ["root", "module", "conclusion"])
        self.assertEqual(find_node(another, module_address(another, another.conclusion.id)).id,
                         another.conclusion.id)

    def test_generation_change_invalidates_late_callbacks(self):
        old = self.s.report_snapshot()
        old_token = self.s.generation
        self.s.replace_project(sample())
        self.assertNotEqual(old_token, self.s.generation)
        with self.assertRaises(StaleIntentError):
            self.g.execute(CommandIntent("rename_module",
                                         module_address(old, old.modules[0].id),
                                         {"title": "Late"}, 0, old_token))
        with self.assertRaises(StaleIntentError):
            self.g.undo(old_token)
        self.assertEqual(self.s.revision, 0)

    def test_pure_gateway_does_not_import_legacy_ui_or_qt(self):
        code = ("import reportmaker.v2.session, reportmaker.v2.commands, "
                "reportmaker.v2.projections, reportmaker.v2.adapters.persistence;"
                "import sys;"
                "assert 'reportmaker.ui' not in sys.modules;"
                "assert 'reportmaker.visual_editor' not in sys.modules;"
                "assert 'PySide6' not in sys.modules")
        result = subprocess.run([sys.executable, "-c", code],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.a = self.directory / "a.rmproj"
        self.b = self.directory / "b.rmproj"
        self.s = ReportSession(sample())
        self.g = CommandGateway(self.s)
        self.p = ProjectPersistence()

    def test_first_save_then_open_and_save_as_preserves_fields_and_ids(self):
        before = self.s.report_snapshot()
        self.g.execute(intent(self.s, "rename_module",
                              module_address(before, before.modules[0].id),
                              title="Renamed"))
        self.assertTrue(self.s.dirty)
        self.assertEqual(self.p.save(self.s, self.a), self.a)
        self.assertFalse(self.s.dirty)
        self.assertEqual(self.s.loaded_version, 4)
        self.assertEqual(self.s.path, self.a)
        self.p.save_as(self.s, self.b)
        self.assertEqual(self.s.path, self.b)
        self.assertTrue(self.a.exists())
        self.assertEqual(load_project(self.a).report.modules[0].id,
                         load_project(self.b).report.modules[0].id)
        opened = self.p.open(self.b)
        replacement = ReportSession(opened)
        self.assertEqual(replacement.report_snapshot(), self.s.report_snapshot())
        self.assertEqual(replacement.report_snapshot().ticket, "SYN-M12")
        self.assertEqual(replacement.report_snapshot().intervention_types,
                         ["ordinary_maintenance", "supervision"])

    def test_first_save_existing_and_failed_save_as_leave_active_identity(self):
        self.a.write_bytes(b"another file")
        before = self.a.read_bytes()
        with self.assertRaises(FileExistsError):
            self.p.save(self.s, self.a)
        self.assertIsNone(self.s.path)
        self.assertEqual(self.a.read_bytes(), before)
        self.p.save(self.s, self.b)
        self.assertEqual(self.s.path, self.b)
        with self.assertRaises(FileExistsError):
            self.p.save_as(self.s, self.a)
        self.assertEqual(self.s.path, self.b)
        self.assertEqual(self.a.read_bytes(), before)
        with self.assertRaises(ValueError):
            self.p.save(self.s, self.a)
        with self.assertRaises(ValueError):
            self.p.save_as(self.s, self.b)
        self.assertEqual(self.s.path, self.b)

    def test_undo_to_saved_content_clears_dirty_without_reusing_revision(self):
        self.p.save(self.s, self.a)
        report = self.s.report_snapshot()
        address = module_address(report, report.modules[0].id)
        old_generation = self.s.generation
        self.g.execute(intent(self.s, "rename_module", address, title="Temporarily edited"))
        self.assertTrue(self.s.dirty)
        self.assertIsNotNone(self.g.undo(old_generation))
        self.assertFalse(self.s.dirty)
        self.assertEqual(self.s.revision, 2)
        self.assertIsNotNone(self.g.redo(old_generation))
        self.assertTrue(self.s.dirty)
        self.assertEqual(self.s.revision, 3)

    def test_pending_drafts_block_saves_open_and_undo(self):
        self.p.save(self.s, self.a)
        before = self.a.read_bytes()
        report = self.s.report_snapshot()
        self.g.execute(intent(self.s, "rename_module",
                              module_address(report, report.modules[0].id),
                              title="Uncommitted-next"))
        dirty_revision = self.s.revision
        self.s.set_draft_guard(lambda: False)
        with self.assertRaises(PendingDraftError):
            self.p.save(self.s)
        with self.assertRaises(PendingDraftError):
            self.p.open_into(self.s, self.a)
        with self.assertRaises(PendingDraftError):
            self.g.undo(self.s.generation)
        self.assertEqual(self.s.revision, dirty_revision)
        self.assertTrue(self.s.dirty)
        self.assertEqual(self.a.read_bytes(), before)
        self.s.set_draft_guard(lambda: True)
        self.assertEqual(self.p.save(self.s), self.a)
        self.assertFalse(self.s.dirty)

    def test_invalid_open_never_changes_session_or_saved_data(self):
        self.p.save(self.s, self.a)
        old_generation = self.s.generation
        original = self.s.report_snapshot()
        self.b.write_bytes(b"not an rmproj")
        with self.assertRaises(ValueError):
            self.p.open_into(self.s, self.b)
        self.assertEqual(self.s.generation, old_generation)
        self.assertEqual(self.s.report_snapshot(), original)
        self.assertEqual(self.s.path, self.a)
        self.assertEqual(load_project(self.a).report, original)

    def test_legacy_v1_v2_v3_require_new_path_and_preserve_original(self):
        # Native v4 data with no photos: remove fields that predate schema v4.
        # These are valid synthetic v1-v3 archives, not private customer files.
        self.p.save(self.s, self.a)
        with ZipFile(self.a) as z:
            template = json.loads(z.read("manifest.json"))
        for version in (1, 2, 3):
            with self.subTest(version=version):
                legacy = deepcopy(template)
                legacy["version"] = version
                if version == 1:
                    legacy.pop("media_library")
                def remove_rich(module):
                    for block in module["blocks"]:
                        if block["kind"] in ("paragraph", "heading"):
                            block.pop("rich", None)
                        if block["kind"] == "module":
                            remove_rich(block["module"])
                for module in legacy["report"]["modules"] + [legacy["report"]["conclusion"]]:
                    remove_rich(module)
                source = self.directory / f"legacy{version}.rmproj"
                target = self.directory / f"upgrade{version}.rmproj"
                with ZipFile(source, "w", ZIP_DEFLATED) as z:
                    z.writestr("manifest.json", json.dumps(legacy))
                unchanged = source.read_bytes()
                opened = self.p.open(source)
                self.assertEqual(opened.loaded_version, version)
                loaded_session = ReportSession(opened)
                with self.assertRaises(ValueError):
                    self.p.save(loaded_session)
                with self.assertRaises(ValueError):
                    self.p.save_as(loaded_session, source, overwrite=True)
                self.p.save_as(loaded_session, target)
                self.assertEqual(loaded_session.loaded_version, 4)
                self.assertEqual(loaded_session.path, target)
                self.assertEqual(source.read_bytes(), unchanged)
                self.assertEqual(load_project(target).report.id,
                                 opened.report.id)
                self.assertEqual(load_project(target).report.modules[0].blocks[1].module.id,
                                 opened.report.modules[0].blocks[1].module.id)


if __name__ == "__main__":
    unittest.main()
