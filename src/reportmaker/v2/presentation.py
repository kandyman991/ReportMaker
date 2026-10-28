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
    """Device-local selection, scroll and collapse state keyed to report/path."""

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

    def write(self, key: str, selected: str | None, scroll: int,
              *, collapsed: frozenset[str] = frozenset()) -> None:
        if not key.startswith(self._PREFIX):
            raise ValueError("Unrecognized presentation identity")
        if selected is not None and not isinstance(selected, str):
            raise ValueError("Selection must be a stable module ID")
        if type(scroll) is not int or scroll < 0:
            raise ValueError("Scroll position must be non-negative")
        if not isinstance(collapsed, frozenset) or any(
                not isinstance(item, str) or not item for item in collapsed):
            raise ValueError("Collapsed state must contain stable module IDs")
        self.settings.setValue(key, json.dumps({
            "selected": selected, "scroll": min(scroll, 1_000_000),
            "collapsed": sorted(collapsed),
        }, sort_keys=True))

    def load_view(self, session: ReportSession) -> tuple[str | None, int, frozenset[str]]:
        """Read legacy M1.4 state and prune unknown/removed stable IDs."""
        raw = self.settings.value(self.key_for(session))
        if not isinstance(raw, str):
            return None, 0, frozenset()
        try:
            record = json.loads(raw)
            if not isinstance(record, dict) or set(record) not in (
                    {"selected", "scroll"}, {"selected", "scroll", "collapsed"}):
                return None, 0, frozenset()
            selected, scroll = record["selected"], record["scroll"]
            collapsed = record.get("collapsed", [])
            if selected is not None and not isinstance(selected, str):
                return None, 0, frozenset()
            if type(scroll) is not int or not 0 <= scroll <= 1_000_000:
                return None, 0, frozenset()
            if (not isinstance(collapsed, list) or
                    any(not isinstance(x, str) or not x for x in collapsed)):
                return None, 0, frozenset()
            valid = {row.stable_id for row in project_branch(session.report_snapshot())
                     if row.kind in ("module", "conclusion")}
            return ((selected if selected in valid else None), scroll,
                    frozenset(collapsed) & valid)
        except (ValueError, TypeError):
            return None, 0, frozenset()

    def load(self, session: ReportSession) -> tuple[str | None, int]:
        """Backward-compatible M1.4 selection/scroll access."""
        selected, scroll, _ = self.load_view(session)
        return selected, scroll
