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


def _validate_style(style: ExportStyle | None) -> ExportStyle:
    if style is None:
        return ExportStyle()
    if not isinstance(style, ExportStyle):
        raise ExportError("Invalid export branding configuration")
    for value, label, limit in ((style.company_name, "Company name", 80),
                                (style.footer_note, "Footer note", 120)):
        if (not isinstance(value, str) or len(value) > limit or
            any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ExportError(label + " contains unsupported characters or is too long")
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
            normal_font=style.normal_font, normal_size_pt=style.normal_size_pt, logo=style.logo))
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
                       style.normal_font, style.normal_size_pt)


def _photo_dimensions(image: bytes, max_width_cm: float = PHOTO_MAX_WIDTH_CM,
                      max_height_cm: float = PHOTO_MAX_HEIGHT_CM) -> tuple[float, float]:
    """Natural 96-dpi size, never larger than the selected printable page."""
    from PIL import Image
    with Image.open(BytesIO(image)) as im:
        width, height = im.size
    scale = min(2.54 / 96.0, max_width_cm / width,
                max_height_cm / height)
    return width * scale, height * scale


def _logo_dimensions(image: bytes) -> tuple[float, float]:
    from PIL import Image
    with Image.open(BytesIO(image)) as im:
        width, height = im.size
    scale = min(2.54 / 96.0, 2.6 / width, 1.05 / height)
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


@dataclass(frozen=True)
class ExportPlan:
    title: str
    info: tuple[tuple[str, str], ...]
    outline: tuple[OutlineEntry, ...]
    items: tuple[RenderItem, ...]


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


def prepare_export(project: ReportProject) -> ExportPlan:
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
                # M4.5.4 will render visual layers consistently to DOCX/PDF.
                # Never silently export the unedited original in their place.
                if block.visual != PhotoVisual():
                    raise ExportError("Edited photographs cannot be exported until "
                                      "M4.5.4 annotated DOCX/PDF support is implemented")
                if block.asset_id not in project.assets:
                    raise ExportError("Referenced photograph is missing: " + block.asset_id)
                items.append(RenderItem(
                    "photo", block.caption.original if block.caption else "",
                    image=_image_bytes(project.assets[block.asset_id])))
            elif isinstance(block, PageBreakBlock):
                items.append(RenderItem("page_break"))
            else:
                raise ExportError("Unsupported content block")
    for module in report.ordered_sections():
        add_module(module)
    return ExportPlan(report.title.original, tuple(
        (label, value) for label, value in info if value
    ), outline, tuple(items))


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
    if style.normal_font:
        normal.font.name = style.normal_font
    normal.font.size = Pt(style.normal_size_pt)
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
    footer.add_run(style.footer_note)
    footer.add_run("\tPage ")
    _word_field(footer, " PAGE ", "1")
    document.core_properties.title = plan.title
    document.add_heading(plan.title, 0)
    document.add_heading("Report information", level=2)
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in plan.info:
        row = table.add_row().cells
        row[0].text, row[1].text = label, value
    document.add_heading("Summary", level=2)
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
    for item in plan.items:
        if item.kind == "module":
            entry = entry_map[item.key]
            paragraph = document.add_heading(item.text, level=min(entry.depth + 1, 9))
            if entry.depth >= 9:
                paragraph.paragraph_format.left_indent = Cm(min(entry.depth, 12) * .4)
            _word_bookmark(paragraph, item.key, bookmark_numbers[item.key])
        elif item.kind in ("paragraph", "heading"):
            from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
            from docx.shared import RGBColor
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
            numbered = 0
            for parts, fmt in _rich_lines(item.text, item.rich):
                if fmt.list_kind == "decimal":
                    numbered += 1
                else:
                    numbered = 0
                style_name = ("List Bullet" if fmt.list_kind == "bullet" else
                              "List Number" if fmt.list_kind != "none" else None)
                p = document.add_paragraph(style=style_name)
                p.alignment = {
                    "left": WD_ALIGN_PARAGRAPH.LEFT,
                    "right": WD_ALIGN_PARAGRAPH.RIGHT,
                    "center": WD_ALIGN_PARAGRAPH.CENTER,
                    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
                }[fmt.align]
                p.paragraph_format.left_indent = Cm(fmt.indent * 0.6)
                p.paragraph_format.line_spacing = fmt.line_height
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
                        run.font.size = Pt(max(10, 16 - item.depth))
                    if info is not None:
                        if info.family:
                            run.font.name = info.family
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
        elif item.kind == "photo":
            photo_w, photo_h = _photo_dimensions(
                item.image, max_width_cm=min(
                    PHOTO_MAX_WIDTH_CM,
                    style.page_width_cm - style.left_margin_cm - style.right_margin_cm - 1),
                max_height_cm=min(
                    PHOTO_MAX_HEIGHT_CM,
                    style.page_height_cm - style.top_margin_cm - style.bottom_margin_cm - 1))
            picture = document.add_paragraph()
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
                text_x = style.left_margin_cm*cm
                if style.logo:
                    logo_w, logo_h = _logo_dimensions(style.logo)
                    canvas.drawImage(ImageReader(BytesIO(style.logo)),
                                     text_x, style.page_height_cm*cm - (style.header_distance_cm + .2)*cm - logo_h*cm,
                                     width=logo_w*cm, height=logo_h*cm,
                                     mask="auto")
                    text_x += (logo_w + .25)*cm
                if style.company_name:
                    header_style = ParagraphStyle(
                        "RMHeader", fontName=bold_font, fontSize=9, leading=11)
                    header = Paragraph(escape(style.company_name), header_style)
                    avail = style.page_width_cm*cm - style.right_margin_cm*cm - text_x
                    _, height = header.wrap(avail, 1.2*cm)
                    if height > 1.2*cm:
                        raise ExportError("Company name does not fit the PDF header")
                    header.drawOn(canvas, text_x, style.page_height_cm*cm - (style.header_distance_cm + .2)*cm - height)
                if style.footer_note:
                    note_style = ParagraphStyle(
                        "RMFooter", fontName=body_font, fontSize=8, leading=10)
                    note = Paragraph(escape(style.footer_note), note_style)
                    _, height = note.wrap(max(2*cm, (style.page_width_cm-style.left_margin_cm-style.right_margin_cm-3)*cm), .85*cm)
                    if height > .85*cm:
                        raise ExportError("Footer note does not fit the PDF footer")
                    note.drawOn(canvas, style.left_margin_cm*cm, style.footer_distance_cm*cm)
                canvas.setFont(body_font, 9)
                canvas.drawRightString((style.page_width_cm-style.right_margin_cm)*cm, style.footer_distance_cm*cm,
                                       "Page " + str(doc.page))
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
                       fontName=bold_font, fontSize=max(11, 16-i),
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
             Spacer(1, 10), Paragraph("Report information", label_style)]
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
    story.extend([Paragraph("Summary", label_style), toc, PageBreak()])

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
                    leading=base.leading * fmt.line_height,
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
            image = Image(BytesIO(item.image), width=photo_w*cm,
                          height=photo_h*cm)
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
                   *, format: str, style: ExportStyle | None = None) -> Path:
    """Create DOCX or PDF atomically; caller owns the source project's Save."""
    if format not in {"docx", "pdf"}:
        raise ExportError("Unsupported export format")
    # Validate and decode all assets and branding before replacing any output.
    plan = prepare_export(project)
    style = _validate_style(style)
    destination = Path(destination)
    with _atomic_destination(destination, "." + format) as temporary:
        if format == "docx":
            _write_docx(plan, temporary, style)
        else:
            _write_pdf(plan, temporary, style)
    return destination
