"""Pure, testable M2 hierarchical report commands and derived outline.

No Qt, database, browser, network, or document-layout dependencies.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from .model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, Report, TableBlock,
)

MAX_NESTING = 256


@dataclass(frozen=True)
class OutlineEntry:
    number: str
    module_id: str
    title: str
    depth: int
    is_conclusion: bool = False


def validate_report_tree(report: Report) -> None:
    """Reject malformed hierarchy, cyclic objects, duplicate IDs and bad blocks."""
    if not isinstance(report, Report):
        raise ValueError("A Report is required")
    report.__post_init__()  # validate editable report metadata after mutations
    report.ordered_sections()
    if any(isinstance(block, NestedModuleBlock) for block in report.conclusion.blocks):
        raise ValueError("Conclusions cannot contain intervention submodules")
    seen_ids: set[str] = set()
    seen_objects: set[int] = set()
    stack = [(part, 0) for part in reversed(report.ordered_sections())]
    while stack:
        module, depth = stack.pop()
        if depth > MAX_NESTING:
            raise ValueError("Report nesting exceeds safe project depth")
        if not isinstance(module, Module) or not isinstance(module.title, LocalizedText):
            raise ValueError("Invalid module or title")
        if id(module) in seen_objects:
            raise ValueError("Module appears more than once or forms a cycle")
        seen_objects.add(id(module))
        _check_id(module.id, seen_ids)
        if not isinstance(module.blocks, list):
            raise ValueError("Module blocks must be ordered")
        children = []
        for block in module.blocks:
            if not isinstance(block, (ParagraphBlock, HeadingBlock, PhotoBlock,
                                      TableBlock, PageBreakBlock, NestedModuleBlock)):
                raise ValueError("Unsupported report block")
            _check_id(block.id, seen_ids)
            if isinstance(block, (ParagraphBlock, HeadingBlock)) and not isinstance(block.text, LocalizedText):
                raise ValueError("Invalid text block")
            if isinstance(block, HeadingBlock) and (not isinstance(block.level, int) or not 1 <= block.level <= 6):
                raise ValueError("Heading level must be 1..6")
            if isinstance(block, PhotoBlock):
                if not isinstance(block.asset_id, str) or not block.asset_id:
                    raise ValueError("Photo must use a logical asset ID")
                if block.caption is not None and not isinstance(block.caption, LocalizedText):
                    raise ValueError("Invalid photo caption")
            if isinstance(block, TableBlock):
                if not isinstance(block.rows, list) or any(
                    not isinstance(row, list) or any(not isinstance(cell, LocalizedText) for cell in row)
                    for row in block.rows
                ):
                    raise ValueError("Invalid table cells")
            if isinstance(block, NestedModuleBlock):
                children.append((block.module, depth + 1))
        stack.extend(reversed(children))


def _check_id(identifier: str, seen: set[str]) -> None:
    if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
        raise ValueError("Duplicate or invalid report object ID")
    seen.add(identifier)


def module_outline(report: Report) -> tuple[OutlineEntry, ...]:
    """Sole source for both editor navigation and generated table of contents."""
    validate_report_tree(report)
    entries: list[OutlineEntry] = []
    stack = [(m, str(i), 0) for i, m in reversed(list(enumerate(report.modules, 1)))]
    while stack:
        module, number, depth = stack.pop()
        entries.append(OutlineEntry(number, module.id, module.title.original, depth))
        children = [block.module for block in module.blocks if isinstance(block, NestedModuleBlock)]
        stack.extend((child, number + "." + str(i), depth + 1)
                     for i, child in reversed(list(enumerate(children, 1))))
    entries.append(OutlineEntry("", report.conclusion.id,
                                report.conclusion.title.original, 0, True))
    return tuple(entries)


def _find(report: Report, module_id: str):
    """Locate module and its containing list; nested lists contain wrapper blocks."""
    if report.conclusion.id == module_id:
        return None, None, report.conclusion
    stack = [(report.modules, i, module) for i, module in enumerate(report.modules)]
    while stack:
        container, index, module = stack.pop()
        if module.id == module_id:
            return container, index, module
        stack.extend((module.blocks, i, block.module)
                     for i, block in enumerate(module.blocks)
                     if isinstance(block, NestedModuleBlock))
    raise LookupError("Module does not exist")


def _insert_index(container: list, index: int | None) -> int:
    if index is None:
        return len(container)
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index <= len(container):
        raise ValueError("Insertion index is out of range")
    return index


def _fresh_ids(module: Module) -> None:
    stack = [module]
    while stack:
        current = stack.pop()
        current.id = uuid4().hex
        for block in current.blocks:
            block.id = uuid4().hex
            if isinstance(block, NestedModuleBlock):
                stack.append(block.module)


class ProjectEditor:
    """Transactional change/undo/redo stack; unsuccessful edits change nothing."""

    def __init__(self, report: Report, *, history_limit: int = 100) -> None:
        validate_report_tree(report)
        if not isinstance(history_limit, int) or history_limit < 1:
            raise ValueError("History limit must be positive")
        self.report = deepcopy(report)
        self.history_limit = history_limit
        self._undo: list[Report] = []
        self._redo: list[Report] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def apply(self, change: Callable[[Report], None]) -> None:
        candidate = deepcopy(self.report)
        change(candidate)
        validate_report_tree(candidate)
        self._undo.append(self.report)
        del self._undo[:-self.history_limit]
        self.report = candidate
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.report)
        self.report = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.report)
        self.report = self._redo.pop()
        return True

    def add_module(self, module: Module, *, parent_id: str | None = None,
                   index: int | None = None) -> None:
        def operation(report: Report) -> None:
            if parent_id == report.conclusion.id:
                raise ValueError("Intervention modules cannot be added under Conclusions")
            container = report.modules if parent_id is None else _find(report, parent_id)[2].blocks
            item = deepcopy(module) if parent_id is None else NestedModuleBlock(deepcopy(module))
            container.insert(_insert_index(container, index), item)
        self.apply(operation)

    def remove_module(self, module_id: str) -> None:
        def operation(report: Report) -> None:
            container, index, _ = _find(report, module_id)
            if container is None:
                raise ValueError("Conclusions cannot be deleted")
            container.pop(index)
        self.apply(operation)

    def rename_module(self, module_id: str, title: str) -> None:
        def operation(report: Report) -> None:
            _find(report, module_id)[2].title.update_original(title)
        self.apply(operation)

    def move_module(self, module_id: str, *, parent_id: str | None = None,
                    index: int | None = None) -> None:
        def operation(report: Report) -> None:
            container, old_index, module = _find(report, module_id)
            if container is None:
                raise ValueError("Conclusions cannot be moved")
            descendant_ids = {entry.module_id for entry in module_outline(
                Report(customer_id=report.customer_id, customer_snapshot=report.customer_snapshot,
                       start_date=report.start_date, end_date=report.end_date,
                       primary_language=report.primary_language,
                       output_languages=list(report.output_languages),
                       conclusion=Module(LocalizedText(report.primary_language, "Conclusion")),
                       modules=[module])) if not entry.is_conclusion}
            if parent_id in descendant_ids:
                raise ValueError("Cannot move a module under itself or its descendants")
            if parent_id is not None and parent_id == report.conclusion.id:
                raise ValueError("Conclusions may not contain intervention modules")
            target = report.modules if parent_id is None else _find(report, parent_id)[2].blocks
            at = _insert_index(target, index)
            container.pop(old_index)
            if container is target and at > old_index:
                at -= 1
            target.insert(at, module if parent_id is None else NestedModuleBlock(module))
        self.apply(operation)

    def duplicate_module(self, module_id: str) -> str:
        new_id = uuid4().hex
        def operation(report: Report) -> None:
            container, index, module = _find(report, module_id)
            if container is None:
                raise ValueError("Cannot duplicate the dedicated Conclusions")
            cloned = deepcopy(module)
            _fresh_ids(cloned)
            cloned.id = new_id
            container.insert(index + 1,
                             cloned if container is report.modules else NestedModuleBlock(cloned))
        self.apply(operation)
        return new_id

    def add_block(self, module_id: str, block, *, index: int | None = None) -> None:
        def operation(report: Report) -> None:
            container = _find(report, module_id)[2].blocks
            container.insert(_insert_index(container, index), deepcopy(block))
        self.apply(operation)

    def remove_block(self, module_id: str, block_id: str) -> None:
        def operation(report: Report) -> None:
            container = _find(report, module_id)[2].blocks
            for i, block in enumerate(container):
                if block.id == block_id:
                    container.pop(i)
                    return
            raise LookupError("Block does not exist")
        self.apply(operation)

    def move_block(self, source_module_id: str, block_id: str,
                   target_module_id: str, *, index: int | None = None) -> None:
        def operation(report: Report) -> None:
            source = _find(report, source_module_id)[2].blocks
            target = _find(report, target_module_id)[2].blocks
            old_index = next((i for i, block in enumerate(source)
                              if block.id == block_id), None)
            if old_index is None:
                raise LookupError("Block does not exist")
            at = _insert_index(target, index)
            block = source.pop(old_index)
            if source is target and at > old_index:
                at -= 1
            target.insert(at, block)
        self.apply(operation)
