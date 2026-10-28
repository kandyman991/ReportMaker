"""Uncommitted inline text lives outside the canonical report.

The only way to persist a draft is through M1.2's validated CommandGateway.
Unresolved drafts block ordinary commands, Undo/Redo, Save and project switches.
Separate fields may be drafted concurrently, but a commit checks that the
specific canonical source field has not changed since its draft began.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model import Module, ParagraphBlock
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


def _source(node, address: NodeAddress) -> str:
    if address.field == "title" and address.block_id is None and isinstance(node, Module):
        return node.title.original
    if address.field == "text" and address.block_id is not None and isinstance(node, ParagraphBlock):
        return node.text.original
    raise ValueError("Only module titles and paragraph text can be edited inline")


class DraftCoordinator:
    """Guard multiple independent drafts without creating a parallel model."""

    def __init__(self, session: ReportSession, gateway: CommandGateway) -> None:
        self.session = session
        self.gateway = gateway
        self._drafts: dict[NodeAddress, TextDraft] = {}
        self._committing = False
        session.set_draft_guard(lambda: not self._drafts or self._committing)

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
        else:
            original, generation = old.original, old.generation
        if generation != self.session.generation:
            raise StaleIntentError("Draft belongs to a previous report")
        if value == original:
            self._drafts.pop(address, None)
        else:
            self._drafts[address] = TextDraft(address, original, value, generation)

    def discard(self, address: NodeAddress) -> str:
        self._drafts.pop(address, None)
        return self.text(address)

    def commit(self, address: NodeAddress):
        draft = self._drafts.get(address)
        if draft is None:
            return None
        if draft.generation != self.session.generation:
            raise StaleIntentError("Draft belongs to a previous report")
        node = find_node(self.session.report_snapshot(), address)
        if _source(node, address) != draft.original:
            raise StaleIntentError("Source changed since editing began; draft preserved")
        if address.field == "title":
            kind, args = "rename_module", {"title": draft.value}
        else:
            kind = "set_paragraph_rich"
            args = {"text": draft.value,
                    "rich": rebase_rich(draft.original, draft.value, node.rich)}
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
