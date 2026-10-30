"""Translate detached HTML field drafts into the existing canonical commands."""
from copy import deepcopy
from dataclasses import replace
from datetime import date

from ..model import HeadingBlock, ParagraphBlock, TableBlock
from ..reference import manual_snapshot
from ..rich_text import (
    ALIGNMENTS, BASELINES, LIST_KINDS, ParagraphStyle, RichFormatting,
    TextRun, style_at, validate_rich,
)
from .adapters.formatting import _paragraph_starts, _run_has_style, to_codepoint
from .adapters.rich_text import rebase_rich
from .adapters.tables import change_grid
from .commands import CommandIntent
from .projections import NodeAddress, find_node

EDIT_METHODS = frozenset({"rename_module", "update_paragraph", "update_heading",
                         "update_photo_caption", "update_table", "update_report_header"})


def field_intent(session, method, args, revision, generation):
    """No canonical mutation, coercion of invalid values, or translation recreation."""
    import json
    report = session.report_snapshot()
    if method not in EDIT_METHODS or not isinstance(args, list):
        raise ValueError("Unsupported HTML field edit")
    target = None
    if method == "update_report_header":
        raw, = args
        data = json.loads(raw)
        if not isinstance(data, dict) or any(not isinstance(v, str) for v in data.values()):
            raise ValueError("Report header fields must be text")
        snap = report.customer_snapshot
        names = {k: data.get(k, getattr(snap, k, "") if snap else "")
                 for k in ("customer_name", "site_name", "machine_name")}
        new_snap = replace(snap, **names) if snap is not None else manual_snapshot(**names)
        payload = dict(customer_id=report.customer_id if snap and snap.customer_id else None,
                       customer_snapshot=new_snap, created_date=report.created_date,
                       start_date=date.fromisoformat(data.get("start_date", report.start_date.isoformat())),
                       end_date=date.fromisoformat(data.get("end_date", report.end_date.isoformat())),
                       primary_language=report.primary_language, output_languages=list(report.output_languages),
                       title=data.get("title", report.title.original), ticket=data.get("ticket", report.ticket),
                       technicians=[s.strip() for s in data.get("technicians", ", ".join(report.technicians)).split(",") if s.strip()],
                       intervention_types=list(report.intervention_types),
                       other_intervention_detail=report.other_intervention_detail)
        kind = "set_report_metadata"
    elif method == "rename_module":
        module, text = args
        target = NodeAddress(report.id, module, None, "title")
        kind, payload = "rename_module", {"title": text}
    else:
        if method == "update_heading":
            module, block_id, text, level = args
        else:
            module, block_id, text = args
        field = "table" if method == "update_table" else "photo" if method == "update_photo_caption" else "text"
        target = NodeAddress(report.id, module, block_id, field)
        block = find_node(report, target)
        if method in ("update_paragraph", "update_heading"):
            expected = HeadingBlock if method == "update_heading" else ParagraphBlock
            if not isinstance(block, expected) or not isinstance(text, str):
                raise ValueError("Text edit has the wrong block or value type")
            payload = {"text": text, "rich": rebase_rich(block.text.original, text, block.rich)}
            kind = "set_heading_rich" if method == "update_heading" else "set_paragraph_rich"
            if method == "update_heading":
                payload["level"] = level
        elif method == "update_table":
            raw = json.loads(text)
            if (not isinstance(block, TableBlock) or not isinstance(raw, list)
                    or len(raw) != len(block.rows)
                    or any(not isinstance(row, list) or len(row) != len(old)
                           for row, old in zip(raw, block.rows))):
                raise ValueError("Cell editing cannot change table shape")
            rows = deepcopy(block.rows)
            for row, values in zip(rows, raw):
                for cell, value in zip(row, values):
                    if not isinstance(value, str):
                        raise ValueError("Cell source must be text")
                    cell.update_original(value)
            kind, payload = "set_table_rows", {"rows": rows}
        else:
            kind, payload = "set_photo_caption", {"text": text}
    return CommandIntent(kind, target, payload, revision, generation)


