"""M4 local document exports over the validated M2 canonical report hierarchy.

DOCX contains editable Word paragraphs/tables/pictures and updateable PAGEREF
fields. PDF is paginated locally from the same outline and ordered blocks.
Neither export changes the .rmproj source or uses any network/AI service.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from hashlib import sha256
import os
from pathlib import Path
from typing import Callable
import tempfile
from xml.sax.saxutils import escape

from .engine import OutlineEntry, module_outline, validate_report_tree
from .model import (
    HeadingBlock, Module, NestedModuleBlock, PageBreakBlock, ParagraphBlock,
    PhotoBlock, PhotoVisual, TableBlock,
)
from .rich_text import RichFormatting, ParagraphStyle, style_at, validate_rich
from .project_io import MAX_ASSET, ReportProject


class ExportError(ValueError):
    """A report cannot be exported without dropping or altering its content."""


TYPE_LABELS = {
    "supervision": "Supervision",
    "ordinary_maintenance": "Ordinary maintenance",
    "extraordinary_maintenance": "Extraordinary maintenance",
    "other": "Other",
}
MAX_IMAGE_PIXELS = 36_000_000
MAX_BRAND_LOGO_BYTES = 2 * 1024 * 1024
PHOTO_MAX_WIDTH_CM = 15.6
PHOTO_MAX_HEIGHT_CM = 19.5


@dataclass(frozen=True)
class ExportStyle:
    """Optional local presentation. Never written to a project or browser profile."""
    company_name: str = ""
    footer_note: str = ""
    logo: bytes = b""
    page_width_cm: float = 21.0
    page_height_cm: float = 29.7
    left_margin_cm: float = 2.1
    right_margin_cm: float = 2.1
    top_margin_cm: float = 3.0
    bottom_margin_cm: float = 2.5
    header_distance_cm: float = 0.9
    footer_distance_cm: float = 0.9
    normal_font: str = ""
    normal_size_pt: float = 11.0
    heading_font: str = ""
    heading_size_pt: float = 16.0
    # Transient authored template prose; these are never included in .rmproj.
    footer_source_language: str | None = None
    footer_locale_approvals: tuple = ()


def _validate_style(style: ExportStyle | None) -> ExportStyle:
    if style is None:
        return ExportStyle()
    if not isinstance(style, ExportStyle):
        raise ExportError("Invalid export branding configuration")
    if not isinstance(style.logo, bytes) or len(style.logo) > MAX_BRAND_LOGO_BYTES:
        raise ExportError("Company logo exceeds the 2 MiB export limit")
    from .template_import import DocumentTemplate, TemplateError, validate_template
    try:
        validate_template(DocumentTemplate(
            page_width_cm=style.page_width_cm, page_height_cm=style.page_height_cm,
            left_margin_cm=style.left_margin_cm, right_margin_cm=style.right_margin_cm,
            top_margin_cm=style.top_margin_cm, bottom_margin_cm=style.bottom_margin_cm,
            header_distance_cm=style.header_distance_cm, footer_distance_cm=style.footer_distance_cm,
            header_text=style.company_name, footer_text=style.footer_note,
            normal_font=style.normal_font, normal_size_pt=style.normal_size_pt,
            heading_font=style.heading_font, heading_size_pt=style.heading_size_pt,
            logo=style.logo))
    except TemplateError as exc:
        raise ExportError(str(exc)) from exc
    if (style.company_name or style.logo) and style.top_margin_cm < 1.6:
        raise ExportError("Header requires at least 1.6 cm top margin")
    if style.bottom_margin_cm < 1.5:
        raise ExportError("Footer/page number requires at least 1.5 cm bottom margin")
    logo = _image_bytes(style.logo) if style.logo else b""
    return ExportStyle(style.company_name, style.footer_note, logo,
                       style.page_width_cm, style.page_height_cm,
                       style.left_margin_cm, style.right_margin_cm,
                       style.top_margin_cm, style.bottom_margin_cm,
                       style.header_distance_cm, style.footer_distance_cm,
                       style.normal_font, style.normal_size_pt,
                       style.heading_font, style.heading_size_pt,
                       style.footer_source_language, style.footer_locale_approvals)


def _photo_dimensions(image: bytes, max_width_cm: float = PHOTO_MAX_WIDTH_CM,
                      max_height_cm: float = PHOTO_MAX_HEIGHT_CM) -> tuple[float, float]:
    """Natural 96-dpi size, never larger than the selected printable page."""
    from PIL import Image
    with Image.open(BytesIO(image)) as im:
        width, height = im.size
    scale = min(2.54 / 96.0, max_width_cm / width,
                max_height_cm / height)
    return width * scale, height * scale


def _logo_dimensions(image: bytes, *, max_height_cm: float = 1.05) -> tuple[float, float]:
    """Logo at its natural (96-dpi) size, bounded without changing aspect ratio."""
    from PIL import Image
    with Image.open(BytesIO(image)) as im:
        width, height = im.size
    scale = min(2.54 / 96.0, 2.6 / width, max_height_cm / height)
    return width * scale, height * scale


@dataclass(frozen=True)
class RenderItem:
    kind: str
    text: str = ""
    depth: int = 0
    key: str = ""
    rows: tuple[tuple[str, ...], ...] = ()
    image: bytes = b""
    rich: RichFormatting | None = None
    photo_width_pct: int = 100
    photo_alignment: str = "default"


@dataclass(frozen=True)
class ExportPlan:
    title: str
    info: tuple[tuple[str, str], ...]
    outline: tuple[OutlineEntry, ...]
    items: tuple[RenderItem, ...]
    # Detached, prevalidated M6.5 semantic labels. Never stored in .rmproj.
    locale_labels: dict[str, str] | None = None


def _image_bytes(payload: bytes) -> bytes:
    """Convert supported source imagery to bounded, portable PNG bytes."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not isinstance(payload, bytes) or not payload:
        raise ExportError("Referenced photograph is missing")
    if len(payload) > MAX_ASSET:
        raise ExportError("Referenced photograph exceeds the project asset size limit")
    try:
        with Image.open(BytesIO(payload)) as im:
            if im.width < 1 or im.height < 1 or im.width * im.height > MAX_IMAGE_PIXELS:
                raise ExportError("Photograph dimensions exceed safe export limits")
            source_format = im.format
            im = ImageOps.exif_transpose(im)
            im.load()
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            im.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            stream = BytesIO()
            # Strip all source metadata, retaining efficient JPEG for photos.
            if source_format == "JPEG":
                im.convert("RGB").save(stream, format="JPEG", quality=90,
                                        optimize=True, subsampling=0)
            else:
                im.save(stream, format="PNG")
            return stream.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ExportError("Photograph is not a supported, safe local image") from exc


