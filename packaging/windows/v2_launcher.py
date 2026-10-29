"""Standalone PyInstaller entry point for the V2 *preview* application.

Never import the legacy `reportmaker.__main__` launcher here: M7 must not
silently distribute the V1 UI or replace its per-user installation.
"""
from reportmaker.v2.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
