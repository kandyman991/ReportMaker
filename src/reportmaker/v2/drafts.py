"""Uncommitted inline text lives outside the canonical report.

The only way to persist a draft is through M1.2's validated CommandGateway.
Unresolved drafts block ordinary commands, Undo/Redo, Save and project switches.
Separate fields may be drafted concurrently, but a commit checks that the
specific canonical source field has not changed since its draft began.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy

from ..model import HeadingBlock, LocalizedText, Module, ParagraphBlock, PhotoBlock, TableBlock
from ..rich_text import RichFormatting
from .adapters.formatting import format_chars, format_paragraphs
from .adapters.tables import checked_rows, edit_cell, change_grid
from .adapters.rich_text import rebase_rich
from .commands import CommandGateway, CommandIntent
from .projections import NodeAddress, find_node
from .session import PendingDraftError, ReportSession, StaleIntentError


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
    if address.field == "caption" and address.block_id is not None and isinstance(node, PhotoBlock):
        return node.caption.original if node.caption is not None else ""
    raise ValueError("Only module titles, paragraph/heading text and photo captions can be edited inline")


class DraftCoordinator:
    """Guard multiple independent drafts without creating a parallel model."""

    def __init__(self, session: ReportSession, gateway: CommandGateway) -> None:
        self.session = session
        self.gateway = gateway
        self._drafts: dict[NodeAddress, TextDraft | TableDraft] = {}
        self._committing = False
        self._owners: dict[NodeAddress, str] = {}
        self._state_listeners = []
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

    def subscribe_pending(self, listener):
        """Notify UI when first pending draft appears or last one resolves.

        Draft content remains private to this coordinator; callbacks receive
        only the boolean state, never report text or individual field drafts.
        """
        if not callable(listener):
            raise TypeError("Draft-state listener must be callable")
        self._state_listeners.append(listener)

        def unsubscribe():
            if listener in self._state_listeners:
                self._state_listeners.remove(listener)
        return unsubscribe

    def _publish_pending(self, previous: bool):
        if previous != bool(self._drafts):
            for listener in tuple(self._state_listeners):
                try:
                    listener(bool(self._drafts))
                except Exception:
                    # A presentation listener cannot cancel a validated draft.
                    continue

    @property
    def pending(self) -> bool:
        return bool(self._drafts)

    def is_dirty(self, address: NodeAddress) -> bool:
        return address in self._drafts

    def pending_addresses(self, *, owner: str | None = None) -> tuple[NodeAddress, ...]:
        """Expose draft identities (never text) for explicit owner-scoped UI actions."""
        if owner is not None and (not isinstance(owner, str) or not owner.strip()):
            raise ValueError("Draft owner must be a nonempty string")
        return tuple(address for address in self._drafts
                     if owner is None or self._owners.get(address) == owner)

    def draft_owner(self, address: NodeAddress) -> str | None:
        """All views inspect one shared pending state, without copying a report."""
        return self._owners.get(address)

    def _check_owner(self, address: NodeAddress, owner: str) -> None:
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("Draft editor must have a nonempty identity")
        current = self._owners.get(address)
        if current is not None and current != owner:
            raise PendingDraftError(
                f"Resolve the {current} draft before editing this field in {owner}")

    def _store(self, address: NodeAddress, draft: TextDraft | TableDraft,
               owner: str) -> None:
        previous = bool(self._drafts)
        self._drafts[address] = draft
        self._owners[address] = owner
        self._publish_pending(previous)

    def _clear(self, address: NodeAddress) -> None:
        previous = bool(self._drafts)
        self._drafts.pop(address, None)
        self._owners.pop(address, None)
        self._publish_pending(previous)

    def for_editor(self, owner: str) -> "EditorDraftPort":
        """Give a future Editor/Gallery tab guarded access to the same drafts."""
        if not isinstance(owner, str) or not owner.strip() or owner == "branch":
            raise ValueError("External editor requires a distinct nonempty identity")
        return EditorDraftPort(self, owner)

    def text(self, address: NodeAddress) -> str:
        draft = self._drafts.get(address)
        if draft is not None:
            return draft.value
        return _source(find_node(self.session.report_snapshot(), address), address)

    def text_stale(self, address: NodeAddress) -> bool:
        """A stale draft remains copyable/revertible but must not be edited."""
        draft = self._drafts.get(address)
        if draft is None:
            return False
        if not isinstance(draft, TextDraft):
            raise ValueError("Not a text draft")
        if draft.generation != self.session.generation:
            return True
        try:
            node = find_node(self.session.report_snapshot(), address)
            return _source(node, address) != draft.original
        except (LookupError, ValueError):
            return True

    def update(self, address: NodeAddress, value: str, *, owner: str = "branch") -> None:
        self._check_owner(address, owner)
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
            self._clear(address)
        else:
            self._store(address, TextDraft(address, original, value, generation, rich), owner)

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
               field: str, value: object, *, paragraph: bool = False,
               owner: str = "branch") -> bool:
        """Stage styling without changing canonical data or undo history."""
        self._check_owner(address, owner)
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
            self._clear(address)
        else:
            self._store(address, TextDraft(
                address, node.text.original, text, self.session.generation, changed), owner)
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

    def table_preview(self, address: NodeAddress) -> tuple[list, bool]:
        """Render an obsolete draft for safe inspection/revert, never for commit.

        A parallel editor may change canonical rows before a queued Qt refresh.
        Rendering must not fail and hide the Revert action. Only table_rows()
        and commit() enforce staleness for actual edits and transactions.
        """
        try:
            return self.table_rows(address), False
        except StaleIntentError:
            draft = self._drafts.get(address)
            if not isinstance(draft, TableDraft):
                raise
            return checked_rows(draft.rows), True

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
                     origins: list[list[tuple[int, int] | None]] | None = None,
                     *, owner: str = "branch") -> bool:
        self._check_owner(address, owner)
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
            self._clear(address)
        else:
            self._store(address, TableDraft(
                address, original, checked_rows(rows), self.session.generation,
                deepcopy(origins) if origins is not None else (
                    deepcopy(previous.origins) if isinstance(previous, TableDraft)
                    else self._origins(original))), owner)
        return True

    def update_cell(self, address: NodeAddress, row: int, column: int,
                    value: str, *, owner: str = "branch") -> bool:
        self._check_owner(address, owner)
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
        return self._stage_table(address, updated, origins=origins, owner=owner)

    def modify_table(self, address: NodeAddress, operation: str, index: int,
                     *, owner: str = "branch") -> bool:
        self._check_owner(address, owner)
        rows = self.table_rows(address)
        previous = self._drafts.get(address)
        origins = (previous.origins if isinstance(previous, TableDraft)
                   else self._origins(rows))
        # New cells use the report's source language, not a neighboring
        # cell's potentially imported language tag.
        updated = change_grid(
            rows, operation, index, self.session.report_snapshot().primary_language)
        return self._stage_table(
            address, updated, origins=self._remap_origins(origins, operation, index),
            owner=owner)

    def discard(self, address: NodeAddress, *, owner: str = "branch"):
        self._check_owner(address, owner)
        self._clear(address)
        return self.table_rows(address) if address.field == "table" else self.text(address)

    def commit_batch(self, addresses, *, owner: str):
        """Atomically apply a document editor's draft fields as ONE undo step.

        Inspect every baseline and owner before executing anything. A failed
        validation/commit retains all original drafts and canonical content.
        """
        keys = tuple(addresses)
        if not keys or len(set(keys)) != len(keys):
            raise ValueError("Editor batch must have distinct pending fields")
        edits = []
        for address in keys:
            self._check_owner(address, owner)
            draft = self._drafts.get(address)
            if draft is None or draft.generation != self.session.generation:
                raise StaleIntentError("Editor batch has a missing or obsolete draft")
            node = find_node(self.session.report_snapshot(), address)
            if isinstance(draft, TextDraft):
                if _source(node, address) != draft.original:
                    raise StaleIntentError("Source changed since editing began; draft preserved")
                if address.field == "title":
                    kind, args = "rename_module", {"title": draft.value}
                elif address.field == "caption":
                    kind, args = "set_photo_caption", {"text": draft.value}
                    address = NodeAddress(address.report_id, address.module_id,
                                          address.block_id, "photo")
                else:
                    kind = ("set_heading_rich" if isinstance(node, HeadingBlock)
                            else "set_paragraph_rich")
                    args = {"text": draft.value,
                            "rich": (deepcopy(draft.rich) if draft.rich is not None
                                     else rebase_rich(draft.original, draft.value, node.rich))}
            elif isinstance(draft, TableDraft):
                if not isinstance(node, TableBlock) or node.rows != draft.original:
                    raise StaleIntentError("Table changed since editing began; draft preserved")
                kind, args = "set_table_rows", {"rows": checked_rows(draft.rows)}
            else:
                raise ValueError("Unsupported editor draft")
            edits.append(CommandIntent(kind, address, args,
                                       self.session.revision, self.session.generation))
        intent = CommandIntent("set_fields_batch", None, {"edits": tuple(edits)},
                               self.session.revision, self.session.generation)
        self._committing = True
        try:
            change = self.gateway.execute(intent)
        finally:
            self._committing = False
        for address in keys:
            self._clear(address)
        return change

    def commit(self, address: NodeAddress, *, owner: str = "branch"):
        self._check_owner(address, owner)
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
        elif address.field == "caption":
            kind, args = "set_photo_caption", {"text": draft.value}
            # Gateway address is photo-owned; draft lookup remains caption-owned.
            address = NodeAddress(address.report_id, address.module_id,
                                  address.block_id, "photo")
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
        self._clear(draft.address)
        return change


@dataclass(frozen=True)
class EditorDraftPort:
    """M3.4 shared-session entry point for a future page Editor tab.

    The page editor does not get an independent report or bypass the command
    gateway. An external caller must explicitly Apply or Revert its owner-tagged
    drafts. Same-field ownership conflicts are rejected before staging.
    """
    coordinator: DraftCoordinator
    owner: str

    def stage_text(self, address: NodeAddress, value: str) -> None:
        self.coordinator.update(address, value, owner=self.owner)

    def stage_format(self, address: NodeAddress, start: int, end: int,
                     field: str, value: object, *, paragraph: bool = False) -> bool:
        return self.coordinator.format(address, start, end, field, value,
                                       paragraph=paragraph, owner=self.owner)

    def stage_cell(self, address: NodeAddress, row: int, column: int,
                   value: str) -> bool:
        return self.coordinator.update_cell(address, row, column, value,
                                             owner=self.owner)

    def stage_grid(self, address: NodeAddress, operation: str, index: int) -> bool:
        return self.coordinator.modify_table(address, operation, index, owner=self.owner)

    def apply(self, address: NodeAddress):
        return self.coordinator.commit(address, owner=self.owner)

    def apply_batch(self, addresses):
        return self.coordinator.commit_batch(addresses, owner=self.owner)

    def revert(self, address: NodeAddress):
        return self.coordinator.discard(address, owner=self.owner)

    def owns(self, address: NodeAddress) -> bool:
        return self.coordinator.draft_owner(address) == self.owner
