# ReportMaker — reviewed development checkpoints
_Updated 2026-10-26. Maintainers edit this file at PR, milestone and chat-handoff boundaries._

## CP-000 — Continuity system installed
- Scope: project documentation, ADR-0005, validation gates, GitHub-hosted mechanical state updates. **No application code**, no merge of M0 PR #1/#3.
- Status: continuity-only bootstrap; check the **live** main branch and workflow before asserting state freshness.
- Privacy: synthetic-only content; no CAD/customer material, screenshots of accounts, browser cookies or credentials.
- Recovery: start from CHAT_HANDOFF.md + handoff/state.json, then read live PR refs and compare exact SHAs.

## CP-M0 — Windows prototype / deferred final acceptance
- M0 PR history: PR #1 began at 4c6fff52bafd3f755888f46f321efb7b17b3e62e; stacked PR #3 passed Windows checks at b1cf60870b96f13706437567bad249a278e665b8 and was merged into foundation at 4846e27ed45e2ebb53ca16f51e985883305b9ddd. Main integration/CI must be verified against live exact head.
- Functionality seen in user-supplied Windows screenshots: installed GUI, three columns, manual scratchpad, embedded full-height ChatGPT website with logged-in conversation, hide/maximize controls.
- Tests: source Windows CI, packaged WebEngine about:blank smoke gate, and offline pane-height/collapse/maximize/settings smoke test passed on cited PR3 revision.
- Distribution: rolling prerelease `reportmaker-windows-m0`, unsigned `ReportMaker-M0-Setup.exe` + `SHA256SUMS.txt` uploaded to GitHub Releases; legacy Actions installer artifacts purged.
- Not yet verified: all interactive Windows acceptance steps, especially app restart, login persistence and panel divider behavior.
- Limitations: no report/project save/reopen, database, polished WYSIWYG editor, DOCX/PDF export yet. More interactive Windows acceptance remains pending, including persistence and resize use.
- Next: verify PR #1 main merge and combined CI after reconciliation; begin M1 on a new main-based branch, retaining M0 usability acceptance items as explicit pending checks.

## CP-M1 — Customer/site/machine storage and GUI in draft PR #5
- Checkpoint date: 2026-10-26.
- Base: live main `5188f8ff74f50753650cb5975713e9c7bc56576f`. Feature: `feature/m1-customer-site-machine-database`. Verified executable-code commit: `9038a0d323516cb5d0ece7f4db63daf1565e4574`; later documentation commits may change current PR head.
- PR: https://github.com/kandyman991/ReportMaker/pull/5 (draft, NO merge authorization).
- Scope: SQLite schema v1, relationships + guarded CRUD, contacts/addresses/serials, intervention history, search, consistent read snapshots, manual unregistered customer references, write-once report references, verified local online SQLite backups, PySide6 Windows customer-management UI, local privacy boundaries, synthetic tests.
- Architecture: existing M0 report module model, language tags, conclusion-last behavior, ChatGPT user-controlled browser, and manual clipboard boundaries unchanged. M1 reference snapshot is an independent data object. M2 is still responsible for saving full report projects.
- **Verified CI on implementation commit:** M1 Windows Qt smoke #40360575549 SUCCESS; M0 Windows architecture/model #40360566811 SUCCESS; continuity #40360575080 SUCCESS. 17 unit tests passing; GUI smoke exercises synthetic hierarchy and search, and opening the existing shell without visiting ChatGPT. No Windows installer published from this PR.
- Native Windows evidence: hosted Windows GUI test only. Installed end-user-PC form acceptance and restart/history/backup checks **not yet verified**.
- Privacy: synthetic-only CI fixtures; data stored per-user locally, browser profile separate; no customer/CAD data, cookies or logins committed. GitHub repository is public.
- Known gaps: report save/load/export M2–M4, CSV/JSON import/export, encrypted archives, fully interactive Windows acceptance and prerelease packaging. M0 manual acceptance remains open.
- Next: independently review PR #5 at its exact live head and CI; perform manual Windows UI acceptance on a separately approved test build; consider M1 rolling prerelease only after review. **Do not merge without user authorization.**
- Rollback: no main changes; close app before replacing local database from a verified private backup. See `docs/M1_CUSTOMER_DATABASE.md`.

## Checkpoint template for subsequent work
```text
Checkpoint ID / date:
Branch and exact SHA:
PR target/head:
Change summary and architecture/ADR impact:
CI run and conclusion (exact commit):
Native Windows evidence (if any):
Privacy / data movement check:
Known failures and deferred tasks:
Merge/deployment authorization:
Next reproducible action:
```