def prepare_export(project: ReportProject, *,
                   visual_renderer: Callable[[bytes, PhotoVisual], bytes] | None = None,
                   locale_labels: dict[str, str] | None = None) -> ExportPlan:
    """Read-only export projection; source text only until M5 localization UI.

    All module numbering and TOC entries come from the exact model outline used
    by the visual editor. No additional outline/list is maintained or persisted.
    """
    if not isinstance(project, ReportProject):
        raise ExportError("An editable ReportMaker project is required")
    report = project.report
    validate_report_tree(report)
    if not isinstance(project.assets, dict):
        raise ExportError("Invalid project assets")
    outline = module_outline(report)
    entries = {entry.module_id: entry for entry in outline}
    snapshot = report.customer_snapshot
    info = [
        ("Created", report.created_date.isoformat()),
        ("Intervention from", report.start_date.isoformat()),
        ("Intervention to", report.end_date.isoformat()),
        ("Customer", snapshot.customer_name if snapshot else ""),
        ("Site", snapshot.site_name if snapshot else ""),
        ("Machine", snapshot.machine_name if snapshot else ""),
        ("Machine serial", snapshot.machine_serial if snapshot else ""),
        ("Ticket", report.ticket),
        ("Personnel", ", ".join(report.technicians)),
        ("Intervention types", ", ".join(TYPE_LABELS[k] for k in report.intervention_types)),
    ]
    if "other" in report.intervention_types:
        info.append(("Other intervention details", report.other_intervention_detail))
    if locale_labels is not None:
        if not isinstance(locale_labels, dict):
            raise ExportError("Metadata localization must be a prevalidated mapping")
        from .v2.metadata_locale import ENGLISH_LABELS
        # The caller must provide *all* required labels. Never fall back to
        # English if a validated language context is incomplete.
        def localized(key):
            if key not in locale_labels or not isinstance(locale_labels[key], str):
                raise ExportError("Untranslated report metadata label: " + key)
            return locale_labels[key]
        renamed = []
        field_keys = {
            "Created": "field.created",
            "Intervention from": "field.intervention_from",
            "Intervention to": "field.intervention_to",
            "Customer": "field.customer", "Site": "field.site",
            "Machine": "field.machine", "Machine serial": "field.machine_serial",
            "Ticket": "field.ticket", "Personnel": "field.personnel",
            "Intervention types": "field.intervention_types",
            "Other intervention details": "field.other_intervention_details",
        }
        for label, value in info:
            if not value:
                continue
            key = field_keys[label]
            if key == "field.intervention_types":
                value = ", ".join(localized("intervention." + kind)
                                  for kind in report.intervention_types)
            elif key == "field.other_intervention_details":
                value = localized("metadata.other_intervention_detail")
            renamed.append((localized(key), value))
        info = renamed
        for key in ("heading.report_information", "heading.summary", "label.page"):
            localized(key)
    items: list[RenderItem] = []

    def add_module(module: Module) -> None:
        entry = entries[module.id]
        title = ((entry.number + " ") if entry.number else "") + entry.title
        items.append(RenderItem("module", title, entry.depth, module.id))
        for block in module.blocks:
            if isinstance(block, NestedModuleBlock):
                add_module(block.module)
            elif isinstance(block, ParagraphBlock):
                items.append(RenderItem("paragraph", block.text.original, rich=block.rich))
            elif isinstance(block, HeadingBlock):
                items.append(RenderItem("heading", block.text.original, block.level, rich=block.rich))
            elif isinstance(block, TableBlock):
                items.append(RenderItem(
                    "table", rows=tuple(tuple(cell.original for cell in row)
                                        for row in block.rows)))
            elif isinstance(block, PhotoBlock):
                # The pure exporter never interprets Qt annotation layers.
                # A caller must supply an explicit reviewed renderer; V1's
                # original fail-closed behavior remains the default.
                if block.asset_id not in project.assets:
                    raise ExportError("Referenced photograph is missing: " + block.asset_id)
                source = project.assets[block.asset_id]
                if block.visual != PhotoVisual():
                    if visual_renderer is None:
                        raise ExportError("Edited photographs cannot be exported until "
                                          "M4.5.4 annotated DOCX/PDF support is implemented "
                                          "(or an approved V2 renderer is supplied)")
                    try:
                        source = visual_renderer(source, block.visual)
                    except (ValueError, RuntimeError, OSError) as exc:
                        raise ExportError("Cannot render edited photograph") from exc
                items.append(RenderItem(
                    "photo", block.caption.original if block.caption else "",
                    image=_image_bytes(source),
                    photo_width_pct=(block.visual.width_pct
                                     if visual_renderer is not None else 100),
                    photo_alignment=(block.visual.alignment
                                     if visual_renderer is not None else "default")))
            elif isinstance(block, PageBreakBlock):
                items.append(RenderItem("page_break"))
            else:
                raise ExportError("Unsupported content block")
    for module in report.ordered_sections():
        add_module(module)
    return ExportPlan(report.title.original, tuple(
        (label, value) for label, value in info if value
    ), outline, tuple(items), locale_labels)


