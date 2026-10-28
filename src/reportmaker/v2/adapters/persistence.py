"""Safe .rmproj v4 storage adapter: no new serializer or automatic migrations.

Opening parses into a detached ReportProject before a session is replaced.
Saves use the existing atomic archive writer; provenance changes only after a
successful write, and older project sources remain untouched.
"""
from __future__ import annotations

import os
from pathlib import Path

from ...project_io import ReportProject, VERSION, load_project, save_project
from ..session import ReportSession


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


class ProjectPersistence:
    def open(self, path: str | Path) -> ReportProject:
        return load_project(path)

    def open_into(self, session: ReportSession, path: str | Path,
                  *, discard_unsaved: bool = False) -> None:
        # Uncommitted drafts and invalid/untrusted files cannot replace the
        # active project. No mutation occurs until both checks succeed.
        session.require_clean_drafts()
        candidate = self.open(path)
        session.replace_project(candidate, discard_unsaved=discard_unsaved)

    def save(self, session: ReportSession, path: str | Path | None = None) -> Path:
        session.require_clean_drafts()
        current = session.path
        if current is not None and session.loaded_version != VERSION:
            raise ValueError("Legacy projects require Save As to a different destination")
        if path is None and current is None:
            raise ValueError("First Save requires a destination")
        target = Path(path) if path is not None else current
        if current is not None and not _same_path(target, current):
            raise ValueError("Use Save As when changing the project path")
        if current is None and target.exists():
            raise FileExistsError("First Save cannot silently overwrite an existing file")
        revision = session.revision
        saved = save_project(session.project_snapshot(), target)
        session._mark_saved(saved, revision)
        return saved

    def save_as(self, session: ReportSession, target: str | Path,
                *, overwrite: bool = False) -> Path:
        session.require_clean_drafts()
        destination = Path(target)
        if session.path is not None and _same_path(destination, session.path):
            raise ValueError("Save As requires a different destination")
        if destination.exists() and not overwrite:
            raise FileExistsError("Confirm overwrite before Save As")
        revision = session.revision
        saved = save_project(session.project_snapshot(), destination)
        session._mark_saved(saved, revision)
        return saved
