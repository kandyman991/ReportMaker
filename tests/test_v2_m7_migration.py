"""M7.2: synthetic v1–v5 migration, non-destructive Save As, and corrupt archive gates."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import warnings
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZipFile

from PIL import Image

from reportmaker.model import PhotoMark, PhotoVisual
from reportmaker.project_io import ReportProject, VERSION, load_project, save_project
from reportmaker.rich_text import ParagraphStyle, RichFormatting, TextRun
from reportmaker.v2.metadata_locale import MetadataLocale
from reportmaker.v2.session import ReportSession
from test_m2_project import example


def fresh_project() -> ReportProject:
    project = example()
    project.report.modules[0].title.update_original("Nuova linea sintetica")
    paragraph = project.report.modules[0].blocks[1].module.blocks[0]
    paragraph.rich = RichFormatting(
        runs=[TextRun(0, 4, bold=True, color="#224466")],
        paragraphs=[ParagraphStyle(0, align="justify", line_height=1.5)],
    )
    photo = project.report.modules[0].blocks[1].module.blocks[1]
    photo.visual = PhotoVisual(rotation=90, marks=[
        PhotoMark(kind="rectangle", x=0.1, y=0.2, x2=0.8, y2=0.9)])
    image = BytesIO()
    Image.new("RGB", (4, 5), (31, 47, 73)).save(image, format="PNG")
    project.assets["gallery-only"] = image.getvalue()
    project.media_library["gallery-only"] = "Synthetic unused gallery photo"
    approved = MetadataLocale(project.report).approve("field.customer", "de", "Kunde")
    project.report.localization_ledger = {
        approved.key: {approved.language: {
            "text": approved.text, "source_sha256": approved.source_sha256}}}
    return project


def downgrade_module(module, version):
    for block in module["blocks"]:
        if block["kind"] in ("paragraph", "heading") and version < 4:
            block.pop("rich", None)
        elif block["kind"] == "photo" and version < 3:
            block.pop("visual", None)
        elif block["kind"] == "module":
            downgrade_module(block["module"], version)


def write_archive(path, manifest, assets):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for key, data in assets.items():
            archive.writestr(key, data)


def fixture(folder, version):
    if not 1 <= version <= VERSION:
        raise ValueError("Unsupported fixture version")
    native = folder / ("seed-%s.rmproj" % version)
    save_project(fresh_project(), native)
    with ZipFile(native) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assets = {i.filename: archive.read(i.filename)
                  for i in archive.infolist() if i.filename != "manifest.json"}
    manifest["version"] = version
    if version < 5:
        manifest["report"].pop("localization_ledger")
    if version == 1:
        manifest.pop("media_library")
        manifest["assets"] = [x for x in manifest["assets"]
                              if x["id"] != "gallery-only"]
        assets.pop("assets/gallery-only")
    for module in manifest["report"]["modules"]:
        downgrade_module(module, version)
    downgrade_module(manifest["report"]["conclusion"], version)
    source = folder / ("source-v%s.rmproj" % version)
    write_archive(source, manifest, assets)
    return source


class M72MigrationMatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_five_versions_preserve_original_and_upgrade_by_save_as(self):
        self.assertEqual(VERSION, 5)
        for version in range(1, 6):
            with self.subTest(version=version):
                source = fixture(self.folder, version)
                original = source.read_bytes()
                project = load_project(source)
                self.assertEqual(project.loaded_version, version)
                report = project.report
                self.assertEqual(report.customer_snapshot.customer_name,
                                 "Synthetic Example")
                self.assertIsNone(report.customer_id)
                self.assertEqual(report.ticket, "SYN-777")
                self.assertEqual(report.intervention_types,
                                 ["supervision", "other"])
                self.assertEqual(report.output_languages, ["de", "zh-Hant-TW"])
                self.assertEqual(report.modules[0].title.stale_languages, {"de"})
                self.assertEqual(report.modules[0].title.translations["de"], "Linie")
                self.assertEqual(report.ordered_sections()[-1].id,
                                 report.conclusion.id)
                child = report.modules[0].blocks[1].module
                paragraph = child.blocks[0]
                self.assertEqual(len(paragraph.rich.runs), 1 if version >= 4 else 0)
                self.assertEqual(len(paragraph.rich.paragraphs), 1 if version >= 4 else 0)
                if version >= 4:
                    self.assertTrue(paragraph.rich.runs[0].bold)
                    self.assertEqual(paragraph.rich.runs[0].color, "#224466")
                    self.assertEqual(paragraph.rich.paragraphs[0].align, "justify")
                photo = child.blocks[1]
                self.assertEqual(photo.asset_id, "photo-1")
                self.assertEqual(photo.caption.translations["de"], "Vorher")
                self.assertEqual(photo.visual.rotation, 90 if version >= 3 else 0)
                self.assertEqual(len(photo.visual.marks), 1 if version >= 3 else 0)
                self.assertEqual(
                    set(project.media_library),
                    {"gallery-only"} if version >= 2 else set())
                self.assertEqual(
                    set(project.assets),
                    {"photo-1", "gallery-only"} if version >= 2 else {"photo-1"})
                self.assertEqual(bool(report.localization_ledger), version == 5)
                if version == 5:
                    approval = report.localization_ledger["field.customer"]["de"]
                    self.assertEqual(approval["text"], "Kunde")
                    self.assertRegex(approval["source_sha256"], r"^[0-9a-f]{64}$")
                if version < 5:
                    with self.assertRaisesRegex(ValueError, "Save As"):
                        save_project(project, source)
                upgraded = self.folder / ("upgraded-%s.rmproj" % version)
                save_project(project, upgraded)
                reopened = load_project(upgraded)
                self.assertEqual(reopened.loaded_version, 5)
                self.assertEqual(reopened.report, project.report)
                self.assertEqual(reopened.assets, project.assets)
                self.assertEqual(reopened.media_library, project.media_library)
                self.assertEqual(reopened.report.id, report.id)
                self.assertEqual(reopened.report.modules[0].id,
                                 report.modules[0].id)
                self.assertEqual(reopened.report.modules[0].blocks[1].module.id,
                                 child.id)
                self.assertEqual(sha256(source.read_bytes()).hexdigest(),
                                 sha256(original).hexdigest())
                self.assertEqual(source.read_bytes(), original)
                with ZipFile(upgraded) as archive:
                    self.assertTrue(set(archive.namelist()) <= {
                        "manifest.json", "assets/photo-1", "assets/gallery-only"})
                    self.assertNotIn("browser", " ".join(archive.namelist()).lower())
                    self.assertEqual(json.loads(archive.read("manifest.json"))["version"], 5)

    def test_bad_schemas_do_not_replace_active_report(self):
        good = fixture(self.folder, 5)
        session = ReportSession(load_project(good))
        previous = session.project_snapshot()
        generation, revision = session.generation, session.revision
        with ZipFile(good) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assets = {i.filename: archive.read(i.filename)
                      for i in archive.infolist() if i.filename != "manifest.json"}
        cases = {
            "future-version": lambda m: m.__setitem__("version", 999),
            "missing-ledger": lambda m: m["report"].pop("localization_ledger"),
            "extra-snapshot": lambda m: m["report"]["customer_snapshot"].update(
                {"unexpected": "untrusted"}),
            "missing-asset": lambda m: m["assets"].__setitem__(
                0, {**m["assets"][0], "id": "ghost"}),
            "wrong-media-dimensions": lambda m: m["media_library"][0].__setitem__(
                "width", 999),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                path = self.folder / (name + ".rmproj")
                candidate = deepcopy(manifest)
                mutate(candidate)
                write_archive(path, candidate, assets)
                unchanged = path.read_bytes()
                with self.assertRaises(ValueError):
                    session.replace_project(load_project(path),
                                            discard_unsaved=True)
                self.assertEqual(path.read_bytes(), unchanged)
                self.assertEqual(session.generation, generation)
                self.assertEqual(session.revision, revision)
                self.assertEqual(session.project_snapshot(), previous)

    def test_reject_malformed_zip_and_preserve_source(self):
        valid = fixture(self.folder, 5)
        with ZipFile(valid) as archive:
            entries = [(item.filename, archive.read(item.filename))
                       for item in archive.infolist()]
        for label, name, payload, method in (
            ("duplicate-member", "assets/photo-1", b"duplicate", ZIP_DEFLATED),
            ("traversal-member", "../outside.txt", b"escape", ZIP_DEFLATED),
            ("unsupported-compression", "assets/injected", b"zip", ZIP_BZIP2),
        ):
            with self.subTest(case=label):
                source = self.folder / (label + ".rmproj")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
                        for entry, data in entries:
                            archive.writestr(entry, data)
                        archive.writestr(name, payload, compress_type=method)
                original = source.read_bytes()
                with self.assertRaises(ValueError):
                    load_project(source)
                self.assertEqual(source.read_bytes(), original)
                self.assertFalse((self.folder / "outside.txt").exists())

    def test_invalid_session_install_is_atomic(self):
        good = fixture(self.folder, 5)
        session = ReportSession(load_project(good))
        before = session.project_snapshot()
        generation, revision = session.generation, session.revision
        invalid = deepcopy(before)
        invalid.assets.pop("photo-1")
        with self.assertRaises(ValueError):
            session.replace_project(invalid, discard_unsaved=True)
        self.assertEqual(session.generation, generation)
        self.assertEqual(session.revision, revision)
        self.assertEqual(session.project_snapshot(), before)

    def test_invalid_cross_version_fields_fail_closed(self):
        for version in (1, 2):
            with self.subTest(version=version):
                source = fixture(self.folder, version)
                with ZipFile(source) as archive:
                    manifest = json.loads(archive.read("manifest.json"))
                    assets = {i.filename: archive.read(i.filename)
                              for i in archive.infolist()
                              if i.filename != "manifest.json"}
                if version == 1:
                    manifest["report"]["localization_ledger"] = {}
                else:
                    manifest["report"]["modules"][0]["blocks"][1]["module"][
                        "blocks"][1]["visual"] = {"untrusted": True}
                path = self.folder / ("illegal-v%s.rmproj" % version)
                write_archive(path, manifest, assets)
                with self.assertRaises(ValueError):
                    load_project(path)
                self.assertEqual(load_project(source).loaded_version, version)

    def test_failed_save_as_preserves_original_and_existing_destination(self):
        source = fixture(self.folder, 4)
        source_bytes = source.read_bytes()
        dest = self.folder / "existing-v5.rmproj"
        save_project(fresh_project(), dest)
        dest_bytes = dest.read_bytes()
        project = load_project(source)
        project.assets.pop("photo-1")
        with self.assertRaises(ValueError):
            save_project(project, dest)
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertEqual(dest.read_bytes(), dest_bytes)
        self.assertEqual(load_project(source).loaded_version, 4)

    def test_v1_fallback_executable_and_appid_are_distinct(self):
        root = Path(__file__).resolve().parents[1]
        old = (root / "packaging/windows/ReportMaker.iss").read_text(encoding="utf-8")
        new = (root / "packaging/windows/ReportMaker-V2-M7.iss").read_text(encoding="utf-8")
        self.assertIn("ReportMaker.exe", old)
        self.assertIn("ReportMakerV2.exe", new)
        self.assertNotEqual(
            next(x for x in old.splitlines() if x.startswith("AppId=")),
            next(x for x in new.splitlines() if x.startswith("AppId=")))


if __name__ == "__main__":
    unittest.main()
