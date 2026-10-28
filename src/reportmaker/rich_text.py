"""Pure, document-layout-independent inline and paragraph typography.

LocalizedText.original remains the *only* source of report wording. Formatting
ranges index Unicode code points in that source; no HTML, remote URL, font file,
or parallel text copy is stored in a portable project.
"""
from dataclasses import dataclass, field
from re import fullmatch
from math import isfinite

ALIGNMENTS = ("left", "center", "right", "justify")
LIST_KINDS = ("none", "bullet", "decimal", "lower-alpha", "upper-alpha")
BASELINES = ("normal", "super", "sub")
MAX_RUNS = 4096
MAX_PARAGRAPHS = 1024


@dataclass
class TextRun:
    start: int
    end: int
    family: str = ""
    size: float = 0.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    baseline: str = "normal"
    color: str = ""
    highlight: str = ""


@dataclass
class ParagraphStyle:
    start: int
    align: str = "left"
    indent: int = 0
    list_kind: str = "none"
    line_height: float = 1.0
    shading: str = ""
    border: bool = False


@dataclass
class RichFormatting:
    runs: list[TextRun] = field(default_factory=list)
    paragraphs: list[ParagraphStyle] = field(default_factory=list)


def _color(value):
    return isinstance(value, str) and (not value or fullmatch(r"#[0-9a-fA-F]{6}", value))


def validate_rich(value: RichFormatting, text: str):
    if not isinstance(value, RichFormatting) or not isinstance(text, str):
        raise ValueError("Invalid rich text record")
    if (not isinstance(value.runs, list) or len(value.runs) > MAX_RUNS
        or not isinstance(value.paragraphs, list) or len(value.paragraphs) > MAX_PARAGRAPHS):
        raise ValueError("Too many rich formatting records")
    prev = 0
    for item in value.runs:
        if (not isinstance(item, TextRun) or type(item.start) is not int
            or type(item.end) is not int or not 0 <= item.start < item.end <= len(text)
            or item.start < prev or not isinstance(item.family, str)
            or len(item.family) > 96 or (item.family and not fullmatch(r"[\w .\[\]-]{1,96}", item.family))
            or type(item.size) not in (float, int)
            or not isfinite(item.size) or (item.size != 0 and not 6 <= item.size <= 96)
            or any(type(getattr(item, k)) is not bool
                   for k in ("bold", "italic", "underline", "strike"))
            or item.baseline not in BASELINES
            or not _color(item.color) or not _color(item.highlight)):
            raise ValueError("Invalid text formatting range")
        prev = item.end
    paragraph_starts = {0}
    paragraph_starts.update(i + 1 for i, c in enumerate(text) if c == "\n")
    seen = set()
    for item in value.paragraphs:
        if (not isinstance(item, ParagraphStyle) or type(item.start) is not int
            or item.start not in paragraph_starts or item.start in seen
            or item.align not in ALIGNMENTS
            or type(item.indent) is not int or not 0 <= item.indent <= 12
            or item.list_kind not in LIST_KINDS
            or type(item.line_height) not in (int, float)
            or not isfinite(item.line_height) or not 1 <= item.line_height <= 3
            or not _color(item.shading) or type(item.border) is not bool):
            raise ValueError("Invalid paragraph formatting")
        seen.add(item.start)


def format_to_dict(value: RichFormatting, text: str) -> dict:
    validate_rich(value, text)
    return {
        "runs": [vars(run).copy() for run in value.runs],
        "paragraphs": [vars(para).copy() for para in value.paragraphs],
    }


def format_from_dict(raw: object, text: str) -> RichFormatting:
    def shape(record, names):
        if not isinstance(record, dict) or set(record) != set(names):
            raise ValueError("Unsupported rich formatting fields")
        return record
    obj = shape(raw, ("runs", "paragraphs"))
    if (not isinstance(obj["runs"], list) or len(obj["runs"]) > MAX_RUNS
        or not isinstance(obj["paragraphs"], list) or len(obj["paragraphs"]) > MAX_PARAGRAPHS):
        raise ValueError("Invalid rich formatting collection")
    out = RichFormatting(
        [TextRun(**shape(x, TextRun.__dataclass_fields__)) for x in obj["runs"]],
        [ParagraphStyle(**shape(x, ParagraphStyle.__dataclass_fields__))
         for x in obj["paragraphs"]],
    )
    validate_rich(out, text)
    return out


def style_at(value: RichFormatting, index: int) -> TextRun | None:
    return next((r for r in value.runs if r.start <= index < r.end), None)


def text_chunks(text: str, value: RichFormatting):
    """Split canonical wording at format boundaries, including multiline runs."""
    validate_rich(value, text)
    boundaries = {0, len(text)}
    for item in value.runs:
        boundaries.update((item.start, item.end))
    boundaries.update(i for i, x in enumerate(text) if x == "\n")
    boundaries.update(i + 1 for i, x in enumerate(text) if x == "\n")
    sorted_ends = sorted(boundaries)
    for left, right in zip(sorted_ends, sorted_ends[1:]):
        if left < right:
            yield text[left:right], style_at(value, left)


def safe_html(text: str, value: RichFormatting) -> str:
    """Escape source wording and emit allowlisted inline CSS for Qt preview."""
    from html import escape
    validate_rich(value, text)
    output = []
    para_by_start = {v.start: v for v in value.paragraphs}
    offset = 0
    for line in text.split("\n"):
        spec = para_by_start.get(offset, ParagraphStyle(offset))
        css = [f"text-align:{spec.align}", f"margin-left:{spec.indent*1.4}em",
               f"line-height:{spec.line_height*100:g}%"]
        if spec.shading:
            css.append("background-color:" + spec.shading)
        if spec.border:
            css.append("border:1px solid #777777")
        output.append('<p style="' + ";".join(css) + '">')
        line_end = offset + len(line)
        edges = {offset, line_end}
        for r in value.runs:
            if r.start < line_end and r.end > offset:
                edges.add(max(offset, r.start))
                edges.add(min(line_end, r.end))
        for start, end in zip(sorted(edges), sorted(edges)[1:]):
            run = style_at(value, start)
            part = escape(text[start:end])
            if run is None:
                output.append(part)
            else:
                styles = []
                if run.family:
                    styles.append("font-family:'" + escape(run.family, quote=True) + "'")
                if run.size:
                    styles.append(f"font-size:{run.size:g}pt")
                if run.bold:
                    styles.append("font-weight:bold")
                if run.italic:
                    styles.append("font-style:italic")
                decor = []
                if run.underline:
                    decor.append("underline")
                if run.strike:
                    decor.append("line-through")
                if decor:
                    styles.append("text-decoration:" + " ".join(decor))
                if run.color:
                    styles.append("color:" + run.color)
                if run.highlight:
                    styles.append("background-color:" + run.highlight)
                if run.baseline != "normal":
                    styles.append("vertical-align:" + run.baseline)
                output.append('<span style="' + ";".join(styles) + '">' + part + "</span>")
        output.append("</p>")
        offset = line_end + 1
    return "".join(output)
