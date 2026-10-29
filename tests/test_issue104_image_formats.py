"""Issue #104: Pillow parser allowlists and secure-format compatibility gates.

Synthetic, local-only fixtures; never use customer files or external network.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import importlib.metadata
import struct
import tomllib
import unittest
import zlib

from PIL import Image, UnidentifiedImageError

from reportmaker.export import (
    EXPORT_IMAGE_FORMATS, ExportError, _image_bytes, _logo_dimensions,
    _photo_dimensions, export_project,
)
from reportmaker.media_import import (
    MAX_ICC_BYTES, PictureImportError, _convert_picture_data, convert_picture,
)
from reportmaker.project_io import _image_signature, load_project, save_project
from test_m4_export import synthetic_project


def encoded(format_name: str) -> bytes:
    data = BytesIO()
    Image.new("RGB", (17, 11), (14, 96, 151)).save(data, format=format_name)
    return data.getvalue()


def huge_png_header() -> bytes:
    """Replace only dimensions in an ordinary 1x1 PNG; never allocate huge pixels."""
    raw = encoded("PNG")
    chunk = struct.pack(">II", 100_000, 100_000) + raw[24:29]
    checksum = zlib.crc32(b"IHDR" + chunk) & 0xFFFFFFFF
    return raw[:16] + chunk + struct.pack(">I", checksum) + raw[33:]


class Issue104ImageSecurityTests(unittest.TestCase):
    def assert_formats_at_open(self, expected: tuple[str, ...], operation):
        """Spy on the *pre-decoding* formats= parameter, not post-open checks."""
        real_open = Image.open
        calls = []

        def guarded_open(fp, *args, **kwargs):
            self.assertIn("formats", kwargs)
            self.assertEqual(tuple(kwargs["formats"]), expected)
            calls.append(tuple(kwargs["formats"]))
            return real_open(fp, *args, **kwargs)

        with patch.object(Image, "open", side_effect=guarded_open):
            result = operation()
        self.assertTrue(calls, "image must pass a parser allowlist before opening")
        return result

    def test_declared_pillow_version_disallows_vulnerable_major(self):
        package = Path(__file__).resolve().parents[1] / "pyproject.toml"
        with package.open("rb") as stream:
            dependencies = tomllib.load(stream)["project"]["dependencies"]
        self.assertIn("Pillow>=13.0.0,<14", dependencies)
        self.assertGreaterEqual(int(importlib.metadata.version("Pillow").split(".")[0]), 13)

    def test_project_media_signature_uses_restricted_three_format_parsers(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            with self.subTest(fmt=fmt):
                signature = self.assert_formats_at_open(
                    ("JPEG", "PNG", "WEBP"), lambda: _image_signature(encoded(fmt)))
                self.assertEqual(signature["format"], fmt)
                self.assertEqual((signature["width"], signature["height"]), (17, 11))
        for fmt in ("BMP", "GIF", "TIFF"):
            with self.subTest(disallowed=fmt):
                with self.assertRaises(ValueError):
                    self.assert_formats_at_open(
                        ("JPEG", "PNG", "WEBP"), lambda: _image_signature(encoded(fmt)))

    def test_media_import_accepts_supported_formats_and_rejects_others(self):
        for fmt in ("JPEG", "PNG", "BMP", "WEBP"):
            with self.subTest(fmt=fmt):
                photo = self.assert_formats_at_open(
                    ("JPEG", "PNG", "BMP", "WEBP", "HEIF"),
                    lambda: _convert_picture_data(
                        encoded(fmt), preset="balanced", output_format="png"))
                self.assertEqual(photo.format, "png")
                self.assertTrue(photo.data.startswith(bytes.fromhex("89504e470d0a1a0a")))
        for fmt in ("GIF", "TIFF"):
            with self.subTest(disallowed=fmt):
                with self.assertRaises((PictureImportError, UnidentifiedImageError)):
                    self.assert_formats_at_open(
                        ("JPEG", "PNG", "BMP", "WEBP", "HEIF"),
                        lambda: _convert_picture_data(
                            encoded(fmt), preset="balanced", output_format="png"))

    def test_export_accepts_legacy_safe_rasters_and_rejects_other_parsers(self):
        self.assertEqual(tuple(EXPORT_IMAGE_FORMATS),
                         ("JPEG", "PNG", "WEBP", "BMP", "GIF", "TIFF"))
        for fmt in EXPORT_IMAGE_FORMATS:
            with self.subTest(fmt=fmt):
                output = self.assert_formats_at_open(
                    EXPORT_IMAGE_FORMATS, lambda: _image_bytes(encoded(fmt)))
                self.assertTrue(output)
                self.assert_formats_at_open(
                    EXPORT_IMAGE_FORMATS, lambda: _photo_dimensions(output))
                self.assert_formats_at_open(
                    EXPORT_IMAGE_FORMATS, lambda: _logo_dimensions(output))
        # Common Pillow parsers must NOT run simply because Pillow recognizes them.
        for fmt in ("PPM",):
            with self.subTest(disallowed=fmt):
                with self.assertRaises(ExportError):
                    self.assert_formats_at_open(
                        EXPORT_IMAGE_FORMATS, lambda: _image_bytes(encoded(fmt)))

    def test_malformed_oversize_and_metadata_paths_fail_closed(self):
        for raw in (b"garbage", encoded("PNG")[:12], huge_png_header()):
            with self.subTest(length=len(raw)):
                with self.assertRaises((ValueError, UnidentifiedImageError,
                                        PictureImportError, Image.DecompressionBombError)):
                    _image_signature(raw)
                with self.assertRaises((ExportError, Image.DecompressionBombError)):
                    _image_bytes(raw)
                with self.assertRaises((PictureImportError, UnidentifiedImageError,
                                        Image.DecompressionBombError)):
                    _convert_picture_data(raw, preset="balanced",
                                          output_format="png")

    def test_oversized_icc_is_rejected_before_transform(self):
        original_open = Image.open

        def oversized_icc(fp, *args, **kwargs):
            image = original_open(fp, *args, **kwargs)
            image.info["icc_profile"] = b"X" * (MAX_ICC_BYTES + 1)
            return image

        with patch.object(Image, "open", side_effect=oversized_icc):
            with self.assertRaisesRegex(PictureImportError, "color profile"):
                _convert_picture_data(encoded("PNG"), preset="balanced",
                                      output_format="png")

    def test_heif_plugin_can_decode_with_pillow_13_when_available(self):
        try:
            import pillow_heif
        except ImportError:
            self.skipTest("optional pillow-heif desktop extra is not installed")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.heic"
            try:
                pillow_heif.from_pillow(Image.new("RGB", (17, 11), "green")).save(path)
            except (OSError, RuntimeError) as exc:
                self.skipTest(f"HEIF encoding unavailable on this platform: {exc}")
            before = path.read_bytes()
            photo = self.assert_formats_at_open(
                ("JPEG", "PNG", "BMP", "WEBP", "HEIF"),
                lambda: convert_picture(path, preset="balanced", output_format="png"))
            self.assertEqual(photo.format, "png")
            self.assertEqual(photo.original_width, 17)
            self.assertEqual(photo.original_height, 11)
            self.assertEqual(path.read_bytes(), before)

    def test_roundtrip_and_word_pdf_export_remain_unchanged(self):
        project = synthetic_project()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic.rmproj"
            save_project(project, source)
            old_bytes = source.read_bytes()
            reopened = load_project(source)
            self.assertEqual(source.read_bytes(), old_bytes)
            self.assertEqual(reopened.assets, project.assets)
            for kind in ("docx", "pdf"):
                path = root / ("synthetic." + kind)
                export_project(reopened, path, format=kind)
                self.assertGreater(path.stat().st_size, 500)
            self.assertEqual(source.read_bytes(), old_bytes)


if __name__ == "__main__":
    unittest.main()
