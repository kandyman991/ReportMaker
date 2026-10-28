"""Pure Unicode-safe adapter for *source* paragraph edits with rich ranges.

Unchanged characters retain their formatting through an edit. Replaced or
new characters are unstyled; existing styles are never applied to unrelated
text by stale offsets. Paragraph styling survives when its delimiter survives.
Ambiguous deletion of a styled paragraph delimiter is rejected, preserving
the original data and the pending draft until the user resolves it.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from difflib import SequenceMatcher

from ...rich_text import RichFormatting, validate_rich


def rebase_rich(before: str, after: str, rich: RichFormatting) -> RichFormatting:
    validate_rich(rich, before)
    if before == after:
        return deepcopy(rich)
    if not rich.runs and not rich.paragraphs:
        # Plain paragraphs need no quadratic diff work even for large pastes.
        return RichFormatting()
    if len(before) + len(after) > 16000:
        raise ValueError("Formatted paragraph is too large for safe inline remapping")
    matching = SequenceMatcher(a=before, b=after, autojunk=False).get_matching_blocks()
    spans = []
    for match in matching:
        if not match.size:
            continue
        left, right = match.a, match.a + match.size
        for run in rich.runs:
            start, end = max(left, run.start), min(right, run.end)
            if start < end:
                offset = match.b - match.a
                spans.append(replace(run, start=start + offset, end=end + offset))
    spans.sort(key=lambda run: (run.start, run.end))
    runs = []
    for run in spans:
        if (runs and runs[-1].end == run.start
            and replace(runs[-1], start=0, end=0) == replace(run, start=0, end=0)):
            runs[-1] = replace(runs[-1], end=run.end)
        else:
            runs.append(run)
    paragraphs = []
    for para in rich.paragraphs:
        if para.start == 0:
            paragraphs.append(replace(para, start=0))
            continue
        newline = para.start - 1
        match = next((m for m in matching if m.a <= newline < m.a + m.size), None)
        if match is None:
            raise ValueError("Styled paragraph boundary was edited; formatting cannot be safely mapped")
        new_start = match.b + (newline - match.a) + 1
        if new_start > len(after) or after[new_start - 1] != "\n":
            raise ValueError("Styled paragraph boundary cannot be retained")
        paragraphs.append(replace(para, start=new_start))
    result = RichFormatting(runs=runs, paragraphs=paragraphs)
    validate_rich(result, after)
    return result
