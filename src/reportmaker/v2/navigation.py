"""Pure, detached navigation over the canonical report projection.

Search and subtree/window selection are presentation-only. They never write
to the report, the project archive, or a second navigation tree.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model import Report
from .projections import BranchRow, project_branch


@dataclass(frozen=True)
class SearchHit:
    stable_id: str
    module_id: str
    kind: str
    excerpt: str


def search_report(report: Report, query: str, *, limit: int = 500) -> tuple[SearchHit, ...]:
    """Case-insensitive matches including collapsed descendants and photo captions."""
    if not isinstance(query, str) or type(limit) is not int or limit < 1:
        raise ValueError("Invalid search")
    needle = query.strip().casefold()
    if not needle:
        return ()
    hits = []
    for row in project_branch(report):
        if row.kind not in ("root", "module", "conclusion", "heading", "paragraph", "photo", "table"):
            continue
        if needle not in row.text.casefold():
            continue
        at = row.text.casefold().find(needle)
        excerpt = row.text[max(0, at - 32):at + len(needle) + 64].replace("\n", " ")
        hits.append(SearchHit(row.stable_id, row.parent_module_id or row.stable_id,
                              row.kind, excerpt))
        if len(hits) >= limit:
            break
    return tuple(hits)


def subtree_range(rows: tuple[BranchRow, ...], module_id: str) -> tuple[int, int]:
    """Contiguous preorder span; never infer ownership from widget parents."""
    start = next((i for i, row in enumerate(rows)
                  if row.stable_id == module_id and row.kind in ("module", "conclusion")), None)
    if start is None:
        raise LookupError("Unknown module to focus")
    depth = rows[start].depth
    end = start + 1
    while end < len(rows) and rows[end].depth > depth:
        end += 1
    return start, end


def window_for(rows: tuple[BranchRow, ...], page: int,
               *, size: int = 120) -> tuple[tuple[BranchRow, ...], int]:
    """Bound active rows with deterministic, stable-ID indexed windows."""
    if type(page) is not int or type(size) is not int or page < 0 or size < 1:
        raise ValueError("Invalid branch window")
    count = max(1, (len(rows) + size - 1) // size)
    if page >= count:
        page = count - 1
    return rows[page * size:(page + 1) * size], count
