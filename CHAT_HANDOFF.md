# ReportMaker — curated chat handoff
_Last curated: 2026-10-26. This is an intentional checkpoint; it is **not** auto-generated._

## Read first in every development or review chat
1. Read `AGENTS.md`, `ARCHITECTURE.md`, `ROADMAP.md`, this file, `docs/CHECKPOINTS.md`, `docs/ARCHITECTURE_MEMORY.md` and the ADRs.
2. Read `handoff/state.json` on **main** once populated by the automatic workflow.
3. Verify **live** GitHub branches, PR heads/bases, CI conclusions, release commit and outstanding issues. The generated JSON is a snapshot, not proof of current status.
4. State a specific branch, exact SHA, intended change, test plan, merge restriction and next checkpoint.
5. At each milestone or context handoff, update the curated records in a reviewable PR. Automation updates the mechanical snapshot only; it does **not** infer architecture decisions or report validation.

## Repository and current branch situation
- Repository: `kandyman991/ReportMaker` (PUBLIC).
- M0 core foundation **PR #1** (incorporating PR #3) was merged to main at `cb774e714fabd847c8a34218686e9375cc4afcde`; the later main continuity-state commit was `5188f8ff74f50753650cb5975713e9c7bc56576f`. Verify live main before future branches. Interactive M0 acceptance is still partial.
- M0 Windows installer/layout **PR #3 merged into PR #1's feature branch** at `4846e27ed45e2ebb53ca16f51e985883305b9ddd`; its original tested head was `b1cf60870b96f13706437567bad249a278e665b8`.
- The M0 executable is an **unsigned Windows preview**, not a functioning saved report editor.
- Stable, rolling **test prerelease**: https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-windows-m0 . Installer and SHA256 checksum are GitHub Release assets; no new Actions artifacts.
- Windows packaging and offline layout CI passed at the PR #3 revision listed above. User installed and launched M0 and demonstrated normal ChatGPT conversation in the embedded full-height website from Windows screenshots.
- **Not yet verified:** reinstall/uninstall edge cases, panel width persistence across app restarts, all resize/collapse interactions, login persistence and complete M0 acceptance. Do not confuse visual evidence with exhaustive tests.
- Once branches change, replace these historical SHA pointers with live GitHub evidence, not guesswork.

## Locked product requirements
- Native, self-contained Windows GUI; no Python/Git required on end-user PC.
- Customer → site → machine → serial number/contact/intervention history; report snapshots must not silently change when customer master data changes.
- Reports have unlimited reordered/nested modules with freely interleaved text, photos, tables and submodules. Dedicated Conclusions section always last.
- Local editable canonical project, later genuinely editable DOCX and optionally PDF. Word template import and visual design later.
- Open-ended BCP-47-style languages; original + translations + stale markers; UI locale independent.
- ChatGPT panel is **ordinary user-operated website only**; explicit manual copy/paste into editor. No OpenAI API, other paid AI provider, agents, automation, hidden scripting, web scraping or token extraction. Default-browser fallback.
- **Company CAD, private customer reports, photographs and credentials must never be placed in this PUBLIC repo or uploaded to AI/cloud services.** All tests use synthetic fixtures. CAD Inspector is intentionally **last** milestone, not part of M1.
- Use hosted Windows Actions runners (`windows-latest`), no user-owned self-hosted machine requirement.
- Direct rolling GitHub **prerelease** distribution; no `actions/upload-artifact`, no Actions cache storage. Keep developer/test releases separate from approved main builds in a later reviewable change.

## Report composition clarification (2026-10-26; ADR-0006)
Read `docs/REPORT_COMPOSITION_CONTRACT.md` before any M1 database, M2 model, M3 editor, M4 export or M5 language work. The user's sketch defines the report-info header (creation date, title, intervention from/to, optional ticket, type(s), personnel), a generated table of contents, and a titled module/submodule hierarchy. A report may select **multiple intervention types**. The contents and editor tree MUST derive from the same canonical hierarchy. Customer data may be selected from the database **or entered manually** with no master; each saved report captures a detached snapshot. Conclusions remain last. These are requirements, **not yet fully implemented features**. The original sketch was provided in chat; the public repo contains the textual contract, not the uploaded image.

