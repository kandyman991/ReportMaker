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

## CP-M1 — Next milestone (not started)
- Goal: local SQLite customers/sites/machines; names, addresses and contacts; serial numbers and history; safe migrations, local backups; report-level immutable snapshots; permit reports without customer master entry.
- Constraints: no paid/automated AI, no private data upload, Windows host CI, release assets not Actions artifacts.
- Execution: isolated M1 PR; synthetic migration/relationship/search tests plus Windows GUI acceptance. Add precise SHA, PR, test evidence and decision/risk summary here before closing the development chat.

## CP-DOC-REPORT-COMPOSITION — requirements preservation (proposed)
- Source: user sketch and explicit clarifications on 2026-10-26.
- Branch: `docs/report-structure-contract-20261026`, based on main `5188f8ff74f50753650cb5975713e9c7bc56576f`.
- Scope: ADR-0006, canonical report composition specification, architecture/agent rules and handoff references. Requirements documentation **only**; not proof of application behavior.
- Review: open documentation PR and verify its exact head SHA/CI before merge. No merge authorized. Existing M1 PR #5 remains independent.
- Tests: M1–M5 acceptance and regression cases specified in contract; code-level tests must be implemented as corresponding features land.
- Next: review this contract, and rebase/integrate into M1 and later milestone work only after explicit approval. No private customer information stored.

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
