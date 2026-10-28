"""M4.5 offline import of independent, bounded working pictures.

Never writes to a source filename and never stores its absolute path in a
ReportProject. No browser/network calls or user-company test fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from .project_io import (
    MAX_ASSET, MAX_ENTRIES, MAX_TOTAL_ASSETS, ReportProject, _assets_checked,
    _photo_ids,
)

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_DECODE_PIXELS = 60_000_000  # accept common 48 MP phone HEIC originals
MAX_ICC_BYTES = 1024 * 1024
MAX_IMPORT_BATCH = 64  # bound retained decoded comparison thumbnails
# maximum long edge, JPEG/WebP encoder quality
PRESETS = {"compact": (1600, 75), "balanced": (2500, 88),
           "high": (4000, 94)}
INPUT_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"}


class PictureImportError(ValueError):
    """Import failed without modifying either the original file or project."""


@dataclass(frozen=True)
class ImportedPicture:
    data: bytes
    format: str
    width: int
    height: int
    original_width: int
    original_height: int
    source_bytes: int
    source_preview: bytes = b""  # small, session-only; never saved in .rmproj


@dataclass(frozen=True)
class StagedPicture:
    name: str
    photo: ImportedPicture


def _prepare_heif(path: Path) -> None:
    if path.suffix.lower() not in {".heic", ".heif"}:
        return
    try:
        from pillow_heif import register_heif_opener
    except ImportError as exc:
        raise PictureImportError(
            "HEIC support is not installed; install the verified Windows HEIC decoder"
        ) from exc
    register_heif_opener()


def convert_picture(path: str | Path, *, preset: str = "balanced",
                    output_format: str = "auto") -> ImportedPicture:
    """Decode an external picture once, return detached optimized image bytes.

    output_format: auto, jpeg, png or webp. Auto chooses PNG for transparency
    and JPEG otherwise; lossy JPEG never silently flattens transparent pixels.
    """
    if preset not in PRESETS or output_format not in {"auto", "jpeg", "png", "webp"}:
        raise PictureImportError("Unsupported picture conversion options")
    source = Path(path)
    if source.suffix.lower() not in INPUT_SUFFIXES or source.is_symlink():
        raise PictureImportError("Unsupported image name or symlink")
    max_edge, quality = PRESETS[preset]
    try:
        _prepare_heif(source)
        with source.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            if size <= 0 or size > MAX_SOURCE_BYTES:
                raise PictureImportError("Source image exceeds the 64 MiB import limit")
            data = stream.read(MAX_SOURCE_BYTES + 1)
        if len(data) != size:
            raise PictureImportError("Source image changed during import")
        return _convert_picture_data(data, preset=preset, output_format=output_format)
    except PictureImportError:
        raise
    except (OSError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombError) as exc:
        raise PictureImportError("Cannot decode or convert this local picture") from exc


def _convert_picture_data(data: bytes, *, preset: str, output_format: str) -> ImportedPicture:
    """Shared content-validated conversion for source files and clipboard pixels."""
    max_edge, quality = PRESETS[preset]
    with Image.open(BytesIO(data)) as input_image:
        if input_image.format not in {"JPEG", "PNG", "BMP", "WEBP", "HEIF"}:
            raise PictureImportError("Unsupported image content format")
        width, height = input_image.size
        if (width < 1 or height < 1
            or width * height > MAX_DECODE_PIXELS):
            raise PictureImportError("Image dimensions exceed safe import limits")
        icc = input_image.info.get("icc_profile")
        if icc and (not isinstance(icc, bytes) or len(icc) > MAX_ICC_BYTES):
            raise PictureImportError("Unsupported or oversized image color profile")
        oriented = ImageOps.exif_transpose(input_image)
        oriented.load()
        # Convert non-sRGB tagged pictures before stripping camera metadata.
        has_alpha = ("A" in oriented.getbands()
                     or "transparency" in input_image.info)
        mode = "RGBA" if has_alpha else "RGB"
        if icc:
            try:
                src_profile = ImageCms.ImageCmsProfile(BytesIO(icc))
                dest_profile = ImageCms.createProfile("sRGB")
                if has_alpha:
                    alpha = oriented.convert("RGBA").getchannel("A")
                    rgb = ImageCms.profileToProfile(
                        oriented.convert("RGB"), src_profile, dest_profile,
                        outputMode="RGB")
                    converted = rgb.convert("RGBA")
                    converted.putalpha(alpha)
                else:
                    converted = ImageCms.profileToProfile(
                        oriented.convert("RGB"), src_profile, dest_profile,
                        outputMode="RGB")
            except (OSError, ValueError, TypeError, ImageCms.PyCMSError) as exc:
                raise PictureImportError("Unsupported source color profile") from exc
        else:
            converted = oriented.convert(mode)
        preview = converted.copy()
        preview.thumbnail((440, 320), Image.Resampling.LANCZOS)
        preview_buffer = BytesIO()
        preview.save(preview_buffer, format="PNG")
        converted.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        chosen = ("png" if has_alpha else "jpeg") if output_format == "auto" else output_format
        if chosen == "jpeg" and has_alpha:
            raise PictureImportError("JPEG cannot preserve transparency; choose PNG or WebP")
        # No EXIF, XMP, IPTC or GPS metadata is copied to project media.
        output = BytesIO()
        settings = {"quality": quality, "method": 5} if chosen == "webp" else (
            {"quality": quality, "optimize": True, "subsampling": 0}
            if chosen == "jpeg" else {"optimize": True})
        converted.save(output, format=chosen.upper(), **settings)
        result = output.getvalue()
        if not result or len(result) > MAX_ASSET:
            raise PictureImportError("Converted picture exceeds the 32 MiB project limit")
        return ImportedPicture(result, chosen, converted.width, converted.height,
                               width, height, size, preview_buffer.getvalue())


def convert_picture_bytes(data: bytes, *, preset: str = "balanced",
                          output_format: str = "auto") -> ImportedPicture:
    """Import detached clipboard image bytes with the exact source-image limits.

    Callers must only supply encoded pixel data, never arbitrary clipboard HTML
    or text. The decoded source format is independently verified by Pillow.
    """
    if preset not in PRESETS or output_format not in {"auto", "jpeg", "png", "webp"}:
        raise PictureImportError("Unsupported picture conversion options")
    if not isinstance(data, bytes) or not data or len(data) > MAX_SOURCE_BYTES:
        raise PictureImportError("Clipboard picture exceeds the 64 MiB import limit")
    try:
        return _convert_picture_data(data, preset=preset, output_format=output_format)
    except PictureImportError:
        raise
    except (OSError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombError) as exc:
        raise PictureImportError("Cannot decode clipboard picture") from exc


def add_imported_picture(project: ReportProject, photo: ImportedPicture,
                         name: str) -> str:
    """Commit a validated detached asset to the library, or leave it untouched."""
    if not isinstance(project, ReportProject) or not isinstance(photo, ImportedPicture):
        raise PictureImportError("Invalid project image import")
    name = name.strip() if isinstance(name, str) else ""
    if not name or len(name) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise PictureImportError("Picture name must be 1–200 printable characters")
    if not isinstance(photo.data, bytes) or not photo.data or len(photo.data) > MAX_ASSET:
        raise PictureImportError("Invalid imported picture bytes")
    key = uuid4().hex
    # Validate on a detached working project so failed mutations stay atomic.
    assets = dict(project.assets)
    library = dict(project.media_library)
    assets[key] = photo.data
    library[key] = name
    _assets_checked(ReportProject(project.report, assets, library))
    project.assets[key] = photo.data
    project.media_library[key] = name
    return key


def import_picture(project: ReportProject, source: str | Path, *,
                   preset: str = "balanced", output_format: str = "auto") -> str:
    picture = convert_picture(source, preset=preset, output_format=output_format)
    return add_imported_picture(project, picture, Path(source).stem)


def remove_library_picture(project: ReportProject, asset_id: str) -> None:
    """User-requested removal; never removes an image still used in the report."""
    if asset_id not in project.media_library:
        raise PictureImportError("Picture is not in the project library")
    if asset_id in _photo_ids(project.report):
        raise PictureImportError("Remove the picture from report modules before deleting it")
    del project.media_library[asset_id]
    # An Undo may restore a formerly placed PhotoBlock. Retain its bytes in
    # the session-only M2 undo cache; save_project serializes ONLY currently
    # placed or declared media, so deleted photos never survive on disk.
    # The in-memory bytes are released when the document closes.


def stage_pictures(paths: list[str | Path], *, preset: str = "balanced",
                   output_format: str = "auto") -> list[StagedPicture]:
    """Read external originals once. Detached, bounded bytes are approval input."""
    if not isinstance(paths, list) or len(paths) > MAX_IMPORT_BATCH:
        raise PictureImportError("Import at most 64 pictures per batch")
    staged = []
    total = 0
    for path in paths:
        name = Path(path).stem
        name = name.strip() if isinstance(name, str) else ""
        if not name or len(name) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise PictureImportError("Invalid photo name")
        photo = convert_picture(path, preset=preset, output_format=output_format)
        total += len(photo.data)
        if total > MAX_TOTAL_ASSETS:
            raise PictureImportError("Picture batch exceeds project limit")
        staged.append(StagedPicture(name, photo))
    return staged


def commit_staged_pictures(project: ReportProject,
                           staged: list[StagedPicture]) -> list[str]:
    """Commit EXACT bytes previously previewed. No external files re-opened."""
    if not isinstance(project, ReportProject) or not isinstance(staged, list):
        raise PictureImportError("Invalid picture import transaction")
    if len(staged) > MAX_IMPORT_BATCH:
        raise PictureImportError("Import at most 64 pictures per batch")
    assets = dict(project.assets)
    library = dict(project.media_library)
    keys = []
    for entry in staged:
        if not isinstance(entry, StagedPicture) or not isinstance(entry.photo, ImportedPicture):
            raise PictureImportError("Invalid staged picture")
        name, photo = entry.name, entry.photo
        if (not isinstance(name, str) or not name.strip() or len(name) > 200
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or not isinstance(photo.data, bytes) or not photo.data
            or len(photo.data) > MAX_ASSET):
            raise PictureImportError("Invalid staged picture data")
        key = uuid4().hex
        assets[key] = photo.data
        library[key] = name
        keys.append(key)
    _assets_checked(ReportProject(project.report, assets, library))
    project.assets.update({key: assets[key] for key in keys})
    project.media_library.update({key: library[key] for key in keys})
    return keys


def import_pictures(project: ReportProject, paths: list[str | Path], *,
                    preset: str = "balanced",
                    output_format: str = "auto") -> list[str]:
    """All-or-nothing batch import, reading each original exactly once."""
    return commit_staged_pictures(
        project, stage_pictures(paths, preset=preset, output_format=output_format))
