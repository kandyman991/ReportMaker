"""Synthetic, deterministically sized canonical V2 report benchmark fixtures."""
from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path

from reportmaker.model import (Report, Module, LocalizedText, ParagraphBlock, HeadingBlock,
                              PhotoBlock, TableBlock, NestedModuleBlock)
from reportmaker.reference import manual_snapshot
from reportmaker.project_io import ReportProject
from reportmaker.engine import validate_report_tree
from reportmaker.v2.projections import project_branch

SIZES = (82, 302, 802)

def project(rows: int) -> ReportProject:
    if rows < 7 or (rows - 2) % 5:
        raise ValueError("Expected 5*n+2 rows, e.g. 82, 302, 802")
    modules = []
    for i in range((rows - 2) // 5):
        leaf = lambda text: LocalizedText("en", text)
        blocks = [
            ParagraphBlock(leaf(f"Synthetic inspection notes {i}, edited inline")),
            PhotoBlock("sample-image", leaf(f"Fabricated caption {i}")),
            TableBlock([[leaf("Measurement"), leaf(str(i))]]),
        ]
        if i % 5 == 0:
            blocks.append(NestedModuleBlock(Module(leaf(f"Nested inspection {i}"))))
        else:
            blocks.append(HeadingBlock(leaf(f"Heading {i}")))
        modules.append(Module(leaf(f"Inspection module {i:03d}"), blocks))
    report = Report(
        customer_id=None, customer_snapshot=manual_snapshot("Synthetic benchmark customer"),
        start_date=date(2026, 10, 28), end_date=date(2026, 10, 28),
        primary_language="en", output_languages=["en"], modules=modules,
        conclusion=Module(LocalizedText("en", "Conclusions")),
    )
    validate_report_tree(report)
    result = ReportProject(report, {"sample-image": b"synthetic-placeholder-bytes"})
    if len(project_branch(report)) != rows:
        raise AssertionError("Generated incorrect row count")
    return result

def projection(rows: int) -> list[dict]:
    from reportmaker.v2.branch.canvas import _branch_rows
    report = project(rows).report
    source = project_branch(report)
    rendered = tuple(_branch_rows(report))
    return [{
        "id": meta.stable_id,
        "kind": meta.kind,
        "parentId": meta.parent_module_id,
        "depth": meta.depth,
        "text": item[3],
        "title": item[2],
    } for item, meta in zip(rendered, source)]

def export(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        (root / f"{size}.json").write_text(json.dumps(projection(size)), encoding="utf-8")
    print("Generated canonical projections:", ", ".join(str(x) for x in SIZES))

if __name__ == "__main__":
    export(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data")
