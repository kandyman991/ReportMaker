"""Pure V2 report session: one canonical editor, no Qt, no second document tree.

Report copies returned to callers are detached. Only CommandGateway uses the
private ProjectEditor. UI-facing listeners receive revision markers, not models.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Callable
from uuid import uuid4

from ..engine import ProjectEditor
from ..project_io import ReportProject, VERSION, _assets_checked


class PendingDraftError(RuntimeError):
    """Save/Open would lose an unresolved edit from a future UI coordinator."""


class StaleIntentError(RuntimeError):
    """An action refers to an obsolete revision or project generation."""


class UnsavedChangesError(RuntimeError):
    """A project switch would discard unsaved canonical report edits."""


class ReportSession:
    def __init__(self, project: ReportProject) -> None:
        self._listeners: list[Callable[[object], None]] = []
        self._draft_guard: Callable[[], bool] = lambda: True
        self._install(project)

    def _install(self, project: ReportProject) -> None:
        # Validate *before* replacing an existing session. This also detects
        # dangling project-owned media references and invalid snapshots.
        _assets_checked(project)
        editor = ProjectEditor(project.report)
        assets = dict(project.assets)
        library = dict(project.media_library)
        version = project.loaded_version
        path = Path(project.loaded_from).absolute() if project.loaded_from is not None else None
        if type(version) is not int or not 1 <= version <= VERSION:
            raise ValueError("Unsupported source project version")
        self._editor = editor
        self._assets = assets
        self._library = library
        self._loaded_version = version
        self._path = path
        self._generation = uuid4().hex
        self._revision = 0
        self._saved_revision: int | None = 0 if path is not None else None
        self._saved_report = deepcopy(editor.report) if path is not None else None
        # Asset dictionaries contain immutable bytes; snapshots share the bytes,
        # not a mutable media library. Keep this ledger aligned with ProjectEditor
        # history so import+placement is undone/redone as ONE transaction.
        self._last_media = (dict(assets), dict(library))
        self._media_undo: list[tuple[dict[str, bytes], dict[str, str]]] = []
        self._media_redo: list[tuple[dict[str, bytes], dict[str, str]]] = []
        self._saved_media = (dict(assets), dict(library)) if path is not None else None

    @property
    def generation(self) -> str:
        return self._generation

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def loaded_version(self) -> int:
        return self._loaded_version

    @property
    def dirty(self) -> bool:
        if self._saved_revision == self._revision:
            return False
        # Undo can return to the exact saved report while the revision token
        # must keep increasing to reject queued stale commands.
        return (self._saved_report is None or self._editor.report != self._saved_report
                or self._saved_media != (self._assets, self._library))

    @property
    def assets(self):
        # The mapping cannot be mutated through the view; bytes are immutable.
        return MappingProxyType(dict(self._assets))

    @property
    def media_library(self):
        return MappingProxyType(dict(self._library))

    def report_snapshot(self):
        return deepcopy(self._editor.report)

    def project_snapshot(self) -> ReportProject:
        return ReportProject(
            self.report_snapshot(), dict(self._assets), dict(self._library),
            self._loaded_version, self._path,
        )

    def set_draft_guard(self, guard: Callable[[], bool]) -> None:
        if not callable(guard):
            raise TypeError("Draft guard must be callable")
        self._draft_guard = guard

    def require_clean_drafts(self) -> None:
        if not self._draft_guard():
            raise PendingDraftError("Resolve pending edits before changing or saving a project")

    def replace_project(self, project: ReportProject, *, discard_unsaved: bool = False) -> None:
        """Switch projects only after explicit consent to discard unsaved edits."""
        self.require_clean_drafts()
        if type(discard_unsaved) is not bool:
            raise TypeError("discard_unsaved must be a boolean")
        if self.dirty and not discard_unsaved:
            raise UnsavedChangesError("Save the current report or confirm discarding changes")
        replacement = ReportSession(project)  # fully validated first
        self._editor = replacement._editor
        self._assets = replacement._assets
        self._library = replacement._library
        self._loaded_version = replacement._loaded_version
        self._path = replacement._path
        self._generation = replacement._generation
        self._revision = 0
        self._saved_revision = replacement._saved_revision
        self._saved_report = replacement._saved_report
        self._saved_media = replacement._saved_media
        self._last_media = replacement._last_media
        self._media_undo.clear()
        self._media_redo.clear()
        self._notify(None)  # generation changed; all prior addresses are stale

    def subscribe(self, callback: Callable[[object], None]):
        if not callable(callback):
            raise TypeError("Listener must be callable")
        self._listeners.append(callback)

        def unsubscribe():
            if callback in self._listeners:
                self._listeners.remove(callback)
        return unsubscribe

    def _notify(self, change) -> None:
        # Listener exceptions must not masquerade as failed/rolled-back edits.
        import logging
        for callback in tuple(self._listeners):
            try:
                callback(change)
            except Exception:
                logging.getLogger(__name__).exception("V2 revision listener failed")

    def _publish(self, change, *, history: str = "forward") -> None:
        if history == "forward":
            self._media_undo.append(self._last_media)
            del self._media_undo[:-self._editor.history_limit]
            self._media_redo.clear()
        elif history == "undo":
            if not self._media_undo:
                raise RuntimeError("Media undo ledger is out of sync")
            self._media_redo.append((self._assets, self._library))
            self._assets, self._library = self._media_undo.pop()
        elif history == "redo":
            if not self._media_redo:
                raise RuntimeError("Media redo ledger is out of sync")
            self._media_undo.append((self._assets, self._library))
            self._assets, self._library = self._media_redo.pop()
        else:
            raise ValueError("Unsupported history direction")
        self._last_media = (dict(self._assets), dict(self._library))
        self._revision += 1
        self._notify(change)

    def _mark_saved(self, target: Path, expected_revision: int) -> None:
        # Archive save succeeds before source identity or dirty state changes.
        if expected_revision != self._revision:
            raise StaleIntentError("Project changed during save")
        self._path = Path(target).absolute()
        self._loaded_version = VERSION
        self._saved_revision = self._revision
        self._saved_report = deepcopy(self._editor.report)
        self._saved_media = (dict(self._assets), dict(self._library))