def table_shape_intent(session, module, block_id, operation):
    report = session.report_snapshot()
    target = NodeAddress(report.id, module, block_id, "table")
    block = find_node(report, target)
    if not isinstance(block, TableBlock):
        raise ValueError("Target block is not a table")
    width = len(block.rows[0]) if block.rows else 0
    operations = {"add_row": ("insert_row", len(block.rows)),
                  "add_col": ("insert_column", width),
                  "del_row": ("delete_row", len(block.rows) - 1),
                  "del_col": ("delete_column", width - 1)}
    if operation not in operations:
        raise ValueError("Unsupported table operation")
    op, index = operations[operation]
    rows = change_grid(block.rows, op, index, report.primary_language)
    return CommandIntent("set_table_rows", target, {"rows": rows}, session.revision, session.generation)


_WORD_PT_SIZES = (8.0, 9.0, 10.0, 11.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0, 28.0, 36.0, 48.0, 72.0)


def _apply_span_transform(text: str, rich: RichFormatting, start: int, end: int, transform) -> RichFormatting:
    if start >= end or not text:
        return deepcopy(rich)
    boundaries = sorted({start, end} | {edge for r in rich.runs for edge in (r.start, r.end)})
    spans = []
    for left, right in zip(boundaries, boundaries[1:]):
        if left >= right:
            continue
        existing = style_at(rich, left)
        candidate = replace(existing, start=left, end=right) if existing else TextRun(left, right)
        if left >= start and right <= end:
            candidate = transform(candidate)
        if _run_has_style(candidate):
            if (spans and spans[-1].end == left
                    and replace(spans[-1], start=0, end=0) == replace(candidate, start=0, end=0)):
                spans[-1] = replace(spans[-1], end=right)
            else:
                spans.append(candidate)
    result = RichFormatting(spans, deepcopy(list(rich.paragraphs)))
    validate_rich(result, text)
    return result


def _apply_para_transform(text: str, rich: RichFormatting, start: int, end: int, transform) -> RichFormatting:
    specs = {p.start: deepcopy(p) for p in rich.paragraphs}
    for pos in _paragraph_starts(text, start, end):
        current = specs.get(pos, ParagraphStyle(pos))
        changed = transform(current)
        if changed == ParagraphStyle(pos):
            specs.pop(pos, None)
        else:
            specs[pos] = changed
    result = RichFormatting(deepcopy(list(rich.runs)), sorted(specs.values(), key=lambda p: p.start))
    validate_rich(result, text)
    return result


def _resolve_codepoint_selection(text: str, raw_start, raw_end) -> tuple[int, int]:
    u16_len = len(text.encode("utf-16-le")) // 2
    s16 = max(0, min(u16_len, int(raw_start) if isinstance(raw_start, int) else 0))
    e16 = max(s16, min(u16_len, int(raw_end) if isinstance(raw_end, int) else s16))
    try:
        cp_start = to_codepoint(text, s16)
    except ValueError:
        cp_start = 0
    try:
        cp_end = to_codepoint(text, e16)
    except ValueError:
        cp_end = len(text)
    if cp_end < cp_start:
        cp_start, cp_end = cp_end, cp_start
    return cp_start, cp_end