@contextmanager
def _atomic_destination(destination: str | Path, extension: str):
    """Write to same-directory temp and replace only after successful build."""
    path = Path(destination)
    if path.suffix.lower() != extension:
        raise ExportError("Expected a " + extension + " filename")
    if not path.parent.is_dir():
        raise ExportError("Export destination directory does not exist")
    fd, name = tempfile.mkstemp(prefix=".reportmaker-export-", suffix=extension, dir=path.parent)
    os.close(fd)
    temp = Path(name)
    try:
        yield temp
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _word_field(paragraph, expression: str, placeholder: str = "?") -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def element(tag, value=None):
        result = OxmlElement(tag)
        if value is not None:
            result.text = value
        return result

    start = paragraph.add_run()
    begin = element("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    start._r.append(begin)
    code = paragraph.add_run()
    instruction = element("w:instrText", expression)
    instruction.set(qn("xml:space"), "preserve")
    code._r.append(instruction)
    separate = element("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    paragraph.add_run()._r.append(separate)
    paragraph.add_run(placeholder)
    end = element("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    paragraph.add_run()._r.append(end)


def _bookmark_key(module_id: str) -> str:
    return "rm_" + sha256(module_id.encode("utf-8")).hexdigest()[:30]


def _word_bookmark(paragraph, module_id: str, number: int) -> str:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    # Word bookmark keys are safe for arbitrary valid report IDs, with unique
    # numeric bookmark identifiers independent of any caller-supplied ID text.
    key = _bookmark_key(module_id)
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(number))
    start.set(qn("w:name"), key)
    # w:pPr must remain the first child of a Word paragraph.
    paragraph._p.insert(1 if paragraph._p.pPr is not None else 0, start)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), start.get(qn("w:id")))
    paragraph._p.append(end)
    return key


def _rich_lines(value: str, rich: RichFormatting | None):
    rich = rich if rich is not None else RichFormatting()
    validate_rich(rich, value)
    by_start = {item.start: item for item in rich.paragraphs}
    start = 0
    for line in value.split("\n"):
        right = start + len(line)
        boundaries = {start, right}
        for r in rich.runs:
            if r.start < right and r.end > start:
                boundaries.add(max(start, r.start))
                boundaries.add(min(right, r.end))
        sorted_edges = sorted(boundaries)
        parts = [(value[left:end], style_at(rich, left))
                 for left, end in zip(sorted_edges, sorted_edges[1:])]
        yield parts, by_start.get(start, ParagraphStyle(start))
        start = right + 1


def _rich_pdf_markup(parts, fallback_bold=False):
    result = []
    for value, rich in parts:
        content = escape(value)
        if rich:
            if rich.bold or fallback_bold:
                content = "<b>" + content + "</b>"
            if rich.italic:
                content = "<i>" + content + "</i>"
            if rich.underline:
                content = "<u>" + content + "</u>"
            if rich.strike:
                content = "<strike>" + content + "</strike>"
            if rich.baseline != "normal":
                content = "<" + rich.baseline + ">" + content + "</" + rich.baseline + ">"
            attrs = []
            if rich.color:
                attrs.append('color="' + rich.color + '"')
            if rich.size:
                attrs.append('size="' + str(rich.size) + '"')
            if attrs:
                content = "<font " + " ".join(attrs) + ">" + content + "</font>"
            if rich.highlight:
                # ReportLab Paragraph has no standard arbitrary background color
                # per inline run. Emphasize highlighted text with a visible box.
                content = '<font backcolor="' + rich.highlight + '">' + content + "</font>"
        elif fallback_bold:
            content = "<b>" + content + "</b>"
        result.append(content)
    return "".join(result)


