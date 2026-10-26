# Independent review of PR #5 — M1 customer storage and Qt manager

Date: 2026-10-26. Repository: `kandyman991/ReportMaker` (public).
Review source: [PR #5](https://github.com/kandyman991/ReportMaker/pull/5) at **`20f74d48009b8669a43a793397852d4d8f6b168a`**. Source branch: `feature/m1-customer-site-machine-database`. Corrections are isolated on `review/pr5-m1-storage-ui-fixes` targeting that feature branch, not `main`. Code-and-tests correction commit before this note: **`f20c998e4338f6b295ff4f3204cecc59c8675675`**.

## Findings and corrections

- **PR5-F01 / High — False-success SQLite backup**: `backup(":memory:")` was accepted with a file-backed source; `target.open("xb")` created an empty file, then `sqlite3.connect(":memory:")` backed up to transient RAM instead of writing the file. The function reported success for an unusable backup. Reject the reserved SQLite filename before opening the target. Add regression test.
- **PR5-F02 / Medium — Search broadens user-entered patterns**: `list_customers("%")` and `list_customers("_")` returned unrelated customers because literal search input was passed to SQL LIKE. Escape `!`, `%`, `_` consistently for all nine filters, using `ESCAPE '!'`. Add literal matching regression tests.
- **PR5-F03 / Medium — Noncanonical intervention dates undermine SQL ordering**: Python `date.fromisoformat` accepts compact/week-based dates in addition to `YYYY-MM-DD`, while SQLite checks/order use string comparison. Require canonical ISO dates for start/end before insertion. Add regression tests.
- **PR5-F04 / Medium — GUI write errors treated as successful operations**: `_safe` returned `None` both on failed operations and on successful `update`/`delete` (void methods), so the edit operation refreshed even on error, potentially discarding user context, and deletion refreshed unconditionally. Use an explicit success marker for void operations; refresh only when successful. Include a Qt smoke regression for failed edit.
- **PR5-F05 / Medium — SQLite open errors not caught by shell**: `MainWindow._open_customers` caught `OSError`, `RuntimeError` and `ValueError` but omitted `sqlite3.Error`; a locked/corrupt DB could propagate out of a Qt toolbar callback. Catch SQLite errors and display the local error dialog. Add offline Qt smoke regression.

## Review scope and project constraints

Examined `AGENTS.md`, `ARCHITECTURE.md`, the curated handoff/checkpoints, the PR diff, `storage.py`, `reference.py`, `customer_ui.py`, `customer_probe.py`, and relevant model/tests. No online AI integration, customer data or credentials are introduced. All tests are synthetic. Existing reference snapshot design remains unchanged; no merger, deployment or installer publication is authorized.

**CI evidence**: Original PR #5 head had completed successful M1 Windows Qt smoke, M0 architecture, and continuity runs. Correction PR checks must be evaluated at the precise correction-PR head after publication; do not treat old PR CI as proof that these new changes passed.

**Remaining risks**: Installed-user-PC Windows form, DPI and accessibility checks, backup recovery testing and installer acceptance have not been independently performed. SQL backup is not encrypted; backup destinations are user-selected local files. Current `main` has advanced with the merged PR #6 report-composition contract since PR #5 branched, so reconciliation before any integration needs separate review. Full report/project persistence and DOCX output remain later milestones.