def rich_format_intent(session, module: str, block_id: str, op_json: str, revision: int, generation: str) -> CommandIntent:
    """Apply a Microsoft Word Font or Paragraph Ribbon operation to a canonical text block."""
    import json
    report = session.report_snapshot()
    target = NodeAddress(report.id, module, block_id, "text")
    block = find_node(report, target)
    if not isinstance(block, (ParagraphBlock, HeadingBlock)):
        raise ValueError("Select a paragraph or heading block to apply Word formatting")
    spec = json.loads(op_json)
    if not isinstance(spec, dict) or "op" not in spec:
        raise ValueError("Invalid formatting operation")

    op = str(spec["op"])
    val = spec.get("value")
    text = block.text.original
    rich = deepcopy(block.rich)
    cp_start, cp_end = _resolve_codepoint_selection(text, spec.get("start", 0), spec.get("end", 0))
    char_start, char_end = (0, len(text)) if cp_start == cp_end else (cp_start, cp_end)

    if op in ("bold", "italic", "underline", "strike"):
        if not text:
            raise ValueError("Enter text in the block before applying character styles")
        all_on = True
        for idx in range(char_start, char_end):
            r = style_at(rich, idx)
            if not r or not getattr(r, op):
                all_on = False
                break
        target_flag = not all_on if val is None else bool(val)
        rich = _apply_span_transform(text, rich, char_start, char_end, lambda r: replace(r, **{op: target_flag}))

    elif op == "baseline":
        if not text:
            raise ValueError("Enter text in the block before applying subscript/superscript")
        if val not in BASELINES:
            raise ValueError("Unsupported baseline mode")
        all_same = all(
            (style_at(rich, idx) is not None and style_at(rich, idx).baseline == val)
            for idx in range(char_start, char_end)
        )
        next_base = "normal" if all_same else val
        rich = _apply_span_transform(text, rich, char_start, char_end, lambda r: replace(r, baseline=next_base))

    elif op == "family":
        if not text:
            raise ValueError("Enter text in the block before changing font family")
        fam = str(val or "").strip()
        rich = _apply_span_transform(text, rich, char_start, char_end, lambda r: replace(r, family=fam))

    elif op == "size":
        if not text:
            raise ValueError("Enter text in the block before changing font size")
        sz = float(val or 0.0)
        if sz != 0.0 and not (6.0 <= sz <= 96.0):
            raise ValueError("Font size must be between 6 and 96 pt")
        rich = _apply_span_transform(text, rich, char_start, char_end, lambda r: replace(r, size=sz))

    elif op == "step_size":
        if not text:
            raise ValueError("Enter text in the block before resizing font")
        delta = 1 if int(val or 1) >= 0 else -1
        default_pt = 16.0 if isinstance(block, HeadingBlock) else 11.0
        sample = style_at(rich, char_start)
        cur_pt = sample.size if (sample and sample.size >= 6.0) else default_pt
        if delta > 0:
            next_pt = next((p for p in _WORD_PT_SIZES if p > cur_pt), 72.0)
        else:
            next_pt = next((p for p in reversed(_WORD_PT_SIZES) if p < cur_pt), 8.0)
        rich = _apply_span_transform(text, rich, char_start, char_end, lambda r: replace(r, size=next_pt))

    elif op == "color":
        if not text:
            raise ValueError("Enter text in the block before applying font color")
        col = str(val or "").strip()
        rich = _apply_span_transform(text, rich, char_start, char_end, lambda r: replace(r, color=col))

    elif op == "highlight":
        if not text:
            raise ValueError("Enter text in the block before applying highlight color")
        hl = str(val or "").strip()
        rich = _apply_span_transform(text, rich, char_start, char_end, lambda r: replace(r, highlight=hl))

    elif op == "text_effect":
        if not text:
            raise ValueError("Enter text in the block before applying text effects")
        presets = {
            "fill_blue": {"color": "#1d4ed8", "bold": True, "highlight": ""},
            "fill_gold": {"color": "#b45309", "bold": True, "highlight": "#fef3c7"},
            "fill_emerald": {"color": "#047857", "bold": True, "highlight": "#d1fae5"},
            "fill_crimson": {"color": "#b91c1c", "bold": True, "highlight": "#fee2e2"},
            "outline_slate": {"color": "#334155", "bold": True, "underline": True},
            "clear": {"color": "", "highlight": "", "bold": False, "underline": False},
        }
        preset = presets.get(str(val), presets["fill_blue"])
        rich = _apply_span_transform(text, rich, char_start, char_end, lambda r: replace(r, **preset))

    elif op == "clear_format":
        if cp_start < cp_end and text:
            rich = _apply_span_transform(
                text, rich, cp_start, cp_end,
                lambda r: TextRun(r.start, r.end),
            )
        else:
            rich = RichFormatting()

    elif op == "change_case":
        if not text:
            raise ValueError("Enter text in the block before changing case")
        sub = text[char_start:char_end]
        mode = str(val or "upper")
        if mode == "lower":
            converted = sub.lower()
        elif mode == "upper":
            converted = sub.upper()
        elif mode == "capitalize":
            converted = " ".join(w[:1].upper() + w[1:].lower() for w in sub.split(" "))
        elif mode == "toggle":
            converted = sub.swapcase()
        else:  # sentence case
            converted = sub[:1].upper() + sub[1:].lower() if sub else sub
        new_text = text[:char_start] + converted + text[char_end:]
        if len(new_text) == len(text):
            text = new_text
            validate_rich(rich, text)
        else:
            rich = rebase_rich(text, new_text, rich)
            text = new_text

    elif op == "align":
        if val not in ALIGNMENTS:
            raise ValueError("Unsupported paragraph alignment")
        rich = _apply_para_transform(text, rich, cp_start, cp_end, lambda p: replace(p, align=val))

    elif op == "list_kind":
        if val not in LIST_KINDS:
            raise ValueError("Unsupported list style")
        starts = _paragraph_starts(text, cp_start, cp_end)
        by_start = {p.start: p for p in rich.paragraphs}
        all_same = all(by_start.get(s, ParagraphStyle(s)).list_kind == val for s in starts)
        next_list = "none" if all_same else val
        rich = _apply_para_transform(text, rich, cp_start, cp_end, lambda p: replace(p, list_kind=next_list))

    elif op == "indent":
        step = 1 if int(val or 1) >= 0 else -1
        rich = _apply_para_transform(
            text, rich, cp_start, cp_end,
            lambda p: replace(p, indent=max(0, min(12, p.indent + step))),
        )

    elif op == "line_height":
        lh = float(val or 1.0)
        if not (1.0 <= lh <= 3.0):
            raise ValueError("Line spacing must be between 1.0 and 3.0")
        rich = _apply_para_transform(text, rich, cp_start, cp_end, lambda p: replace(p, line_height=lh))

    elif op == "shading":
        sh = str(val or "").strip()
        rich = _apply_para_transform(text, rich, cp_start, cp_end, lambda p: replace(p, shading=sh))

    elif op == "border":
        starts = _paragraph_starts(text, cp_start, cp_end)
        by_start = {p.start: p for p in rich.paragraphs}
        all_bordered = all(by_start.get(s, ParagraphStyle(s)).border for s in starts)
        next_border = (not all_bordered) if val in (None, "toggle") else bool(val)
        rich = _apply_para_transform(text, rich, cp_start, cp_end, lambda p: replace(p, border=next_border))

    elif op == "sort_lines":
        lines = text.split("\n")
        if len(lines) > 1:
            reverse = str(val) == "desc"
            sorted_lines = sorted(lines, key=lambda s: s.casefold(), reverse=reverse)
            new_text = "\n".join(sorted_lines)
            first_para = next((p for p in rich.paragraphs if p.start == 0), None)
            new_paras = [replace(first_para, start=0)] if first_para else []
            text = new_text
            rich = RichFormatting(runs=[], paragraphs=new_paras)
            validate_rich(rich, text)
    else:
        raise ValueError(f"Unsupported formatting operation: {op}")

    kind = "set_heading_rich" if isinstance(block, HeadingBlock) else "set_paragraph_rich"
    payload = {"text": text, "rich": rich}
    if isinstance(block, HeadingBlock):
        payload["level"] = block.level
    return CommandIntent(kind, target, payload, revision, generation)