def _rich_leading(parts, style: ExportStyle, *, heading_depth: int | None = None) -> float:
    """One explicit line pitch for editable Word and locally paginated PDF.

    Large custom run sizes must not be clipped by a base Normal-style leading.
    Word and ReportLab use points for this same supported paragraph metric;
    installed font substitution and Word's own pagination may still differ.
    """
    base = (max(10.0, style.heading_size_pt - heading_depth)
            if heading_depth is not None else style.normal_size_pt)
    return max((base, *(run.size for _, run in parts
                        if run is not None and run.size)), default=base) * 1.4


class _WordListNumbering:
    """Explicit Word numbering for canonical list sequences and restart points.

    Each switch of list type/indent, non-list paragraph or structural block
    starts a new numbering instance; adjacent text blocks can continue one.
    Never rely on an installed Word List Number/List Bullet style to decide
    whether an alphabetic list starts at a, A or 1.
    """
    _FORMATS = {
        "bullet": ("bullet", "•"),
        "decimal": ("decimal", "%1."),
        "lower-alpha": ("lowerLetter", "%1."),
        "upper-alpha": ("upperLetter", "%1."),
    }

    def __init__(self, document):
        self._root = document.part.numbering_part.element
        self._abstract = {}
        self._last_key = None
        self._active_num = None

    def reset(self):
        self._last_key = None
        self._active_num = None

    def _abstract_id(self, kind: str) -> int:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        if kind in self._abstract:
            return self._abstract[kind]
        if kind not in self._FORMATS:
            raise ExportError("Unsupported Word list numbering format")
        existing = self._root.xpath("./w:abstractNum")
        number = max((int(item.get(qn("w:abstractNumId")))
                      for item in existing), default=-1) + 1
        abstract = OxmlElement("w:abstractNum")
        abstract.set(qn("w:abstractNumId"), str(number))
        level = OxmlElement("w:lvl")
        level.set(qn("w:ilvl"), "0")
        for tag, value in (
            ("w:start", "1"),
            ("w:numFmt", self._FORMATS[kind][0]),
            ("w:lvlText", self._FORMATS[kind][1]),
            ("w:lvlJc", "left"),
        ):
            element = OxmlElement(tag)
            element.set(qn("w:val"), value)
            level.append(element)
        abstract.append(level)
        # The numbering part schema places abstractNum before num entries.
        nums = self._root.xpath("./w:num")
        if nums:
            self._root.insert(self._root.index(nums[0]), abstract)
        else:
            self._root.append(abstract)
        self._abstract[kind] = number
        return number

    def assign(self, paragraph, kind: str, indent: int):
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        key = (kind, indent)
        if self._last_key != key:
            entry = self._root.add_num(self._abstract_id(kind))
            self._active_num = int(entry.get(qn("w:numId")))
            self._last_key = key
        props = paragraph._p.get_or_add_pPr()
        numpr = OxmlElement("w:numPr")
        for tag, number in (("w:ilvl", 0), ("w:numId", self._active_num)):
            element = OxmlElement(tag)
            element.set(qn("w:val"), str(number))
            numpr.append(element)
        props.append(numpr)


def _pdf_number_marker(kind: str, ordinal: int) -> str:
    """Visible numbering for canonical PDF list paragraphs (one-based)."""
    if kind == "decimal":
        return f"{ordinal}. "
    if kind not in ("lower-alpha", "upper-alpha") or ordinal < 1:
        raise ValueError("Invalid PDF list number")
    label = ""
    while ordinal:
        ordinal, digit = divmod(ordinal - 1, 26)
        label = chr(ord("a") + digit) + label
    return (label.upper() if kind == "upper-alpha" else label) + ". "


def _word_font_family(font, family: str) -> None:
    """Apply an explicit font to Word's Latin, East Asian and complex scripts.

    python-docx Font.name alone writes ascii/hAnsi; Word then guesses the
    East Asian and complex-script face even when users chose one explicitly.
    Installed glyph coverage and substitution still require native acceptance.
    """
    from docx.oxml.ns import qn

    if not family:
        return
    font.name = family
    fonts = font._element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn("w:eastAsia"), family)
    fonts.set(qn("w:cs"), family)


def _word_fixed_table(table, widths_cm: tuple[float, ...]) -> None:
    """Set *both* Word table grid and cell widths to the printable area.

    python-docx's default autofit lets Word expand a table beyond the
    selected template margins, unlike the explicitly sized PDF tables.
    This keeps OOXML editable and deterministic across supported layouts.
    """
    from docx.shared import Cm
    from docx.oxml.ns import qn

    if len(widths_cm) != len(table.columns) or any(w <= 0 for w in widths_cm):
        raise ExportError("Invalid printable Word table widths")
    table.autofit = False
    for col, width in zip(table.columns, widths_cm):
        col.width = Cm(width)
    for row in table.rows:
        for cell, width in zip(row.cells, widths_cm):
            cell.width = Cm(width)
    table_width = table._tbl.tblPr.xpath("./w:tblW")
    if len(table_width) != 1:
        raise ExportError("Word table width definition is missing")
    table_width[0].set(qn("w:type"), "dxa")
    table_width[0].set(qn("w:w"), str(Cm(sum(widths_cm)).twips))


