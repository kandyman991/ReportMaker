"""Stable-ID, detached V2 branch projections; Qt and persistence-free.

Rows are read-only value records derived from the same Report.modules and
Module.blocks used by engine.module_outline and project export. They are never
stored as an independently editable report hierarchy.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model import (
    HeadingBlock, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, Report, TableBlock,
)


@dataclass(frozen=True)
class NodeAddress:
    report_id: str
    module_id: str
    block_id: str | None = None
    field: str = "title"
    row: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class BranchRow:
    stable_id: str
    parent_module_id: str | None
    kind: str
    depth: int
    mixed_sibling_index: int
    source_revision: int
    text: str = ""
    wrapper_id: str | None = None


def _modules(report: Report):
    stack = list(reversed(report.ordered_sections()))
    while stack:
        module = stack.pop()
        yield module
        stack.extend(block.module for block in reversed(module.blocks)
                     if isinstance(block, NestedModuleBlock))


def find_node(report: Report, address: NodeAddress):
    """Resolve a canonical address against the supplied report snapshot.

    Callers must supply a *detached* report (session.report_snapshot) when
    using this outside a ProjectEditor transaction.
    """
    if not isinstance(report, Report) or not isinstance(address, NodeAddress):
        raise ValueError("A report and stable node address are required")
    if address.report_id != report.id:
        raise LookupError("Address belongs to another report")
    if address.module_id == report.id and address.block_id is None:
        return report
    for module in _modules(report):
        if module.id == address.module_id:
            if address.block_id is None:
                return module
            for block in module.blocks:
                if block.id == address.block_id and not isinstance(block, NestedModuleBlock):
                    return block
            raise LookupError("Block is not owned by the addressed module")
    raise LookupError("Unknown module ID")


def _kind_and_text(node):
    if isinstance(node, Module):
        return "module", node.title.original
    if isinstance(node, ParagraphBlock):
        return "paragraph", node.text.original
    if isinstance(node, HeadingBlock):
        return "heading", node.text.original
    if isinstance(node, PhotoBlock):
        return "photo", node.caption.original if node.caption is not None else ""
    if isinstance(node, TableBlock):
        return "table", "\n".join(" | ".join(cell.original for cell in row) for row in node.rows)
    if isinstance(node, PageBreakBlock):
        return "page-break", ""
    raise ValueError("Unknown report node")


def project_branch(
    report: Report, *, expanded: frozenset[str] | None = None,
    revision: int = 0,
) -> tuple[BranchRow, ...]:
    """Iterative preorder preserving original *mixed* sibling positions.

    With expanded=None all containers are visible. If supplied, children of
    any module absent from expanded are hidden in this transient projection.
    Conclusions always remain the final top-level row.
    """
    if type(revision) is not int or revision < 0:
        raise ValueError("Projection revision must be non-negative")
    if expanded is not None and not isinstance(expanded, frozenset):
        raise ValueError("Expanded nodes must be a frozen ID set")
    rows = [BranchRow(report.id, None, "root", 0, 0, revision, report.title.original)]
    sections = report.ordered_sections()
    stack = [(mod, None, i, 1, None, mod is report.conclusion)
             for i, mod in reversed(list(enumerate(sections)))]
    while stack:
        node, parent_id, index, depth, wrapper_id, is_conclusion = stack.pop()
        kind, text = _kind_and_text(node)
        if is_conclusion:
            kind = "conclusion"
        rows.append(BranchRow(node.id, parent_id, kind, depth, index,
                              revision, text, wrapper_id))
        if isinstance(node, Module) and (expanded is None or node.id in expanded):
            for i in range(len(node.blocks) - 1, -1, -1):
                block = node.blocks[i]
                if isinstance(block, NestedModuleBlock):
                    stack.append((block.module, node.id, i, depth + 1, block.id, False))
                else:
                    stack.append((block, node.id, i, depth + 1, None, False))
    return tuple(rows)