Historical documentation-review checkpoint: PR #6 merged into `main` at `1981d802194bb2619e689533ac35dabde0f706da`; `main` was verified at `4f6cec7b51cfb1282923e3fa05c38d8d0d1f035b` during M1 reconciliation.

## M1 entry
Start after reading the records and verifying M0 PR #1 and #3 are integrated into main. Design local SQLite customer/site/machine schema/migrations and editable GUI. A report must capture a local immutable customer/site/machine snapshot; support work without a master customer entry. Define backup and privacy boundaries before persistent data. Work on an isolated M1 feature branch/PR from the correct *live* main commit; do not overwrite continuity records. Use fabricated test customers, never production information.

## M1 development checkpoint — PR #5 (draft, NOT MERGED)
- Branch: `feature/m1-customer-site-machine-database`; created from verified main `5188f8ff74f50753650cb5975713e9c7bc56576f`.
- Verified implementation commit: `9038a0d323516cb5d0ece7f4db63daf1565e4574` (subsequent doc commits do not change executable code). The live branch head must always be checked independently.
- Scope: pure SQLite schema v1/migration, customers/sites/machines/contacts/serials, guarded CRUD, machine intervention history, immutable customer snapshots, manual one-off references, write-once report-reference storage, explicit local SQLite backup, Windows Qt customer manager in the M0 shell. See `docs/M1_CUSTOMER_DATABASE.md`.
- Exact verified runs on the implementation commit: [M1 Windows Qt smoke #40360575549](https://github.com/kandyman991/ReportMaker/actions/runs/40360575549) SUCCESS; [M0 Windows architecture/model #40360566811](https://github.com/kandyman991/ReportMaker/actions/runs/40360566811) SUCCESS; [continuity #40360575080](https://github.com/kandyman991/ReportMaker/actions/runs/40360575080) SUCCESS. Unit suite: 17 passing tests. These are hosted Windows checks, not installed-PC manual acceptance.
- M1 intentionally does NOT persist full report projects or export DOCX; M2 and M4 own those capabilities. No real customer data has been entered into tests, CI or GitHub.
- Pending: independent code review; installed Windows manual acceptance including search/forms/history/backups, resize/DPI and app restart; decision on distributing a reviewed M1 prerelease installer. No merge or deployment authorized.
- Rollback: leave draft PR unmerged; release/main unchanged. For local data restore only after closing app from a verified private backup. PR: https://github.com/kandyman991/ReportMaker/pull/5 .

## PR #7 corrections and main/PR #6 reconciliation (2026-10-26)
- PR #7's five corrections merged into PR #5's feature branch at `685fd6bc884036d29e8ef2658c5dfc192864e8b8`. PR #5 remains draft, unmerged.
- Hosted Windows M0 CI on that head: [#40363954099](https://github.com/kandyman991/ReportMaker/actions/runs/40363954099) SUCCESS. PR #7 correction head `62dda31d689a5a208928da78053586f97fc3c981` passed Windows M1 Qt smoke including 20 synthetic unit tests [#40362467582](https://github.com/kandyman991/ReportMaker/actions/runs/40362467582). The latter was not run on the PR #5 merge SHA.
- Latest main reconciliation parent: `4f6cec7b51cfb1282923e3fa05c38d8d0d1f035b` (including merged PR #6 and ADR-0006). The forthcoming merge commit preserves M1 implementation and both branches' curated checkpoints.
- **Milestone boundary**: M1 manual snapshots do not imply multi-intervention metadata, unified tree/summary UI, or saved project functionality. Those remain M2–M4 deliverables.
- Next: exact-new-head Windows CI and independent review, followed by installed Windows acceptance of search/forms/history/backup/keyboard. Never merge PR #5 to main, deploy, or publish an M1 installer without explicit authorization.

## Completion/checkpoint procedure
Update this file and `docs/CHECKPOINTS.md` whenever work is ready for review or a chat handoff. Record exact commit, PR, CI/run, behavior tested, known gaps, next specific action, and rollback; add an ADR for any architectural deviation. Never merge a PR without user authorization. Review exact commit CI and verify GitHub state before claiming work complete.