def _write_docx(plan: ExportPlan, destination: Path, style: ExportStyle) -> None:
    from docx import Document
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Cm, Pt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    document = Document()
    sec = document.sections[0]
    sec.page_width, sec.page_height = Cm(style.page_width_cm), Cm(style.page_height_cm)
    sec.left_margin, sec.right_margin = Cm(style.left_margin_cm), Cm(style.right_margin_cm)
    sec.top_margin, sec.bottom_margin = Cm(style.top_margin_cm), Cm(style.bottom_margin_cm)
    sec.header_distance = Cm(style.header_distance_cm)
    sec.footer_distance = Cm(style.footer_distance_cm)
    normal = document.styles["Normal"]
    _word_font_family(normal.font, style.normal_font)
    normal.font.size = Pt(style.normal_size_pt)
    # Nested module headings use Heading 1..9. A Word layout profile must
    # govern every supported depth, not merely Heading 1 while descendants
    # silently fall back to machine/default Word styles.
    for level in range(1, 10):
        heading_style = document.styles["Heading " + str(level)]
        _word_font_family(heading_style.font, style.heading_font)
        heading_style.font.size = Pt(max(10, style.heading_size_pt - (level - 1)))
    printable_width = style.page_width_cm - style.left_margin_cm - style.right_margin_cm
    # Repeated Word header/footer, with a live PAGE field.
    if style.company_name or style.logo:
        header = sec.header.paragraphs[0]
        if style.logo:
            logo_w, logo_h = _logo_dimensions(style.logo)
            header.add_run().add_picture(BytesIO(style.logo),
                                         width=Cm(logo_w), height=Cm(logo_h))
            header.add_run("  ")
        header.add_run(style.company_name).bold = True
    footer = sec.footer.paragraphs[0]
    footer.paragraph_format.tab_stops.add_tab_stop(
        Cm(printable_width), WD_TAB_ALIGNMENT.RIGHT)
    labels = plan.locale_labels or {}
    footer.add_run(labels.get("branding.footer_note", style.footer_note))
    footer.add_run("\t" + labels.get("label.page", "Page") + " ")
    _word_field(footer, " PAGE ", "1")
    document.core_properties.title = plan.title
    document.add_heading(plan.title, 0)
    document.add_heading((plan.locale_labels or {}).get(
        "heading.report_information", "Report information"), level=2)
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in plan.info:
        row = table.add_row().cells
        row[0].text, row[1].text = label, value
    info_label_width = min(4.2, printable_width * .28)
    _word_fixed_table(table, (info_label_width, printable_width - info_label_width))
    document.add_heading((plan.locale_labels or {}).get(
        "heading.summary", "Summary"), level=2)
    for entry in plan.outline:
        paragraph = document.add_paragraph(style="Normal")
        paragraph.paragraph_format.left_indent = Cm(min(entry.depth, 12) * .5)
        paragraph.paragraph_format.tab_stops.add_tab_stop(
            Cm(max(3, printable_width - .6)), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        paragraph.add_run(((entry.number + " ") if entry.number else "") + entry.title)
        paragraph.add_run("\t")
        key = _bookmark_key(entry.module_id)
        _word_field(paragraph, " PAGEREF " + key + " \\h ", "?")
    # Ask Word to resolve page references after its own final pagination.
    setting = OxmlElement("w:updateFields")
    setting.set(qn("w:val"), "true")
    document.settings.element.append(setting)
    document.add_page_break()

    entry_map = {e.module_id: e for e in plan.outline}
    bookmark_numbers = {entry.module_id: i for i, entry in enumerate(plan.outline, 1)}
    numbering = _WordListNumbering(document)
    for item in plan.items:
        if item.kind not in ("paragraph", "heading"):
            numbering.reset()
        if item.kind == "module":
            entry = entry_map[item.key]
            paragraph = document.add_heading(item.text, level=min(entry.depth + 1, 9))
            paragraph.paragraph_format.keep_with_next = True
            if entry.depth >= 9:
                paragraph.paragraph_format.left_indent = Cm(min(entry.depth, 12) * .4)
            _word_bookmark(paragraph, item.key, bookmark_numbers[item.key])
        elif item.kind in ("paragraph", "heading"):
            from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
            from docx.shared import RGBColor
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
            for parts, fmt in _rich_lines(item.text, item.rich):
                p = document.add_paragraph(style="Normal")
                if fmt.list_kind == "none":
                    numbering.reset()
                else:
                    numbering.assign(p, fmt.list_kind, fmt.indent)
                p.alignment = {
                    "left": WD_ALIGN_PARAGRAPH.LEFT,
                    "right": WD_ALIGN_PARAGRAPH.RIGHT,
                    "center": WD_ALIGN_PARAGRAPH.CENTER,
                    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
                }[fmt.align]
                p.paragraph_format.left_indent = Cm(
                    fmt.indent * 0.6 + (0.6 if fmt.list_kind != "none" else 0))
                if fmt.list_kind != "none":
                    p.paragraph_format.first_line_indent = Cm(-0.42)
                p.paragraph_format.line_spacing = Pt(
                    _rich_leading(parts, style, heading_depth=item.depth
                                  if item.kind == "heading" else None) * fmt.line_height)
                if item.kind == "heading":
                    p.paragraph_format.keep_with_next = True
                if fmt.shading:
                    shade = OxmlElement("w:shd")
                    shade.set(qn("w:fill"), fmt.shading.lstrip("#"))
                    p._p.get_or_add_pPr().append(shade)
                if fmt.border:
                    border = OxmlElement("w:pBdr")
                    edge = OxmlElement("w:bottom")
                    edge.set(qn("w:val"), "single")
                    edge.set(qn("w:sz"), "6")
                    border.append(edge)
                    p._p.get_or_add_pPr().append(border)
                for part, info in parts:
                    run = p.add_run(part)
                    if item.kind == "heading":
                        run.bold = True
                        run.font.size = Pt(max(10, style.heading_size_pt - item.depth))
                        _word_font_family(run.font, style.heading_font)
                    if info is not None:
                        _word_font_family(run.font, info.family)
                        if info.size:
                            run.font.size = Pt(info.size)
                        run.bold = info.bold or item.kind == "heading"
                        run.italic = info.italic
                        run.underline = info.underline
                        run.font.strike = info.strike
                        run.font.superscript = info.baseline == "super"
                        run.font.subscript = info.baseline == "sub"
                        if info.color:
                            run.font.color.rgb = RGBColor.from_string(info.color[1:])
                        if info.highlight:
                            shading = OxmlElement("w:shd")
                            shading.set(qn("w:fill"), info.highlight[1:])
                            run._r.get_or_add_rPr().append(shading)
        elif item.kind == "table":
            if not item.rows:
                continue
            width = max((len(row) for row in item.rows), default=0)
            if width < 1:
                continue
            table = document.add_table(rows=len(item.rows), cols=width)
            table.style = "Table Grid"
            for i, row in enumerate(item.rows):
                for j, value in enumerate(row):
                    table.cell(i, j).text = value
            _word_fixed_table(table, (printable_width / width,) * width)
        elif item.kind == "photo":
            photo_w, photo_h = _photo_dimensions(
                item.image, max_width_cm=min(
                    PHOTO_MAX_WIDTH_CM,
                    style.page_width_cm - style.left_margin_cm - style.right_margin_cm - 1),
                max_height_cm=min(
                    PHOTO_MAX_HEIGHT_CM,
                    style.page_height_cm - style.top_margin_cm - style.bottom_margin_cm - 1))
            picture = document.add_paragraph()
            if item.photo_alignment != "default":
                from docx.enum.text import WD_ALIGN_PARAGRAPH
                picture.alignment = {
                    "left": WD_ALIGN_PARAGRAPH.LEFT,
                    "center": WD_ALIGN_PARAGRAPH.CENTER,
                    "right": WD_ALIGN_PARAGRAPH.RIGHT,
                }[item.photo_alignment]
            photo_w *= item.photo_width_pct / 100
            photo_h *= item.photo_width_pct / 100
            picture.paragraph_format.keep_together = True
            picture.paragraph_format.keep_with_next = bool(item.text)
            picture.add_run().add_picture(BytesIO(item.image),
                                          width=Cm(photo_w), height=Cm(photo_h))
            if item.text:
                caption = document.add_paragraph(item.text, style="Caption")
                caption.paragraph_format.keep_together = True
        elif item.kind == "page_break":
            document.add_page_break()
        else:
            raise ExportError("Unsupported document item")
    document.save(destination)


def _write_pdf(plan: ExportPlan, destination: Path, style: ExportStyle) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, Image, KeepTogether, PageBreak,
        PageTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont, TTFError
    from reportlab.lib.utils import ImageReader

    body_font, bold_font = "Helvetica", "Helvetica-Bold"
    # Embed a local system Unicode font where present. No font/user data is
    # uploaded, and unsupported language-specific typography belongs to M5.
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [
        (windows_fonts / "segoeui.ttf", windows_fonts / "segoeuib.ttf"),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
         Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            try:
                pdfmetrics.registerFont(TTFont("RM-Body", str(regular)))
                pdfmetrics.registerFont(TTFont("RM-Bold", str(bold)))
                body_font, bold_font = "RM-Body", "RM-Bold"
                break
            except (ValueError, OSError, TTFError):
                continue

    # Resolve the complete page decoration before ReportLab's onPage callback.
    # Raising there wraps a helpful ExportError as "handle_pageBegin args=()".
    # Header distance is measured from the top edge, while the top margin is
    # the start of body content; the logo must fit between the two.
    header_room_cm = style.top_margin_cm - style.header_distance_cm - .2
    if (style.logo or style.company_name) and header_room_cm <= 1e-6:
        raise ExportError("PDF header has no space above the report body; "
                          "increase the top margin or reduce the header distance")
    header_top_y = (style.page_height_cm - style.header_distance_cm - .2)*cm
    header_text_x = style.left_margin_cm*cm
    logo_w = logo_h = 0.0
    logo_image = None
    if style.logo:
        # Keep the existing maximum logo dimensions, but scale down further
        # for a tight imported template instead of aborting mid-export.
        logo_w, logo_h = _logo_dimensions(style.logo, max_height_cm=header_room_cm)
        logo_image = ImageReader(BytesIO(style.logo))
        header_text_x += (logo_w + .25)*cm

    header = None
    header_height = 0.0
    if style.company_name:
        header_style = ParagraphStyle("RMHeader", fontName=bold_font,
                                      fontSize=9, leading=11)
        markup = escape(style.company_name).replace("\t", "&#160;" * 4).replace("\n", "<br/>")
        header = Paragraph(markup, header_style)
        available_width = (style.page_width_cm - style.right_margin_cm)*cm - header_text_x
        if available_width <= 0:
            raise ExportError("PDF header text has no space beside the logo; "
                              "increase page width or reduce side margins")
        _, header_height = header.wrap(available_width, header_room_cm*cm)
        if header_height > header_room_cm*cm:
            raise ExportError("Header text does not fit the PDF top margin; "
                              "increase the top margin or shorten the header")

    footer = None
    footer_note = (plan.locale_labels or {}).get("branding.footer_note", style.footer_note)
    if footer_note:
        footer_style = ParagraphStyle("RMFooter", fontName=body_font,
                                      fontSize=8, leading=10)
        markup = escape(footer_note).replace("\t", "&#160;" * 4).replace("\n", "<br/>")
        footer = Paragraph(markup, footer_style)
        note_width = max(2*cm, (style.page_width_cm-style.left_margin_cm-
                                style.right_margin_cm-3)*cm)
        allowed_height = (style.bottom_margin_cm-style.footer_distance_cm-.15)*cm
        _, footer_height = footer.wrap(note_width, max(0, allowed_height))
        if allowed_height <= 0 or footer_height > allowed_height:
            raise ExportError("Footer text does not fit the PDF bottom margin; "
                              "increase the bottom margin or shorten the footer")

    class ReportPDF(BaseDocTemplate):
        def __init__(self, path):
            super().__init__(str(path),
                             pagesize=(style.page_width_cm*cm, style.page_height_cm*cm),
                             leftMargin=style.left_margin_cm*cm,
                             rightMargin=style.right_margin_cm*cm,
                             topMargin=style.top_margin_cm*cm,
                             bottomMargin=style.bottom_margin_cm*cm, title=plan.title)
            frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height,
                          leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
            self.addPageTemplates(PageTemplate(id="report", frames=[frame],
                                               onPage=self.page_decoration))

        def page_decoration(self, canvas, doc):
            canvas.saveState()
            try:
                if logo_image is not None:
                    canvas.drawImage(logo_image, style.left_margin_cm*cm,
                                     header_top_y - logo_h*cm,
                                     width=logo_w*cm, height=logo_h*cm,
                                     mask="auto")
                if header is not None:
                    header.drawOn(canvas, header_text_x,
                                  header_top_y - header_height)
                if footer is not None:
                    footer.drawOn(canvas, style.left_margin_cm*cm,
                                  style.footer_distance_cm*cm)
                canvas.setFont(body_font, 9)
                canvas.drawRightString((style.page_width_cm-style.right_margin_cm)*cm,
                                       style.footer_distance_cm*cm,
                                       (plan.locale_labels or {}).get(
                                           "label.page", "Page") + " " + str(doc.page))
            finally:
                canvas.restoreState()

        def afterFlowable(self, flowable):
            entry = getattr(flowable, "_rm_entry", None)
            if entry is None:
                return
            level, label, key = entry
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(label, key, level=min(level, 8), closed=False)
            # ReportLab treats TOC labels as Paragraph markup: preserve literal
            # angle brackets and ampersands rather than silently dropping text.
            self.notify("TOCEntry", (min(level, 8), escape(label), self.page, key))

    styles = getSampleStyleSheet()
    normal = styles["BodyText"]
    normal.fontName = body_font
    normal.fontSize = style.normal_size_pt
    normal.leading = style.normal_size_pt * 1.4
    heading_styles = [
        ParagraphStyle("ReportSection" + str(i), parent=normal,
                       fontName=bold_font, fontSize=max(10, style.heading_size_pt-i),
                       leading=max(15, 20-i), spaceBefore=13, spaceAfter=6,
                       keepWithNext=1, leftIndent=min(i, 12)*.35*cm)
        for i in range(9)
    ]
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC" + str(i), parent=normal, leftIndent=i * .4*cm,
                       firstLineIndent=0, fontName=body_font, fontSize=9,
                       leading=12, alignment=TA_LEFT)
        for i in range(9)
    ]
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName=bold_font)
    label_style = ParagraphStyle("ReportLabel", parent=styles["Heading2"], fontName=bold_font)
    story = [Paragraph(escape(plan.title), title_style),
             Spacer(1, 10), Paragraph(escape((plan.locale_labels or {}).get(
                 "heading.report_information", "Report information")), label_style)]
    # Use the same selected/embedded Unicode font as report body content.
    # Default BodyText is Helvetica and corrupts non-Latin customer metadata.
    metadata = [[Paragraph(escape(label), normal),
                 Paragraph(escape(value).replace("\n", "<br/>"), normal)]
                for label, value in plan.info]
    if metadata:
        printable = style.page_width_cm - style.left_margin_cm - style.right_margin_cm
        label_width = min(4.2, printable * .28)
        tbl = Table(metadata, colWidths=[label_width*cm, (printable-label_width)*cm], hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), .3, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.extend([tbl, Spacer(1, 12)])
    story.extend([Paragraph(escape((plan.locale_labels or {}).get(
        "heading.summary", "Summary")), label_style), toc, PageBreak()])

    # Continue a list over adjacent canonical text blocks, but never across a
    # module/table/photo/page break or a plain/bulleted paragraph.
    numbering_key = None
    ordinal = 0
    for item in plan.items:
        if item.kind not in ("paragraph", "heading"):
            numbering_key = None
            ordinal = 0
        if item.kind == "module":
            label = escape(item.text)
            level = min(item.depth, 8)
            paragraph = Paragraph(label, heading_styles[level])
            paragraph._rm_entry = (level, item.text, _bookmark_key(item.key))
            story.append(paragraph)
        elif item.kind in ("paragraph", "heading"):
            from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
            from reportlab.lib.styles import ParagraphStyle
            for index, (parts, fmt) in enumerate(_rich_lines(item.text, item.rich)):
                key = ((fmt.list_kind, fmt.indent) if fmt.list_kind in
                       ("decimal", "lower-alpha", "upper-alpha") else None)
                if key is None:
                    ordinal = 0
                else:
                    ordinal = ordinal + 1 if key == numbering_key else 1
                numbering_key = key
                base = (heading_styles[min(max(item.depth, 1), 8)]
                        if item.kind == "heading" else normal)
                pstyle = ParagraphStyle("Rich-%s-%d-%d" % (item.kind, len(story), index),
                    parent=base, alignment={
                        "left": TA_LEFT, "center": TA_CENTER,
                        "right": TA_RIGHT, "justify": TA_JUSTIFY,
                    }[fmt.align], leftIndent=base.leftIndent + fmt.indent * 15,
                    leading=_rich_leading(parts, style, heading_depth=item.depth
                                          if item.kind == "heading" else None) * fmt.line_height,
                    backColor=fmt.shading or None,
                    borderWidth=0.75 if fmt.border else 0,
                    borderColor=colors.HexColor("#777777") if fmt.border else None,
                    borderPadding=3 if fmt.border else 0)
                if fmt.list_kind == "bullet":
                    marker = "&#8226; "
                elif key is not None:
                    marker = _pdf_number_marker(fmt.list_kind, ordinal)
                else:
                    marker = ""
                story.append(Paragraph(marker +
                    _rich_pdf_markup(parts, item.kind == "heading") or " ",
                    pstyle))
        elif item.kind == "table":
            width = max((len(row) for row in item.rows), default=0)
            if not item.rows or width == 0:
                continue
            printable = style.page_width_cm - style.left_margin_cm - style.right_margin_cm
            col_width = (printable*cm) / width
            rows = [[Paragraph(escape(value).replace("\n", "<br/>"), normal)
                     for value in tuple(row) + ("",)*(width-len(row))]
                    for row in item.rows]
            tbl = Table(rows, colWidths=[col_width]*width, hAlign="LEFT")
            tbl.setStyle(TableStyle([
                ("GRID", (0,0), (-1,-1), .35, colors.grey),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING", (0,0), (-1,-1), 4),
                ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ]))
            story.extend([tbl, Spacer(1, 8)])
        elif item.kind == "photo":
            photo_w, photo_h = _photo_dimensions(
                item.image, max_width_cm=min(
                    PHOTO_MAX_WIDTH_CM,
                    style.page_width_cm - style.left_margin_cm - style.right_margin_cm - 1),
                max_height_cm=min(
                    PHOTO_MAX_HEIGHT_CM,
                    style.page_height_cm - style.top_margin_cm - style.bottom_margin_cm - 1))
            photo_w *= item.photo_width_pct / 100
            photo_h *= item.photo_width_pct / 100
            image = Image(BytesIO(item.image), width=photo_w*cm,
                          height=photo_h*cm)
            if item.photo_alignment != "default":
                image.hAlign = item.photo_alignment.upper()
            if item.text:
                story.append(KeepTogether([image, Paragraph(escape(item.text),
                                                           normal)]))
            else:
                story.append(image)
        elif item.kind == "page_break":
            story.append(PageBreak())
        else:
            raise ExportError("Unsupported PDF item")
    from reportlab.platypus.doctemplate import LayoutError
    try:
        ReportPDF(destination).multiBuild(story, maxPasses=8)
    except LayoutError as exc:
        # A very tall table row / non-splittable object is normal invalid
        # printable content, not a reason to leave the desktop export silent.
        raise ExportError("PDF content does not fit on a page; shorten or split the oversized table cell or image") from exc


def export_project(project: ReportProject, destination: str | Path,
                   *, format: str, style: ExportStyle | None = None,
                   visual_renderer: Callable[[bytes, PhotoVisual], bytes] | None = None,
                   locale_labels: dict[str, str] | None = None) -> Path:
    """Create DOCX or PDF atomically; caller owns the source project's Save."""
    if format not in {"docx", "pdf"}:
        raise ExportError("Unsupported export format")
    # Validate and decode all assets and branding before replacing any output.
    plan = prepare_export(project, visual_renderer=visual_renderer,
                          locale_labels=locale_labels)
    style = _validate_style(style)
    destination = Path(destination)
    with _atomic_destination(destination, "." + format) as temporary:
        if format == "docx":
            _write_docx(plan, temporary, style)
        else:
            _write_pdf(plan, temporary, style)
    return destination
