"""Atomic multi-language DOCX/PDF bundle for the V2 Preview workspace.

All selected languages are rendered from detached projections of one canonical
report. The ZIP replaces its destination only after every requested export has
succeeded. Nothing is stored back in the .rmproj, browser, or customer database.
"""
from __future__ import annotations

from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
from typing import Callable, Sequence
from zipfile import ZIP_DEFLATED, ZipFile
import json
import os
import tempfile

from ..engine import validate_report_tree
from ..export import ExportError, ExportStyle, export_project
from ..model import PhotoVisual, validate_language_tag
from ..project_io import ReportProject
from .localized_export import localized_project
from .metadata_locale import resolve_export_metadata


def export_language_bundle(
    project: ReportProject,
    destination: str | Path,
    *,
    languages: Sequence[str] | None = None,
    formats: Sequence[str] = ("docx", "pdf"),
    style: ExportStyle | None = None,
    visual_renderer: Callable[[bytes, PhotoVisual], bytes] | None = None,
) -> Path:
    """Export an all-or-none ZIP with one file per language and format.

    Language tags are the exact BCP-47-style choices stored in the report;
    language-specific source content is checked field-by-field with no fallback.
    M6.5 requires explicit approved metadata/boilerplate translations for
    each target language; an incomplete member aborts the whole archive.
    """
    if not isinstance(project, ReportProject):
        raise ExportError("An editable ReportMaker project is required")
    validate_report_tree(project.report)
    destination = Path(destination)
    if destination.suffix.lower() != ".zip" or not destination.parent.is_dir():
        raise ExportError("Choose a .zip file in an existing folder")

    wanted = project.report.output_languages if languages is None else languages
    if not isinstance(wanted, (tuple, list)) or not wanted:
        raise ExportError("Select at least one export language")
    selected = []
    seen = set()
    allowed = {tag.casefold(): tag for tag in project.report.output_languages}
    for language in wanted:
        validate_language_tag(language)
        if language.casefold() not in allowed:
            raise ExportError("Language is not selected in Report Information: " + language)
        if language.casefold() in seen:
            raise ExportError("Duplicate export language")
        seen.add(language.casefold())
        selected.append(allowed[language.casefold()])
    if not isinstance(formats, (tuple, list)) or not 1 <= len(formats) <= 2:
        raise ExportError("Select DOCX, PDF, or both")
    if any(fmt not in ("docx", "pdf") for fmt in formats) or len(set(formats)) != len(formats):
        raise ExportError("Invalid or repeated export format")

    # All failures leave an existing destination unchanged; use ordinary
    # temporary files rather than holding multiple large media PDFs in RAM.
    # Destination parent keeps the final os.replace on the same filesystem.
    with TemporaryDirectory(prefix=".reportmaker-languages-", dir=destination.parent) as temp:
        root = Path(temp)
        members = []
        for language in selected:
            labels = resolve_export_metadata(project.report, language, style=style)
            translated = localized_project(project, language)
            for fmt in formats:
                # Language syntax allows only ASCII letters, digits and '-',
                # so no archive path may contain a slash, backslash or '..'.
                # Very long but syntactically valid tags must still fit
                # portable Windows filenames; use a stable digest suffix.
                safe = (language if len(language) <= 65 else
                        language[:48] + "_" +
                        sha256(language.encode("ascii")).hexdigest()[:12])
                name = f"report_{safe}.{fmt}"
                export_project(
                    translated, root / name, format=fmt, style=style,
                    visual_renderer=visual_renderer, locale_labels=labels)
                members.append({"language": language, "format": fmt, "file": name})
        manifest = {
            "schema": "reportmaker-v2-language-bundle-1",
            "source_language": project.report.primary_language,
            "languages": selected,
            "files": members,
            "metadata_localization": "Strict approved per-language labels, intervention types and other details; proper names and identifiers remain canonical.",
        }
        handle, scratch = tempfile.mkstemp(
            prefix=".reportmaker-language-bundle-", suffix=".zip",
            dir=destination.parent)
        os.close(handle)
        scratch_path = Path(scratch)
        try:
            with ZipFile(scratch_path, "w", compression=ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as package:
                package.writestr("manifest.json", json.dumps(
                    manifest, ensure_ascii=False, indent=2) + "\n")
                for item in members:
                    package.write(root / item["file"], arcname=item["file"])
            os.replace(scratch_path, destination)
        finally:
            scratch_path.unlink(missing_ok=True)
    return destination
