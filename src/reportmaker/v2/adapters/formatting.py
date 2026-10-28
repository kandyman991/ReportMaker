"""Selection-scoped rich formatting for V2, independent of Qt and document HTML.

All offsets in this module are Unicode *code point* indices. QTextCursor uses
UTF-16 units; adapters at the UI boundary must convert explicitly. A formatting
draft is not a report mutation until the guarded CommandGateway commit.
"""
from __future__ import annotations

from dataclasses import replace

from ...rich_text import (
    ALIGNMENTS, LIST_KINDS, ParagraphStyle, RichFormatting, TextRun,
    style_at, validate_rich,
)

CHAR_FIELDS = ("bold", "italic", "underline", "strike", "size")
PARA_FIELDS = ("align", "list_kind")


def to_codepoint(text: str, utf16_offset: int) -> int:
    if type(utf16_offset) is not int or utf16_offset < 0:
        raise ValueError("UTF-16 offset must be a non-negative integer")
    units = 0
    for i, char in enumerate(text):
        if units == utf16_offset:
            return i
        units += 2 if ord(char) > 0xFFFF else 1
        if units > utf16_offset:
            raise ValueError("Selection splits a UTF-16 surrogate pair")
    if units == utf16_offset:
        return len(text)
    raise ValueError("Selection is outside the text")


def to_utf16(text: str, index: int) -> int:
    if type(index) is not int or not 0 <= index <= len(text):
        raise ValueError("Invalid codepoint position")
    return len(text[:index].encode("utf-16-le")) // 2


def _bounds(text, start, end):
    if (type(start) is not int or type(end) is not int
            or not 0 <= start <= end <= len(text)):
        raise ValueError("Selection is outside canonical text")


def _run_has_style(run: TextRun) -> bool:
    return any((
        run.family, run.size, run.bold, run.italic, run.underline,
        run.strike, run.baseline != "normal", run.color, run.highlight,
    ))


def selection_uniform(text: str, rich: RichFormatting, start: int,
                      end: int, field: str) -> bool:
    """True only if *every* selected code point has the flag set."""
    validate_rich(rich, text)
    _bounds(text, start, end)
    if field not in ("bold", "italic", "underline", "strike") or start == end:
        return False
    cursor = start
    for run in rich.runs:
        if run.end <= cursor:
            continue
        if run.start > cursor:
            return False
        if not getattr(run, field):
            return False
        cursor = max(cursor, min(end, run.end))
        if cursor == end:
            return True
    return False


def format_chars(text: str, rich: RichFormatting, start: int, end: int,
                 field: str, value: object) -> RichFormatting:
    """Replace exactly one style field over a selection, preserving others."""
    validate_rich(rich, text)
    _bounds(text, start, end)
    if field not in CHAR_FIELDS:
        raise ValueError("Unsupported character format")
    if field == "size":
        if (type(value) not in (float, int) or not
                (value == 0 or 6 <= value <= 96)):
            raise ValueError("Font size must be 6–96 pt or default")
    elif type(value) is not bool:
        raise ValueError("Formatting flag must be a boolean")
    if start == end:
        raise ValueError("Select text before applying character formatting")
    boundaries = sorted({start, end} |
                        {edge for run in rich.runs for edge in (run.start, run.end)})
    spans = []
    for left, right in zip(boundaries, boundaries[1:]):
        if left == right:
            continue
        existing = style_at(rich, left)
        candidate = replace(existing, start=left, end=right) if existing else TextRun(left, right)
        if left >= start and right <= end:
            candidate = replace(candidate, **{field: value})
        if _run_has_style(candidate):
            if (spans and spans[-1].end == left
                    and replace(spans[-1], start=0, end=0)
                    == replace(candidate, start=0, end=0)):
                spans[-1] = replace(spans[-1], end=right)
            else:
                spans.append(candidate)
    result = RichFormatting(spans, list(rich.paragraphs))
    validate_rich(result, text)
    return result


def _paragraph_starts(text: str, start: int, end: int) -> list[int]:
    # A selection ending exactly on the next paragraph's first character must
    # not accidentally change that paragraph. Caret-only actions are allowed.
    end_character = end - 1 if end > start else start
    starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
    return [s for i, s in enumerate(starts)
            if s <= end_character and
            (starts[i + 1] if i + 1 < len(starts) else len(text) + 1) > start]


def format_paragraphs(text: str, rich: RichFormatting, start: int,
                      end: int, field: str, value: str) -> RichFormatting:
    validate_rich(rich, text)
    _bounds(text, start, end)
    if (field == "align" and value not in ALIGNMENTS or
            field == "list_kind" and value not in LIST_KINDS or
            field not in PARA_FIELDS):
        raise ValueError("Unsupported paragraph formatting")
    specs = {p.start: p for p in rich.paragraphs}
    for position in _paragraph_starts(text, start, end):
        current = specs.get(position, ParagraphStyle(position))
        changed = replace(current, **{field: value})
        if changed == ParagraphStyle(position):
            specs.pop(position, None)
        else:
            specs[position] = changed
    result = RichFormatting(list(rich.runs), sorted(specs.values(), key=lambda p: p.start))
    validate_rich(result, text)
    return result


def paragraph_uniform(text: str, rich: RichFormatting, start: int,
                      end: int, field: str, value: str) -> bool:
    """One active/checked state for the entire selected paragraph group."""
    validate_rich(rich, text)
    _bounds(text, start, end)
    if field not in PARA_FIELDS:
        raise ValueError("Unsupported paragraph format")
    specs = {p.start: p for p in rich.paragraphs}
    return all(getattr(specs.get(s, ParagraphStyle(s)), field) == value
               for s in _paragraph_starts(text, start, end))


def paragraph_value(text: str, rich: RichFormatting, caret: int, field: str) -> str:
    validate_rich(rich, text)
    _bounds(text, caret, caret)
    if field not in PARA_FIELDS:
        raise ValueError("Unsupported paragraph format")
    beginning = text.rfind("\n", 0, caret) + 1
    spec = next((x for x in rich.paragraphs if x.start == beginning),
                ParagraphStyle(beginning))
    return getattr(spec, field)
