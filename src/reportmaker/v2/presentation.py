"""Local-only V2 canvas state, never written into project archives.

The identity contains a hashed absolute project path and stable report ID.
Save/Save As migrate view state only after an archive write succeeds.
Report wording, photographs, browser data and customer snapshots are excluded.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

from PySide6.QtCore import QSettings

from .projections import project_branch
from .session import ReportSession


class PresentationStore:
    """M1.4 minimal selection/scroll state; M2 adds collapse and expansion."""

    _PREFIX = "presentation/v1/"

    def __init__(self, settings: QSettings | None = None) -> None:
        self.settings = settings if settings is not None else QSettings(
            "ReportMaker", "ReportMaker V2"
        )

    @classmethod
    def identity(cls, report_id: str, path: Path | None) -> str:
        location = ("unsaved" if path is None else
                    "path:" + os.path.normcase(os.path.abspath(path)))
        encoded = (report_id + "\0" + location).encode("utf-8")
        return cls._PREFIX + sha256(encoded).hexdigest()

    def key_for(self, session: ReportSession) -> str:
        return self.identity(session.report_snapshot().id, session.path)

    def write(self, key: str, selected: str | None, scroll: int) -> None:
        if not key.startswith(self._PREFIX):
            raise ValueError("Unrecognized presentation identity")
        if selected is not None and not isinstance(selected, str):
            raise ValueError("Selection must be a stable module ID")
        if type(scroll) is not int or scroll < 0:
            raise ValueError("Scroll position must be non-negative")
        self.settings.setValue(key, json.dumps({
            "selected": selected, "scroll": min(scroll, 1_000_000),
        }, sort_keys=True))

    def load(self, session: ReportSession) -> tuple[str | None, int]:
        raw = self.settings.value(self.key_for(session))
        if not isinstance(raw, str):
            return None, 0
        try:
            record = json.loads(raw)
            if not isinstance(record, dict) or set(record) != {"selected", "scroll"}:
                return None, 0
            selected = record["selected"]
            scroll = record["scroll"]
            if selected is not None and not isinstance(selected, str):
                return None, 0
            if type(scroll) is not int or not 0 <= scroll <= 1_000_000:
                return None, 0
            # Never restore an ID from another report or a stale subtree.
            valid = {row.stable_id for row in project_branch(session.report_snapshot())
                     if row.kind in ("module", "conclusion")}
            return (selected if selected in valid else None), scroll
        except (ValueError, TypeError):
            return None, 0
