# ReportMaker — reviewed development checkpoints
_Updated 2026-10-26. Maintainers edit this file at PR, milestone and chat-handoff boundaries._

## CP-000 — Continuity system installed
- Scope: project documentation, ADR-0005, validation gates, GitHub-hosted mechanical state updates. **No application code**, no merge of M0 PR #1/#3.
- Status: continuity-only branch under review; check the **live** PR and workflow before asserting main is updated.
- Privacy: synthetic-only content; no CAD/customer material, screenshots of accounts, browser cookies or credentials.
- Recovery: start from CHAT_HANDOFF.md + handoff/state.json, then read live PR refs and compare exact SHAs.

## CP-M0 — Windows prototype / deferred final acceptance
- Branches at recording time: PR #1 head 4c6fff52bafd3f755888f46f321efb7b17b3e62e (base main); stacked PR #3 head b1cf60870b96f13706437567bad249a278e665b8 (base feature/m0-foundation). BOTH unmerged.
- Functionality seen in user-supplied Windows screenshots: installed GUI, three columns, manual scratchpad, embedded full-height ChatGPT website with logged-in conversation, hide/maximize controls.
- Tests: source Windows CI, packaged WebEngine about:blank smoke gate, and offline pane-height/collapse/maximize/settings smoke test passed on cited PR3 revision.
- Distribution: rolling prerelease `reportmaker-windows-m0`, unsigned `ReportMaker-M0-Setup.exe` + `SHA256SUMS.txt` uploaded to GitHub Releases; legacy Actions installer artifacts purged.
- Limitations: no report/project save/reopen, database, polished WYSIWYG editor, DOCX/PDF export yet. More interactive Windows acceptance remains pending, including persistence and resize use.
- Next: establish continuity on main, preserve unmerged M0 branches; begin M1 separately after live repository inspection and correct base selection.

## CP-M1 — Next milestone (not started)
- Goal: local SQLite customers/sites/machines; names, addresses and contacts; serial numbers and history; safe migrations, local backups; report-level immutable snapshots; permit reports without customer master entry.
- Constraints: no paid/automated AI, no private data upload, Windows host CI, release assets not Actions artifacts.
- Execution: isolated M1 PR; synthetic migration/relationship/search tests plus Windows GUI acceptance. Add precise SHA, PR, test evidence and decision/risk summary here before closing the development chat.

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
