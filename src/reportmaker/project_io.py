"""M2 local, portable report-project bundles (.rmproj).

One ZIP file is the canonical editable project, never a Word/PDF export.
Files are not extracted: asset names are logical IDs, never disk paths. All
operations are local; no browser data or network dependencies are involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
import zlib

from .engine import MAX_NESTING, validate_report_tree
from .model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, Report, TableBlock,
)
from .reference import CustomerSnapshot

FORMAT = "reportmaker.project"
VERSION = 2
LEGACY_VERSION = 1
MAX_MANIFEST = 8 * 1024 * 1024
MAX_ASSET = 32 * 1024 * 1024
MAX_TOTAL_ASSETS = 256 * 1024 * 1024
MAX_ENTRIES = 2048
ASSET_ID = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")


@dataclass
class ReportProject:
    report: Report
    assets: dict[str, bytes] = field(default_factory=dict)
    # Explicit project media-library membership persists even without PhotoBlocks.
    # Unlike legacy v1 orphans, these images are intentionally user-owned content.
    media_library: dict[str, str] = field(default_factory=dict)  # asset ID -> display name
    # Session-only provenance; never serialized to project or browser data.
    loaded_version: int = VERSION
    loaded_from: Path | None = None


def default_projects_directory() -> Path:
    """Windows user data location independent of Chromium/profile storage."""
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(
            Path.home() / "AppData" / "Local"))) / "ReportMaker" / "projects"
    return Path(os.environ.get("XDG_DATA_HOME", str(
        Path.home() / ".local" / "share"))) / "reportmaker" / "projects"


def _shape(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required) <= obj.keys() or (
        obj.keys() - set(required) - set(optional)
    ):
        raise ValueError("Incompatible project record properties")
    return obj


def _string(value):
    if not isinstance(value, str):
        raise ValueError("Expected text")
    return value


def _date(value):
    value = _string(value)
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid project date") from exc
    if result.isoformat() != value:
        raise ValueError("Project dates must use canonical YYYY-MM-DD")
    return result


def _localized_to(value: LocalizedText):
    if not isinstance(value, LocalizedText):
        raise ValueError("Invalid localized content")
    return {
        "original_language": value.original_language,
        "original": value.original,
        "translations": dict(value.translations),
        "stale_languages": sorted(value.stale_languages),
    }


def _localized_from(obj):
    obj = _shape(obj, ("original_language", "original", "translations", "stale_languages"))
    translations, stale = obj["translations"], obj["stale_languages"]
    if (not isinstance(translations, dict) or
        any(not isinstance(k, str) or not isinstance(v, str)
            for k, v in translations.items()) or
        not isinstance(stale, list) or
        any(not isinstance(v, str) for v in stale) or
        len(stale) != len(set(stale)) or not set(stale) <= translations.keys()):
        raise ValueError("Invalid translation provenance")
    return LocalizedText(_string(obj["original_language"]), _string(obj["original"]),
                         translations, set(stale))


def _module_to(value: Module):
    return {"id": value.id, "title": _localized_to(value.title),
            "blocks": [_block_to(b) for b in value.blocks]}


def _block_to(block):
    record = {"id": block.id}
    if isinstance(block, ParagraphBlock):
        record.update(kind="paragraph", text=_localized_to(block.text))
    elif isinstance(block, HeadingBlock):
        record.update(kind="heading", text=_localized_to(block.text), level=block.level)
    elif isinstance(block, PhotoBlock):
        record.update(kind="photo", asset_id=block.asset_id,
                      caption=_localized_to(block.caption) if block.caption is not None else None)
    elif isinstance(block, TableBlock):
        record.update(kind="table", rows=[[_localized_to(c) for c in row] for row in block.rows])
    elif isinstance(block, PageBreakBlock):
        record.update(kind="page_break")
    elif isinstance(block, NestedModuleBlock):
        record.update(kind="module", module=_module_to(block.module))
    else:
        raise ValueError("Unknown report block")
    return record


def _module_from(obj, depth=0):
    if depth > MAX_NESTING:
        raise ValueError("Report project is too deeply nested")
    obj = _shape(obj, ("id", "title", "blocks"))
    if not isinstance(obj["blocks"], list):
        raise ValueError("Module blocks must be an array")
    return Module(_localized_from(obj["title"]),
                  [_block_from(b, depth) for b in obj["blocks"]], _string(obj["id"]))


def _block_from(obj, depth):
    obj = _shape(obj, ("kind", "id"), ("text", "level", "asset_id", "caption", "rows", "module"))
    kind, identifier = _string(obj["kind"]), _string(obj["id"])
    allowed = {
        "paragraph": {"kind", "id", "text"},
        "heading": {"kind", "id", "text", "level"},
        "photo": {"kind", "id", "asset_id", "caption"},
        "table": {"kind", "id", "rows"},
        "page_break": {"kind", "id"},
        "module": {"kind", "id", "module"},
    }
    if kind not in allowed or obj.keys() != allowed[kind]:
        raise ValueError("Unsupported or inconsistent block kind")
    if kind == "paragraph":
        return ParagraphBlock(_localized_from(obj["text"]), identifier)
    if kind == "heading":
        return HeadingBlock(_localized_from(obj["text"]), obj["level"], identifier)
    if kind == "photo":
        caption = obj["caption"]
        return PhotoBlock(_string(obj["asset_id"]),
                          _localized_from(caption) if caption is not None else None, identifier)
    if kind == "table":
        if not isinstance(obj["rows"], list) or any(not isinstance(r, list) for r in obj["rows"]):
            raise ValueError("Table must have rows")
        return TableBlock([[_localized_from(c) for c in row] for row in obj["rows"]], identifier)
    if kind == "page_break":
        return PageBreakBlock(identifier)
    return NestedModuleBlock(_module_from(obj["module"], depth + 1), identifier)


def _snapshot_checked(value):
    """Fail closed on malformed imported customer/site/machine snapshot data."""
    if not isinstance(value, dict):
        raise ValueError("Customer snapshot must be an object")
    valid = {f.name for f in fields(CustomerSnapshot)}
    if set(value) - valid:
        raise ValueError("Unknown customer snapshot field")
    snapshot = CustomerSnapshot.from_dict(value)
    for key, entry in snapshot.to_dict().items():
        if key == "schema_version":
            if type(entry) is not int or entry != 1:
                raise ValueError("Unsupported snapshot schema version")
        elif key in ("customer_id", "site_id", "machine_id"):
            if entry is not None and not isinstance(entry, str):
                raise ValueError("Invalid snapshot database link")
        elif not isinstance(entry, str):
            raise ValueError("Snapshot details must be text")
    return snapshot


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicated JSON project field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON constant in project")


def _report_to(report):
    validate_report_tree(report)
    if report.customer_snapshot is None:
        raise ValueError("Persisted projects require a detached customer snapshot")
    _snapshot_checked(report.customer_snapshot.to_dict())
    return {
        "id": report.id, "customer_id": report.customer_id,
        "customer_snapshot": report.customer_snapshot.to_dict(),
        "created_date": report.created_date.isoformat(),
        "title": _localized_to(report.title),
        "start_date": report.start_date.isoformat(), "end_date": report.end_date.isoformat(),
        "primary_language": report.primary_language,
        "output_languages": list(report.output_languages),
        "ticket": report.ticket, "technicians": list(report.technicians),
        "intervention_types": list(report.intervention_types),
        "other_intervention_detail": report.other_intervention_detail,
        "modules": [_module_to(m) for m in report.modules],
        "conclusion": _module_to(report.conclusion),
    }


def _report_from(obj):
    obj = _shape(obj, ("id", "customer_id", "customer_snapshot", "created_date",
                       "title", "start_date", "end_date", "primary_language",
                       "output_languages", "ticket", "technicians", "intervention_types",
                       "other_intervention_detail", "modules", "conclusion"))
    if (not isinstance(obj["output_languages"], list) or
        not isinstance(obj["technicians"], list) or
        not isinstance(obj["intervention_types"], list) or
        not isinstance(obj["modules"], list)):
        raise ValueError("Invalid report collection")
    customer_id = obj["customer_id"]
    if customer_id is not None:
        _string(customer_id)
    report = Report(
        customer_id=customer_id,
        customer_snapshot=_snapshot_checked(obj["customer_snapshot"]),
        created_date=_date(obj["created_date"]), title=_localized_from(obj["title"]),
        start_date=_date(obj["start_date"]), end_date=_date(obj["end_date"]),
        primary_language=_string(obj["primary_language"]),
        output_languages=[_string(v) for v in obj["output_languages"]],
        ticket=_string(obj["ticket"]),
        technicians=[_string(v) for v in obj["technicians"]],
        intervention_types=[_string(v) for v in obj["intervention_types"]],
        other_intervention_detail=_string(obj["other_intervention_detail"]),
        modules=[_module_from(v) for v in obj["modules"]],
        conclusion=_module_from(obj["conclusion"]),
        id=_string(obj["id"]),
    )
    validate_report_tree(report)
    return report


def _photo_ids(report):
    ids = set()
    stack = list(report.ordered_sections())
    while stack:
        module = stack.pop()
        for block in module.blocks:
            if isinstance(block, PhotoBlock):
                ids.add(block.asset_id)
            elif isinstance(block, NestedModuleBlock):
                stack.append(block.module)
    return ids


def _assets_checked(project):
    if not isinstance(project, ReportProject) or not isinstance(project.assets, dict):
        raise ValueError("Expected a report project")
    report_json = _report_to(project.report)
    # Keep all placed photos plus explicitly listed project media. Unlisted
    # in-memory orphan bytes remain available for Undo but are never serialized.
    if not isinstance(project.media_library, dict):
        raise ValueError("Invalid project picture container")
    library = []
    for identifier, name in sorted(project.media_library.items()):
        if (not isinstance(identifier, str) or ASSET_ID.fullmatch(identifier) is None
            or not isinstance(name, str) or not name.strip() or len(name) > 200
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
            raise ValueError("Invalid media-library entry")
        library.append({"id": identifier, "name": name})
    referenced = _photo_ids(project.report) | set(project.media_library)
    for identifier in project.assets:
        if not isinstance(identifier, str) or ASSET_ID.fullmatch(identifier) is None:
            raise ValueError("Unsafe logical asset ID")
    if not referenced <= project.assets.keys():
        raise ValueError("Project refers to an asset that has not been stored")
    total = 0
    metadata = []
    for identifier in sorted(referenced):
        blob = project.assets[identifier]
        if not isinstance(blob, bytes) or len(blob) > MAX_ASSET:
            raise ValueError("Referenced photo assets must be bounded bytes")
        total += len(blob)
        if total > MAX_TOTAL_ASSETS or len(metadata) >= MAX_ENTRIES - 1:
            raise ValueError("Report assets exceed project limits")
        metadata.append({"id": identifier, "length": len(blob),
                         "sha256": sha256(blob).hexdigest()})
    manifest = {"format": FORMAT, "version": VERSION,
                "report": report_json, "assets": metadata,
                "media_library": library}
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(serialized) > MAX_MANIFEST:
        raise ValueError("Report metadata is too large")
    return serialized, metadata


def save_project(project: ReportProject, destination: str | Path) -> Path:
    """Atomically save in-place, preserving an existing file on save failure."""
    target = Path(destination)
    if target.is_symlink() or target.is_dir():
        raise ValueError("Project target cannot be a symlink or directory")
    if (project.loaded_version == LEGACY_VERSION and project.loaded_from is not None
        and os.path.normcase(os.path.abspath(target)) ==
            os.path.normcase(os.path.abspath(project.loaded_from))):
        raise ValueError("This v1 project must be upgraded with Save As to a new file; original v1 project was preserved")
    manifest, metadata = _assets_checked(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".reportmaker-", suffix=".tmp",
                                    dir=target.parent)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w+b") as stream:
            with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", manifest)
                for record in metadata:
                    key = record["id"]
                    archive.writestr("assets/" + key, project.assets[key])
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck immediately before replace; reject accidental symlink swap.
        if target.is_symlink():
            raise ValueError("Project target became a symlink")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def load_project(source: str | Path) -> ReportProject:
    """Parse a project archive without writing/extracting any untrusted files."""
    source = Path(source)
    if source.is_symlink():
        raise ValueError("Project source cannot be a symlink")
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if (not names or len(names) > MAX_ENTRIES or len(names) != len(set(names)) or
                "manifest.json" not in names or any(i.is_dir() for i in infos)):
                raise ValueError("Invalid project archive entries")
            for info in infos:
                # Never enter zipfile's unsupported/encrypted compression paths.
                # ZIP_STORED and ZIP_DEFLATED are sufficient for v1 and native
                # Python interoperability on Windows.
                if (info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or info.flag_bits & (0x1 | 0x40 | 0x2000)):
                    raise ValueError("Unsupported ZIP compression or encryption")
                if (info.file_size > (MAX_MANIFEST if info.filename == "manifest.json" else MAX_ASSET)
                    or info.filename != "manifest.json" and
                    not info.filename.startswith("assets/")):
                    raise ValueError("Unexpected or oversized project archive entry")
            data = archive.read("manifest.json")
            if len(data) > MAX_MANIFEST:
                raise ValueError("Project manifest is too large")
            manifest = json.loads(data.decode("utf-8"),
                                  object_pairs_hook=_unique_pairs,
                                  parse_constant=_reject_constant)
            if (not isinstance(manifest, dict) or manifest.get("format") != FORMAT
                or type(manifest.get("version")) is not int
                or manifest["version"] not in (LEGACY_VERSION, VERSION)):
                raise ValueError("Unsupported project schema; no automatic downgrade")
            if manifest["version"] == LEGACY_VERSION:
                _shape(manifest, ("format", "version", "report", "assets"))
                library = {}
            else:
                _shape(manifest, ("format", "version", "report", "assets", "media_library"))
                entries = manifest["media_library"]
                if not isinstance(entries, list) or len(entries) > MAX_ENTRIES - 1:
                    raise ValueError("Invalid media library")
                library = {}
                for entry in entries:
                    entry = _shape(entry, ("id", "name"))
                    identifier, name = entry["id"], entry["name"]
                    if (not isinstance(identifier, str) or ASSET_ID.fullmatch(identifier) is None
                        or not isinstance(name, str) or not name.strip() or len(name) > 200
                        or any(ord(char) < 32 or ord(char) == 127 for char in name)
                        or identifier in library):
                        raise ValueError("Invalid or duplicated media-library member")
                    library[identifier] = name
            if not isinstance(manifest["assets"], list):
                raise ValueError("Project asset records must be an array")
            expected = {"manifest.json"}
            assets = {}
            total = 0
            for item in manifest["assets"]:
                item = _shape(item, ("id", "length", "sha256"))
                identifier = _string(item["id"])
                if ASSET_ID.fullmatch(identifier) is None or type(item["length"]) is not int or not 0 <= item["length"] <= MAX_ASSET:
                    raise ValueError("Invalid asset metadata")
                name = "assets/" + identifier
                if name in expected:
                    raise ValueError("Duplicated logical asset")
                expected.add(name)
                if name not in names:
                    raise ValueError("Referenced archive asset missing")
                total += item["length"]
                if total > MAX_TOTAL_ASSETS:
                    raise ValueError("Project assets exceed limit")
                blob = archive.read(name)
                if len(blob) != item["length"] or sha256(blob).hexdigest() != item["sha256"]:
                    raise ValueError("Asset length/hash mismatch")
                assets[identifier] = blob
            if set(names) != expected:
                raise ValueError("Unlisted/untrusted files in project archive")
            report = _report_from(manifest["report"])
            # Legacy v1 bundles may contain verified orphans, discarded on load.
            # v2 only contains block-referenced or explicitly declared library
            # assets; reject hidden unreferenced ZIP members even if hashed.
            keep = _photo_ids(report) | set(library)
            if not keep <= assets.keys():
                raise ValueError("Declared picture is missing from archive")
            if manifest["version"] == VERSION and set(assets) != keep:
                raise ValueError("Undeclared project image asset")
            project = ReportProject(report, {
                identifier: assets[identifier] for identifier in keep
            }, library, manifest["version"], source.absolute())
            _assets_checked(project)
            return project
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError,
            EOFError, zlib.error, NotImplementedError, RuntimeError) as exc:
        raise ValueError("Invalid, unsupported or damaged ReportMaker project") from exc
