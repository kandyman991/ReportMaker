"""Render exact canonical 33-case physical Windows acceptance checklist (never mark passed)."""
import argparse
from pathlib import Path

from validate_windows_physical_acceptance import required_cases


def render() -> str:
    cases = required_cases()
    lines = [
        "# ReportMaker V2 — physical installed-Windows manual test checklist",
        "",
        "**All 33 cases remain PENDING until run on a real Windows PC.**",
        "Do not use customer data. Confirm V1 stays installed. Record signed/unsigned status,",
        "the exact installer SHA-256, source SHA, hardware model and Windows version.",
        "",
        "Hardware model: __________  Windows build: __________  Tester: __________",
        "Source SHA: __________  Installer SHA-256: __________  UTC test date: __________",
        "",
        "For each case capture a synthetic screenshot, video or detailed log; calculate",
        "its SHA-256. The separate evidence validator requires a matching JSON record.",
        "",
    ]
    for id_, description in cases.items():
        lines.extend((f"## {id_} — {description}", "",
                      "- [ ] Performed physically on installed Windows app",
                      "- Observed result: __________",
                      "- Screenshot/video/log file: __________",
                      "- Evidence SHA-256: __________",
                      "- Defect/issue reference (if applicable): __________", ""))
    lines.extend(("**STOP:** A failed/missing case is a release blocker, not a waiver.",
                  "Evidence completion must be independently reviewed.", ""))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("Refusing to overwrite an existing acceptance checklist")
    args.output.write_text(render(), encoding="utf-8")
    print(f"Created 33-case PENDING checklist: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
