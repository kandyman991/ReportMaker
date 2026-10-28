"""Typed V2 command gateway around the existing, transactional ProjectEditor.

No view widget receives ProjectEditor or its mutable Report. Each successful
intent is one logical undo step; stale/malformed intents never reach apply().
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping
from uuid import uuid4

from ..model import HeadingBlock, LocalizedText, Module, ParagraphBlock
from ..rich_text import RichFormatting, validate_rich
from .projections import NodeAddress, find_node
from .session import ReportSession, StaleIntentError
from .structure import plan_drop, structural_node


@dataclass(frozen=True)
class CommandIntent:
    kind: str
    target: NodeAddress | None
    args: Mapping[str, object]
    expected_revision: int
    project_generation: str


@dataclass(frozen=True)
class ChangeSet:
    revision: int
    changed_ids: frozenset[str]
    structure_changed: bool = False
    assets_changed: bool = False
    outline_invalidated: bool = False


_KINDS = {
    "add_module": ({"title"}, {"index"}),
    "add_nested_module": ({"title"}, {"index"}),
    "add_paragraph": ({"text"}, {"index"}),
    "add_heading": ({"text", "level"}, {"index"}),
    "rename_module": ({"title"}, set()),
    "set_paragraph": ({"text"}, set()),
    "set_paragraph_rich": ({"text", "rich"}, set()),
    "set_heading_rich": ({"text", "rich"}, set()),
    "move_node": ({"anchor", "position"}, set()),
    "duplicate_node": (set(), set()),
    "delete_node": (set(), set()),
}


class CommandGateway:
    def __init__(self, session: ReportSession) -> None:
        self._session = session

    def _check_generation(self, generation: str) -> None:
        if generation != self._session.generation:
            raise StaleIntentError("Action belongs to a previous report session")

    def validate(self, intent: CommandIntent) -> None:
        if not isinstance(intent, CommandIntent) or intent.kind not in _KINDS:
            raise ValueError("Unsupported V2 command")
        self._check_generation(intent.project_generation)
        if type(intent.expected_revision) is not int or intent.expected_revision != self._session.revision:
            raise StaleIntentError("Action was based on an outdated report revision")
        if not isinstance(intent.args, Mapping):
            raise ValueError("Command arguments must be a mapping")
        required, optional = _KINDS[intent.kind]
        if set(intent.args) - required - optional or not required <= set(intent.args):
            raise ValueError("Unsupported command arguments")
        if intent.kind == "move_node":
            plan_drop(self._session.report_snapshot(), intent.target,
                      intent.args["anchor"], intent.args["position"])
            return
        if intent.kind in ("duplicate_node", "delete_node"):
            structural_node(self._session.report_snapshot(), intent.target)
            return
        value_key = "text" if intent.kind in ("add_paragraph", "add_heading", "set_paragraph", "set_paragraph_rich", "set_heading_rich") else "title"
        if not isinstance(intent.args[value_key], str):
            raise ValueError("Title and text must be strings")
        if intent.kind == "add_heading" and (type(intent.args["level"]) is not int
                                             or not 1 <= intent.args["level"] <= 6):
            raise ValueError("Heading level must be 1..6")
        if intent.kind in ("set_paragraph_rich", "set_heading_rich"):
            if not isinstance(intent.args["rich"], RichFormatting):
                raise ValueError("An explicit rich formatting value is required")
            validate_rich(intent.args["rich"], intent.args["text"])
        if "index" in intent.args and (type(intent.args["index"]) is not int or intent.args["index"] < 0):
            raise ValueError("Mixed insertion index must be a non-negative integer")
        report = self._session.report_snapshot()
        if intent.kind == "add_module":
            if intent.target is not None:
                raise ValueError("Top-level module insertion has no target")
            size = len(report.modules)
        else:
            addr = intent.target
            if not isinstance(addr, NodeAddress) or addr.report_id != report.id:
                raise ValueError("Action must address the active report")
            if intent.kind in ("set_paragraph", "set_paragraph_rich", "set_heading_rich"):
                if addr.field != "text" or addr.block_id is None:
                    raise ValueError("Text edit requires a block text address")
                block = find_node(report, addr)
                expected = HeadingBlock if intent.kind == "set_heading_rich" else ParagraphBlock
                if not isinstance(block, expected):
                    raise ValueError("Wrong block kind for text edit")
            else:
                if addr.block_id is not None or addr.field != "title":
                    raise ValueError("Command requires a module address")
                module = find_node(report, addr)
                if not isinstance(module, Module):
                    raise ValueError("Target is not a module")
                if intent.kind == "add_nested_module" and module.id == report.conclusion.id:
                    raise ValueError("Conclusions cannot have intervention submodules")
                size = len(module.blocks)
        if intent.kind in ("add_module", "add_nested_module", "add_paragraph", "add_heading"):
            if "index" in intent.args and intent.args["index"] > size:
                raise ValueError("Mixed insertion index exceeds parent length")

    def execute(self, intent: CommandIntent) -> ChangeSet | None:
        self.validate(intent)
        self._session.require_clean_drafts()
        # Freeze inputs before mutating the canonical data; arbitrary UI-provided
        # callables/fields never enter the transaction.
        kind, args, address = intent.kind, dict(intent.args), intent.target
        editor = self._session._editor
        if kind == "move_node":
            plan = plan_drop(editor.report, address, args["anchor"], args["position"])
            if plan.noop:
                return None  # Preserve redo, revision and listeners on a no-op.
            if plan.source_kind == "module":
                editor.move_module(plan.source_id, parent_id=plan.destination_parent_id,
                                   index=plan.destination_index)
            else:
                if plan.source_parent_id is None or plan.destination_parent_id is None:
                    raise ValueError("Content needs an owning module")
                editor.move_block(plan.source_parent_id, plan.source_id,
                                  plan.destination_parent_id,
                                  index=plan.destination_index)
            change = ChangeSet(self._session.revision + 1,
                               frozenset({plan.source_id}), True, False, True)
            self._session._publish(change)
            return change
        if kind in ("duplicate_node", "delete_node"):
            node = structural_node(editor.report, address)
            if kind == "delete_node":
                if node.kind == "module":
                    editor.remove_module(node.stable_id)
                else:
                    editor.remove_block(node.parent_module_id, node.stable_id)
                changed_id = node.stable_id
            elif node.kind == "module":
                changed_id = editor.duplicate_module(node.stable_id)
            else:
                changed_id = uuid4().hex

                def duplicate_block(report):
                    owner = find_node(report, NodeAddress(report.id, node.parent_module_id))
                    at = next(i for i, block in enumerate(owner.blocks)
                              if block.id == node.stable_id)
                    copy = deepcopy(owner.blocks[at])
                    copy.id = changed_id
                    owner.blocks.insert(at + 1, copy)

                editor.apply(duplicate_block)
            change = ChangeSet(self._session.revision + 1,
                               frozenset({changed_id}), True, False, True)
            self._session._publish(change)
            return change
        # An unchanged inline commit must not add a history step, invalidate
        # queued edits, or erase the redo stack after an Undo.
        if kind == "rename_module" and find_node(editor.report, address).title.original == args["title"]:
            return None
        if kind == "set_paragraph":
            current = find_node(editor.report, address)
            if current.text.original == args["text"]:
                return None
            # The legacy plain-text command has no formatting remap data.
            # Reject edits to formatted sources even when the new text has
            # the same length: otherwise old offsets can style wrong letters.
            # Inline editors must use the atomic set_paragraph_rich command.
            if current.rich.runs or current.rich.paragraphs:
                raise ValueError("Formatted paragraphs require set_paragraph_rich")
        if kind in ("set_paragraph_rich", "set_heading_rich"):
            current = find_node(editor.report, address)
            if current.text.original == args["text"] and current.rich == args["rich"]:
                return None
        language = editor.report.primary_language
        changed_id: str
        structure = kind in ("add_module", "add_nested_module", "add_paragraph", "add_heading")
        if kind in ("add_module", "add_nested_module"):
            module = Module(LocalizedText(language, args["title"]))
            if kind == "add_module":
                editor.add_module(module, index=args.get("index"))
            else:
                editor.add_module(module, parent_id=address.module_id, index=args.get("index"))
            changed_id = module.id
        elif kind == "add_paragraph":
            paragraph = ParagraphBlock(LocalizedText(language, args["text"]))
            editor.add_block(address.module_id, paragraph, index=args.get("index"))
            changed_id = paragraph.id
        elif kind == "add_heading":
            heading = HeadingBlock(LocalizedText(language, args["text"]), level=args["level"])
            editor.add_block(address.module_id, heading, index=args.get("index"))
            changed_id = heading.id
        elif kind == "rename_module":
            editor.rename_module(address.module_id, args["title"])
            changed_id = address.module_id
        elif kind in ("set_paragraph_rich", "set_heading_rich"):
            # Native text widgets supply a detached rich record; one transaction
            # updates wording, provenance, and offsets without a shadow model.
            rich = deepcopy(args["rich"])
            def edit(report):
                block = find_node(report, address)
                block.text.update_original(args["text"])
                block.rich = rich
                validate_rich(block.rich, block.text.original)
            editor.apply(edit)
            changed_id = address.block_id
        elif kind == "set_paragraph":
            def edit(report):
                paragraph = find_node(report, address)
                # Never silently discard existing rich typography. The M1.3
                # text adapter will supply a coherent text+rich transaction.
                paragraph.text.update_original(args["text"])
                validate_rich(paragraph.rich, paragraph.text.original)
            editor.apply(edit)
            changed_id = address.block_id
        else:
            raise ValueError("Unsupported V2 command")
        change = ChangeSet(
            self._session.revision + 1, frozenset({changed_id}), structure,
            False, structure or kind == "rename_module",
        )
        self._session._publish(change)
        return change

    def undo(self, expected_generation: str, expected_revision: int) -> ChangeSet | None:
        self._check_generation(expected_generation)
        if type(expected_revision) is not int or expected_revision != self._session.revision:
            raise StaleIntentError("Undo was based on an outdated report revision")
        self._session.require_clean_drafts()
        if not self._session._editor.undo():
            return None
        change = ChangeSet(self._session.revision + 1,
                           frozenset({self._session._editor.report.id}),
                           True, False, True)
        self._session._publish(change)
        return change

    def redo(self, expected_generation: str, expected_revision: int) -> ChangeSet | None:
        self._check_generation(expected_generation)
        if type(expected_revision) is not int or expected_revision != self._session.revision:
            raise StaleIntentError("Redo was based on an outdated report revision")
        self._session.require_clean_drafts()
        if not self._session._editor.redo():
            return None
        change = ChangeSet(self._session.revision + 1,
                           frozenset({self._session._editor.report.id}),
                           True, False, True)
        self._session._publish(change)
        return change
