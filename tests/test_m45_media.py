"""M4.5.1 synthetic picture-container/import regression gates."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image

from reportmaker.media_import import (
    PictureImportError, convert_picture, import_picture, import_pictures,
    remove_library_picture,
)
from reportmaker.model import LocalizedText, PhotoBlock
from reportmaker.project_io import ReportProject, load_project, save_project
from test_m2_project import example


def sample(path: Path, *, alpha: bool = False, quality: int = 95):
    picture = Image.new("RGBA" if alpha else "RGB", (340, 240),
                        (20, 80, 170, 180) if alpha else (20, 80, 170))
    picture.save(path, format="PNG" if alpha else "JPEG", quality=quality)
    return path.read_bytes()


class M45MediaContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = example()
        self.dest = self.root / "test.rmproj"

    def test_import_creates_detached_optimized_copy_without_changing_original(self):
        source = self.root / "source.jpg"
        original = sample(source)
        identifier = import_picture(self.project, source)
        self.assertEqual(source.read_bytes(), original)
        self.assertIn(identifier, self.project.media_library)
        self.assertEqual(self.project.media_library[identifier], "source")
        self.assertTrue(self.project.assets[identifier].startswith(b"\xff\xd8"))
        self.assertNotIn(str(source).encode(), self.project.assets[identifier])
        with Image.open(BytesIO(self.project.assets[identifier])) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertEqual(im.size, (340, 240))
            self.assertFalse(im.getexif())
        save_project(self.project, self.dest)
        self.assertEqual(source.read_bytes(), original)
        # Move/remove originals: self-contained project reopens without them.
        source.unlink()
        restored = load_project(self.dest)
        self.assertEqual(restored.assets[identifier], self.project.assets[identifier])
        self.assertEqual(restored.media_library, {identifier: "source"})
        with ZipFile(self.dest) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            self.assertEqual(manifest["version"], 2)
            self.assertEqual(manifest["media_library"], [{"id": identifier, "name": "source"}])
            self.assertEqual(set(bundle.namelist()),
                {"manifest.json", "assets/photo-1", "assets/" + identifier})
            self.assertNotIn(str(source), bundle.read("manifest.json").decode())

    def test_declared_unused_asset_survives_but_hidden_undo_orphan_does_not(self):
        path = self.root / "input.jpg"
        sample(path)
        media_id = import_picture(self.project, path)
        self.project.assets["hidden-undo"] = b"not serialized"
        save_project(self.project, self.dest)
        loaded = load_project(self.dest)
        self.assertIn(media_id, loaded.assets)
        self.assertNotIn("hidden-undo", loaded.assets)
        self.assertEqual(set(loaded.media_library), {media_id})
        with ZipFile(self.dest) as bundle:
            self.assertNotIn("assets/hidden-undo", bundle.namelist())

    def test_same_image_can_be_placed_twice_and_explicit_removal_is_guarded(self):
        source = self.root / "reused.jpg"
        sample(source)
        key = import_picture(self.project, source)
        first = PhotoBlock(key, LocalizedText("it", "Prima"))
        second = PhotoBlock(key, LocalizedText("it", "Dopo"))
        self.project.report.modules[0].blocks.extend([first, second])
        save_project(self.project, self.dest)
        restored = load_project(self.dest)
        self.assertEqual(restored.report.modules[0].blocks[-1].asset_id, key)
        self.assertEqual(restored.report.modules[0].blocks[-2].asset_id, key)
        with ZipFile(self.dest) as archive:
            self.assertEqual(archive.namelist().count("assets/" + key), 1)
        with self.assertRaises(PictureImportError):
            remove_library_picture(restored, key)
        self.assertIn(key, restored.media_library)
        restored.report.modules[0].blocks = restored.report.modules[0].blocks[:-2]
        remove_library_picture(restored, key)
        self.assertNotIn(key, restored.assets)
        self.assertNotIn(key, restored.media_library)

    def test_batch_import_is_atomic_if_one_source_invalid(self):
        valid = self.root / "valid.jpg"
        invalid = self.root / "invalid.heic"
        original = sample(valid)
        invalid.write_bytes(b"not really HEIC")
        before = deepcopy(self.project)
        with self.assertRaises(PictureImportError):
            import_pictures(self.project, [valid, invalid])
        self.assertEqual(self.project, before)
        self.assertEqual(valid.read_bytes(), original)

    def test_alpha_preserved_and_jpeg_not_allowed_to_flatten_silently(self):
        original = self.root / "alpha.png"
        raw = sample(original, alpha=True)
        output = convert_picture(original)
        self.assertEqual(output.format, "png")
        with Image.open(BytesIO(output.data)) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((0, 0))[3], 180)
        with self.assertRaises(PictureImportError):
            convert_picture(original, output_format="jpeg")
        self.assertEqual(original.read_bytes(), raw)

    def test_oversized_or_malformed_images_do_not_clobber_project(self):
        bad = self.root / "bad.jpg"
        bad.write_bytes(b"broken image bytes")
        before = deepcopy(self.project)
        with self.assertRaises(PictureImportError):
            import_picture(self.project, bad)
        self.assertEqual(self.project, before)
        huge = self.root / "huge.png"
        huge.write_bytes(b"\x00" * (64 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(PictureImportError, "64 MiB"):
            import_picture(self.project, huge)
        self.assertEqual(self.project, before)

    def test_old_v1_archive_loads_and_migrates_without_mutating_original(self):
        save_project(self.project, self.dest)
        with ZipFile(self.dest) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assets = {name: archive.read(name) for name in archive.namelist()
                      if name.startswith("assets/")}
        manifest.pop("media_library")
        manifest["version"] = 1
        with ZipFile(self.dest, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            for name, data in assets.items():
                archive.writestr(name, data)
        original = self.dest.read_bytes()
        loaded = load_project(self.dest)
        self.assertEqual(loaded.media_library, {})
        self.assertEqual(loaded.assets, self.project.assets)
        self.assertEqual(self.dest.read_bytes(), original)
        newer = self.root / "migrated.rmproj"
        save_project(loaded, newer)
        self.assertEqual(json.loads(ZipFile(newer).read("manifest.json"))["version"], 2)

    def test_v2_rejects_undeclared_media_and_bad_library_entries(self):
        source = self.root / "source.jpg"
        sample(source)
        identifier = import_picture(self.project, source)
        save_project(self.project, self.dest)
        with ZipFile(self.dest) as archive:
            initial = json.loads(archive.read("manifest.json"))
            assets = {name: archive.read(name) for name in archive.namelist()
                      if name.startswith("assets/")}
        for edit in ("duplicate_member", "missing_member", "unlisted_member"):
            manifest = deepcopy(initial)
            if edit == "duplicate_member":
                manifest["media_library"].append(dict(manifest["media_library"][0]))
            elif edit == "missing_member":
                manifest["media_library"] = []
            else:
                manifest["media_library"][0]["id"] = "../escape"
            with self.subTest(edit=edit):
                with ZipFile(self.dest, "w", ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", json.dumps(manifest))
                    for name, blob in assets.items():
                        archive.writestr(name, blob)
                with self.assertRaises(ValueError):
                    load_project(self.dest)

    def test_synthetic_heic_decoder_when_available(self):
        try:
            from pillow_heif import from_pillow
        except ImportError:
            self.skipTest("HEIC decoder is not installed in this test environment")
        path = self.root / "synthetic.heic"
        from_pillow(Image.new("RGB", (64, 48), "blue")).save(str(path))
        before = path.read_bytes()
        output = convert_picture(path)
        self.assertEqual(output.format, "jpeg")
        self.assertEqual((output.width, output.height), (64, 48))
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
