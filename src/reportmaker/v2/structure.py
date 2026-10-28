"""Pure, pre-commit structural placement planner for V2 Branch Editor.

A drop is a source node and an explicit BEFORE/AFTER/INSIDE destination.
The only positional truth is the canonical report projection. This module
never mutates a report or stores a second hierarchy.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model import Report
from .projections import BranchRow, NodeAddress, project_branch


@dataclass(frozen=True)
class DropPlan:
    source_id: str
    source_kind: str  # "module" or "block"
    source_parent_id: str | None
    destination_parent_id: str | None
    destination_index: int  # insertion index BEFORE removing the source
    noop: bool


def _resolve(rows: dict[str, BranchRow], report: Report,
             address: NodeAddress) -> BranchRow:
    if not isinstance(address, NodeAddress) or address.report_id != report.id:
        raise ValueError("Placement address belongs to another report")
    identifier = address.block_id or address.module_id
    row = rows.get(identifier)
    if row is None:
        raise LookupError("Placement node no longer exists")
    if address.block_id is None:
        if identifier != report.id and row.kind not in ("module", "conclusion"):
            raise ValueError("A module address is required")
    elif row.kind in ("root", "module", "conclusion"):
        raise ValueError("Nested modules must use their module ID, not wrapper ID")
    elif row.parent_module_id != address.module_id:
        raise LookupError("Content block does not belong to the addressed module")
    return row


def plan_drop(report: Report, source: NodeAddress, anchor: NodeAddress,
              position: str) -> DropPlan:
    """Validate and plan a structural move without changing the canonical tree.

    index semantics intentionally match ProjectEditor.move_module/move_block:
    the insertion index refers to the *pre-removal* destination sequence.
    """
    if position not in ("before", "after", "inside"):
        raise ValueError("Drop position must be Before, After or Inside")
    projection = project_branch(report)
    rows = {row.stable_id: row for row in projection}
    origin = _resolve(rows, report, source)
    destination = _resolve(rows, report, anchor)
    if origin.kind in ("root", "conclusion"):
        raise ValueError("Report root and Conclusions cannot be moved")
    if origin.stable_id == destination.stable_id:
        raise ValueError("Cannot drop a node onto itself")
    is_module = origin.kind == "module"

    if position == "inside":
        if destination.kind not in ("root", "module", "conclusion"):
            raise ValueError("Inside is available only on module containers")
        parent = None if destination.kind == "root" else destination.stable_id
        if parent is None:
            at = len(report.modules)
        else:
            # All IDs have already been resolved against the canonical tree.
            from .projections import find_node
            at = len(find_node(report, NodeAddress(report.id, parent)).blocks)
    else:
        if destination.kind == "root":
            raise ValueError("Before/After requires an actual sibling")
        if destination.kind == "conclusion":
            if position != "before":
                raise ValueError("Conclusions must remain last")
            parent = None
            at = len(report.modules)
        else:
            parent = destination.parent_module_id
            at = destination.mixed_sibling_index + (position == "after")

    # Conclusions is a dedicated final section, not a drop destination.
    # Allow the special "before Conclusions" root position above, but reject
    # dropping blocks (as well as modules) inside or among its content.
    if parent == report.conclusion.id:
        raise ValueError("Cannot drop nodes into Conclusions")
    if is_module:
        # Walk canonical ancestors, rather than reconstructing a separate tree.
        current = parent
        while current is not None:
            if current == origin.stable_id:
                raise ValueError("Cannot move a module into its own subtree")
            current_row = rows.get(current)
            if current_row is None or current_row.kind not in ("module", "conclusion"):
                raise ValueError("Invalid structural destination")
            current = current_row.parent_module_id
    elif parent is None:
        raise ValueError("Content blocks cannot be direct report children")

    old_parent = origin.parent_module_id
    # Existing core moves adjust the insertion index after source removal.
    effective = at - (old_parent == parent and at > origin.mixed_sibling_index)
    noop = old_parent == parent and effective == origin.mixed_sibling_index
    return DropPlan(origin.stable_id, "module" if is_module else "block",
                    old_parent, parent, at, noop)
