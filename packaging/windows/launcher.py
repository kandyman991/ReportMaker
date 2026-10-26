"""Entry point for PyInstaller; keep reportmaker as an importable package."""

from reportmaker.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
