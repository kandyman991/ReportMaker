"""M2 local, portable report-project bundles (.rmproj).

One ZIP file is the canonical editable project, never a Word/PDF export.
Files are not extracted: asset names are logical IDs, never disk paths. All
operations are local; no browser data or network dependencies are involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

from .engine import MAX_NESTING, validate_report_tree
from .model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, Report, TableBlock,
)
from .reference import CustomerSnapshot

FORMAT = "reportmaker.project"
VERSION = 1
MAX_MANIFEST = 8 * 1024 * 1024
MAX_ASSET = 32 * 1024 * 1024
MAX_TOTAL_ASSETS = 256 * 1024 * 1024
MAX_ENTRIES = 2048
ASSET_ID = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")


@dataclass
class ReportProject:
    report: Report
    assets: dict[str, bytes] = field(default_factory=dict)


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


def _report_to(report):
    validate_report_tree(report)
    if report.customer_snapshot is None:
        raise ValueError("Persisted projects require a detached customer snapshot")
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
        customer_snapshot=CustomerSnapshot.from_dict(obj["customer_snapshot"]),
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
    total = 0
    metadata = []
    for identifier, blob in sorted(project.assets.items()):
        if not isinstance(identifier, str) or ASSET_ID.fullmatch(identifier) is None:
            raise ValueError("Unsafe logical asset ID")
        if not isinstance(blob, bytes) or len(blob) > MAX_ASSET:
            raise ValueError("Photo assets must be bounded bytes")
        total += len(blob)
        if total > MAX_TOTAL_ASSETS or len(metadata) >= MAX_ENTRIES - 1:
            raise ValueError("Report assets exceed project limits")
        metadata.append({"id": identifier, "length": len(blob),
                         "sha256": sha256(blob).hexdigest()})
    if not _photo_ids(project.report) <= project.assets.keys():
        raise ValueError("Project refers to an asset that has not been stored")
    manifest = {"format": FORMAT, "version": VERSION,
                "report": report_json, "assets": metadata}
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
                "manifest.json" not in names or
                any(i.is_dir() or i.flag_bits & 0x1 for i in infos)):
                raise ValueError("Invalid project archive entries")
            for info in infos:
                if (info.file_size > (MAX_MANIFEST if info.filename == "manifest.json" else MAX_ASSET)
                    or info.filename != "manifest.json" and
                    not info.filename.startswith("assets/")):
                    raise ValueError("Unexpected or oversized project archive entry")
            data = archive.read("manifest.json")
            if len(data) > MAX_MANIFEST:
                raise ValueError("Project manifest is too large")
            manifest = _shape(json.loads(data.decode("utf-8")),
                              ("format", "version", "report", "assets"))
            if manifest["format"] != FORMAT or type(manifest["version"]) is not int or manifest["version"] != VERSION:
                raise ValueError("Unsupported project schema; no automatic downgrade")
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
            project = ReportProject(_report_from(manifest["report"]), assets)
            _assets_checked(project)
            return project
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, EOFError) as exc:
        raise ValueError("Invalid or damaged ReportMaker project") from exc
