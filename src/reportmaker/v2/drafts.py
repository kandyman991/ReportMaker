"""Uncommitted inline text lives outside the canonical report.

The only way to persist a draft is through M1.2's validated CommandGateway.
Unresolved drafts block ordinary commands, Undo/Redo, Save and project switches.
Separate fields may be drafted concurrently, but a commit checks that the
specific canonical source field has not changed since its draft began.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy

from ..model import HeadingBlock, LocalizedText, Module, ParagraphBlock, TableBlock
from ..rich_text import RichFormatting
from .adapters.formatting import format_chars, format_paragraphs
from .adapters.tables import checked_rows, edit_cell, change_grid
from .adapters.rich_text import rebase_rich
from .commands import CommandGateway, CommandIntent
from .projections import NodeAddress, find_node
from .session import ReportSession, StaleIntentError


@dataclass(frozen=True)
class TextDraft:
    address: NodeAddress
    original: str
    value: str
    generation: str
    rich: RichFormatting | None = None


@dataclass(frozen=True)
class TableDraft:
    address: NodeAddress
    original: list[list[LocalizedText]]
    rows: list[list[LocalizedText]]
    generation: str
    # Provenance is only a transient draft mapping. TableBlock has no cell IDs.
    origins: list[list[tuple[int, int] | None]]


def _source(node, address: NodeAddress) -> str:
    if address.field == "title" and address.block_id is None and isinstance(node, Module):
        return node.title.original
    if (address.field == "text" and address.block_id is not None
            and isinstance(node, (ParagraphBlock, HeadingBlock))):
        return node.text.original
    raise ValueError("Only module titles, paragraph and heading text can be edited inline")


class DraftCoordinator:
    """Guard multiple independent drafts without creating a parallel model."""

    def __init__(self, session: ReportSession, gateway: CommandGateway) -> None:
        self.session = session
        self.gateway = gateway
        self._drafts: dict[NodeAddress, TextDraft | TableDraft] = {}
        self._committing = False
        session.set_draft_guard(self._draft_guard)

    def _draft_guard(self) -> bool:
        if not self._drafts:
            return True
        if self._committing:
            # Single-use permit: no reentrant command from a publish listener
            # can accidentally piggyback on this inline commit.
            self._committing = False
            return True
        return False

    @property
    def pending(self) -> bool:
        return bool(self._drafts)

    def is_dirty(self, address: NodeAddress) -> bool:
        return address in self._drafts

    def text(self, address: NodeAddress) -> str:
        draft = self._drafts.get(address)
        if draft is not None:
            return draft.value
        return _source(find_node(self.session.report_snapshot(), address), address)

    def update(self, address: NodeAddress, value: str) -> None:
        if not isinstance(value, str):
            raise ValueError("Inline text must be a string")
        old = self._drafts.get(address)
        if old is None:
            original = _source(find_node(self.session.report_snapshot(), address), address)
            generation = self.session.generation
            rich = None
        else:
            original, generation = old.original, old.generation
            # Rebase staged formatting through subsequent text edits instead
            # of discarding toolbar changes or moving styling onto new text.
            rich = (rebase_rich(old.value, value, old.rich)
                    if old.rich is not None and value != old.value else
                    deepcopy(old.rich))
        if generation != self.session.generation:
            raise StaleIntentError("Draft belongs to a previous report")
        node = find_node(self.session.report_snapshot(), address)
        if _source(node, address) != original:
            raise StaleIntentError("Source changed since editing began; draft preserved")
        if value == original and (rich is None or rich == getattr(node, "rich", None)):
            self._drafts.pop(address, None)
        else:
            self._drafts[address] = TextDraft(address, original, value, generation, rich)

    def rich(self, address: NodeAddress) -> RichFormatting:
        node = find_node(self.session.report_snapshot(), address)
        if not isinstance(node, (ParagraphBlock, HeadingBlock)):
            raise ValueError("Rich formatting requires a paragraph or heading")
        draft = self._drafts.get(address)
        if draft is None:
            return deepcopy(node.rich)
        if draft.generation != self.session.generation or node.text.original != draft.original:
            raise StaleIntentError("Source changed since editing began; draft preserved")
        if draft.rich is not None:
            return deepcopy(draft.rich)
        return rebase_rich(draft.original, draft.value, node.rich)

    def format(self, address: NodeAddress, start: int, end: int,
               field: str, value: object, *, paragraph: bool = False) -> bool:
        """Stage styling without changing canonical data or undo history."""
        node = find_node(self.session.report_snapshot(), address)
        if (address.field != "text" or address.block_id is None
                or not isinstance(node, (ParagraphBlock, HeadingBlock))):
            raise ValueError("Formatting requires a paragraph or heading text address")
        old = self._drafts.get(address)
        if old is not None and (old.generation != self.session.generation
                                or old.original != node.text.original):
            raise StaleIntentError("Source changed since editing began; draft preserved")
        text = old.value if old is not None else node.text.original
        previous = self.rich(address)
        changed = (format_paragraphs(text, previous, start, end, field, value)
                   if paragraph else
                   format_chars(text, previous, start, end, field, value))
        if previous == changed:
            return False
        if text == node.text.original and changed == node.rich:
            self._drafts.pop(address, None)
        else:
            self._drafts[address] = TextDraft(
                address, node.text.original, text, self.session.generation, changed)
        return True

    def table_rows(self, address: NodeAddress) -> list:
        node = find_node(self.session.report_snapshot(), address)
        if (address.field != "table" or address.block_id is None
                or address.row is not None or address.column is not None
                or not isinstance(node, TableBlock)):
            raise ValueError("Expected a stable table address")
        draft = self._drafts.get(address)
        if draft is None:
            return checked_rows(node.rows)
        if not isinstance(draft, TableDraft):
            raise ValueError("Conflicting draft address")
        if draft.generation != self.session.generation or draft.original != node.rows:
            raise StaleIntentError("Table changed since editing began; draft preserved")
        return checked_rows(draft.rows)

    @staticmethod
    def _origins(rows: list[list[LocalizedText]]) -> list[list[tuple[int, int] | None]]:
        return [[(i, j) for j in range(len(cells))]
                for i, cells in enumerate(rows)]

    @staticmethod
    def _remap_origins(origins: list[list[tuple[int, int] | None]],
                       operation: str, index: int):
        result = deepcopy(origins)
        if operation == "insert_row":
            width = max(1, len(result[0]) if result else 1)
            result.insert(index, [None] * width)
        elif operation == "delete_row":
            result.pop(index)
        elif operation == "insert_column":
            for row in result:
                row.insert(index, None)
        elif operation == "delete_column":
            for row in result:
                row.pop(index)
        return result

    def _stage_table(self, address: NodeAddress, rows: list,
                     origins: list[list[tuple[int, int] | None]] | None = None) -> bool:
        node = find_node(self.session.report_snapshot(), address)
        if not isinstance(node, TableBlock):
            raise ValueError("Not a table")
        previous = self._drafts.get(address)
        original = checked_rows(node.rows) if previous is None else previous.original
        if previous is not None and (not isinstance(previous, TableDraft)
                                     or previous.generation != self.session.generation
                                     or original != node.rows):
            raise StaleIntentError("Table changed since editing began; draft preserved")
        if ((previous is not None and previous.rows == rows)
                or (previous is None and original == rows)):
            return False
        if original == rows:
            self._drafts.pop(address, None)
        else:
            self._drafts[address] = TableDraft(
                address, original, checked_rows(rows), self.session.generation,
                deepcopy(origins) if origins is not None else (
                    deepcopy(previous.origins) if isinstance(previous, TableDraft)
                    else self._origins(original)))
        return True

    def update_cell(self, address: NodeAddress, row: int, column: int, value: str) -> bool:
        rows = self.table_rows(address)
        updated = edit_cell(rows, row, column, value)
        previous = self._drafts.get(address)
        origins = (previous.origins if isinstance(previous, TableDraft)
                   else self._origins(rows))
        origin = origins[row][column]
        if origin is not None:
            # Recompute from the ORIGINAL localized cell, not the previous
            # keystroke: changing text then restoring it must not stale a
            # translation, even when columns/rows shifted within the draft.
            initial = (previous.original if isinstance(previous, TableDraft)
                       else rows)
            baseline = deepcopy(initial[origin[0]][origin[1]])
            baseline.update_original(value)
            updated[row][column] = baseline
        return self._stage_table(address, updated, origins=origins)

    def modify_table(self, address: NodeAddress, operation: str, index: int) -> bool:
        rows = self.table_rows(address)
        previous = self._drafts.get(address)
        origins = (previous.origins if isinstance(previous, TableDraft)
                   else self._origins(rows))
        # New cells use the report's source language, not a neighboring
        # cell's potentially imported language tag.
        updated = change_grid(
            rows, operation, index, self.session.report_snapshot().primary_language)
        return self._stage_table(
            address, updated, origins=self._remap_origins(origins, operation, index))

    def discard(self, address: NodeAddress):
        self._drafts.pop(address, None)
        return self.table_rows(address) if address.field == "table" else self.text(address)

    def commit(self, address: NodeAddress):
        draft = self._drafts.get(address)
        if draft is None:
            return None
        if draft.generation != self.session.generation:
            raise StaleIntentError("Draft belongs to a previous report")
        node = find_node(self.session.report_snapshot(), address)
        if isinstance(draft, TextDraft) and _source(node, address) != draft.original:
            raise StaleIntentError("Source changed since editing began; draft preserved")
        if isinstance(draft, TableDraft):
            node = find_node(self.session.report_snapshot(), address)
            if not isinstance(node, TableBlock) or node.rows != draft.original:
                raise StaleIntentError("Table changed since editing began; draft preserved")
            kind, args = "set_table_rows", {"rows": checked_rows(draft.rows)}
        elif address.field == "title":
            kind, args = "rename_module", {"title": draft.value}
        else:
            kind = "set_heading_rich" if isinstance(node, HeadingBlock) else "set_paragraph_rich"
            args = {"text": draft.value,
                    "rich": (deepcopy(draft.rich) if draft.rich is not None
                             else rebase_rich(draft.original, draft.value, node.rich))}
        intent = CommandIntent(kind, address, args,
                               self.session.revision, self.session.generation)
        # Bypass the draft guard only for this one verified command. Other
        # outstanding drafts remain protected against Undo, Save and Open.
        self._committing = True
        try:
            change = self.gateway.execute(intent)
        finally:
            self._committing = False
        self._drafts.pop(address, None)
        return change
