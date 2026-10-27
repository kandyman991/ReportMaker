"""M0 structured report data model. No GUI, storage or web dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from dataclasses import fields
from re import fullmatch
from uuid import uuid4

from .reference import CustomerSnapshot
from .rich_text import RichFormatting


def validate_language_tag(language: str) -> str:
    """Accept extensible BCP-47-style tags; this is syntax checking, not a locale registry."""
    if not isinstance(language, str) or not fullmatch(
        r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", language
    ):
        raise ValueError(f"Invalid language tag: {language!r}")
    return language


@dataclass
class LocalizedText:
    original_language: str
    original: str
    translations: dict[str, str] = field(default_factory=dict)
    stale_languages: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        validate_localized_text(self)

    def update_original(self, value: str) -> None:
        if not isinstance(value, str):
            raise ValueError("Source text must be a string")
        if value != self.original:
            self.original = value
            self.stale_languages.update(self.translations)

    def set_translation(self, language: str, text: str) -> None:
        validate_language_tag(language)
        if not isinstance(text, str):
            raise ValueError("Translation text must be a string")
        if language.lower() == self.original_language.lower():
            raise ValueError("A translation cannot overwrite the original")
        if any(existing.lower() == language.lower() and existing != language
               for existing in self.translations):
            raise ValueError("Language tag already present with different casing")
        self.translations[language] = text
        self.stale_languages.discard(language)


def validate_localized_text(value: LocalizedText) -> None:
    """Read-only check; serialized source, translations and provenance must reopen."""
    if not isinstance(value, LocalizedText):
        raise ValueError("Expected localized text")
    validate_language_tag(value.original_language)
    if not isinstance(value.original, str):
        raise ValueError("Original text must be a string")
    if not isinstance(value.translations, dict) or not isinstance(value.stale_languages, set):
        raise ValueError("Invalid translation collection or stale markers")
    seen = {value.original_language.lower()}
    for language, translation in value.translations.items():
        validate_language_tag(language)
        if not isinstance(translation, str):
            raise ValueError("Translation must contain text")
        lowered = language.lower()
        if lowered in seen:
            raise ValueError("Duplicate or source-language translation")
        seen.add(lowered)
    if not all(isinstance(language, str) and language in value.translations
               for language in value.stale_languages):
        raise ValueError("Stale translation does not correspond to a stored translation")


def validate_report_metadata(report: Report) -> None:
    """Pure validation, including fields that project save/load round-trip.

    __post_init__ supplies legacy defaults *only at first construction*.
    Running validation on an edited report must never repair or mutate it.
    """
    if not isinstance(report, Report):
        raise ValueError("Expected a report")
    if not isinstance(report.id, str) or not report.id.strip():
        raise ValueError("Report ID must be nonempty text")
    if report.customer_id is not None and not isinstance(report.customer_id, str):
        raise ValueError("Customer ID must be a string or None")
    customer_id = report.customer_id or ""
    snapshot = report.customer_snapshot
    if not customer_id.strip() and snapshot is None:
        raise ValueError("A customer ID or a manual customer snapshot is required")
    if snapshot is not None:
        if not isinstance(snapshot, CustomerSnapshot):
            raise ValueError("Invalid customer snapshot")
        # M1's frozen snapshots can be supplied via deserialization and should
        # be checked before persistence, without contacting the live database.
        for item in fields(CustomerSnapshot):
            value = getattr(snapshot, item.name)
            if item.name == "schema_version":
                if type(value) is not int or value != 1:
                    raise ValueError("Unsupported snapshot schema")
            elif item.name in {"customer_id", "site_id", "machine_id"}:
                if value is not None and not isinstance(value, str):
                    raise ValueError("Snapshot reference IDs must be text")
            elif not isinstance(value, str):
                raise ValueError("Snapshot attributes must be text")
        if not snapshot.customer_name.strip():
            raise ValueError("A customer snapshot requires a name")
        if snapshot.machine_id and not snapshot.site_id or (
            snapshot.site_id and not snapshot.customer_id
        ):
            raise ValueError("Inconsistent customer/site/machine snapshot links")
        if (snapshot.customer_id or "") != customer_id:
            raise ValueError("Report customer ID and captured reference disagree")
    if customer_id and not customer_id.strip():
        raise ValueError("Blank customer ID is not a registered reference")
    if (not isinstance(report.start_date, date)
        or isinstance(report.start_date, datetime)
        or not isinstance(report.end_date, date)
        or isinstance(report.end_date, datetime)
        or report.start_date > report.end_date):
        raise ValueError("Invalid intervention date range")
    if not isinstance(report.created_date, date) or isinstance(report.created_date, datetime):
        raise ValueError("Creation date must be a date")
    validate_language_tag(report.primary_language)
    if not isinstance(report.output_languages, list) or not report.output_languages:
        raise ValueError("Select at least one output language")
    for language in report.output_languages:
        validate_language_tag(language)
    if len({language.lower() for language in report.output_languages}) != len(report.output_languages):
        raise ValueError("Duplicate output language")
    validate_localized_text(report.title)
    if not isinstance(report.ticket, str):
        raise ValueError("Ticket must be text")
    if not isinstance(report.technicians, list) or any(
        not isinstance(name, str) or not name.strip() for name in report.technicians
    ):
        raise ValueError("Technicians must be nonempty strings")
    valid_types = {"supervision", "ordinary_maintenance", "extraordinary_maintenance", "other"}
    if not isinstance(report.intervention_types, list) or any(
        not isinstance(kind, str) or kind not in valid_types
        for kind in report.intervention_types
    ) or len(report.intervention_types) != len(set(report.intervention_types)):
        raise ValueError("Invalid or duplicated intervention types")
    if not isinstance(report.other_intervention_detail, str):
        raise ValueError("Other intervention description must be text")
    if "other" in report.intervention_types and not report.other_intervention_detail.strip():
        raise ValueError("Other intervention type requires a description")
    if "other" not in report.intervention_types and report.other_intervention_detail.strip():
        raise ValueError("Other intervention description requires the Other type")
    if not isinstance(report.modules, list):
        raise ValueError("Report modules must be a list")
    if not isinstance(report.conclusion, Module):
        raise ValueError("A dedicated Conclusions section is required")


@dataclass
class ParagraphBlock:
    text: LocalizedText
    id: str = field(default_factory=lambda: uuid4().hex)
    rich: RichFormatting = field(default_factory=RichFormatting)


# A photograph's source bytes are project-owned and never modified by the editor.
# Per-placement visual state lives with the PhotoBlock, not the shared media asset.
PHOTO_MARK_KINDS = frozenset({"arrow", "line", "rectangle", "ellipse",
                              "highlight", "text", "callout", "pen"})
MAX_PHOTO_MARKS = 120
MAX_PEN_POINTS = 500


@dataclass
class PhotoMark:
    kind: str
    x: float
    y: float
    x2: float
    y2: float
    color: str = "#e02020"
    thickness: int = 3
    text: LocalizedText | None = None
    points: list[tuple[float, float]] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class PhotoVisual:
    # Normalized coordinates relative to the oriented source working copy.
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    rotation: int = 0  # multiples of 90 degrees
    straighten: int = 0  # additional degrees (-15..15)
    flip_h: bool = False
    flip_v: bool = False
    width_pct: int = 100
    alignment: str = "center"
    marks: list[PhotoMark] = field(default_factory=list)


def validate_photo_visual(value: PhotoVisual) -> None:
    import math
    if not isinstance(value, PhotoVisual):
        raise ValueError("Invalid photo visual state")
    def coordinate(v):
        return type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 1
    if (not isinstance(value.crop, tuple) or len(value.crop) != 4
        or not all(coordinate(p) for p in value.crop)):
        raise ValueError("Invalid photo crop")
    x, y, width, height = value.crop
    if width < 0.01 or height < 0.01 or x + width > 1.000001 or y + height > 1.000001:
        raise ValueError("Photo crop must be nonempty and inside the original")
    if (type(value.rotation) is not int or value.rotation not in (0, 90, 180, 270)
        or type(value.straighten) is not int or not -15 <= value.straighten <= 15
        or type(value.flip_h) is not bool or type(value.flip_v) is not bool
        or type(value.width_pct) is not int or not 20 <= value.width_pct <= 100
        or value.alignment not in ("left", "center", "right")):
        raise ValueError("Unsupported photo layout/transform")
    if not isinstance(value.marks, list) or len(value.marks) > MAX_PHOTO_MARKS:
        raise ValueError("Too many photo annotations")
    ids = set()
    for mark in value.marks:
        if (not isinstance(mark, PhotoMark) or not isinstance(mark.kind, str)
            or mark.kind not in PHOTO_MARK_KINDS
            or not all(coordinate(v) for v in (mark.x, mark.y, mark.x2, mark.y2))
            or type(mark.thickness) is not int or not 1 <= mark.thickness <= 16
            or not isinstance(mark.color, str)
            or not fullmatch(r"#[0-9A-Fa-f]{6}", mark.color)
            or not isinstance(mark.id, str) or not fullmatch(r"[a-f0-9]{32}", mark.id)
            or mark.id in ids):
            raise ValueError("Invalid photo annotation")
        ids.add(mark.id)
        if (not isinstance(mark.points, list) or len(mark.points) > MAX_PEN_POINTS
            or any(not isinstance(pair, tuple) or len(pair) != 2
                   or not all(coordinate(v) for v in pair) for pair in mark.points)
            or (mark.kind == "pen" and len(mark.points) < 2)
            or (mark.kind != "pen" and mark.points)):
            raise ValueError("Invalid freehand photo annotation")
        if mark.kind in ("text", "callout"):
            validate_localized_text(mark.text)
            if len(mark.text.original) > 500:
                raise ValueError("Photo text annotation is too long")
        elif mark.text is not None:
            raise ValueError("Shapes cannot carry hidden text")


@dataclass
class PhotoBlock:
    asset_id: str  # logical ID, not filesystem path or remote URL
    caption: LocalizedText | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    visual: PhotoVisual = field(default_factory=PhotoVisual)


@dataclass
class TableBlock:
    rows: list[list[LocalizedText]]
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class HeadingBlock:
    text: LocalizedText
    level: int = 2
    id: str = field(default_factory=lambda: uuid4().hex)
    rich: RichFormatting = field(default_factory=RichFormatting)


@dataclass
class PageBreakBlock:
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class Module:
    title: LocalizedText
    blocks: list[Block] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class NestedModuleBlock:
    module: Module
    id: str = field(default_factory=lambda: uuid4().hex)


Block = ParagraphBlock | HeadingBlock | PhotoBlock | TableBlock | PageBreakBlock | NestedModuleBlock


@dataclass
class Report:
    customer_id: str | None
    start_date: date
    end_date: date
    primary_language: str
    output_languages: list[str]
    conclusion: Module
    modules: list[Module] = field(default_factory=list)
    ticket: str = ""
    id: str = field(default_factory=lambda: uuid4().hex)
    customer_snapshot: CustomerSnapshot | None = None
    created_date: date = field(default_factory=date.today)
    title: LocalizedText | None = None
    technicians: list[str] = field(default_factory=list)
    intervention_types: list[str] = field(default_factory=list)
    other_intervention_detail: str = ""

    def __post_init__(self) -> None:
        # Preserve M0/M1 constructor compatibility without mutating later edits.
        if self.title is None:
            self.title = LocalizedText(self.primary_language, "Report of intervention")
        validate_report_metadata(self)

    def ordered_sections(self) -> tuple[Module, ...]:
        """Conclusion is never interspersed with user-reorderable modules."""
        if any(module.id == self.conclusion.id for module in self.modules):
            raise ValueError("Conclusion cannot also be an intervention module")
        return (*self.modules, self.conclusion)
