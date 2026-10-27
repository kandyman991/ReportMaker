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

## M1 final review corrections — stacked PR #8 (2026-10-26)
- [PR #8](https://github.com/kandyman991/ReportMaker/pull/8) targets `feature/m1-customer-site-machine-database` (PR #5) and began at `99e486fffd071a62aa0f0b4a9af40d1127f9f9a2`. Original review comment: [#5656102312](https://github.com/kandyman991/ReportMaker/pull/5#pullrequestreview-5656102312).
- Release boundary: automatic M0 rolling installer updates on `main` are disabled. The manual-only M0 publisher is pinned to approved M0 source `1981d802194bb2619e689533ac35dabde0f706da`. M1 installation requires a separate approved workflow/release; M1 Windows smoke runs on PRs and on main, without release assets.
- Data fixes: optional/null manual customer ID, complete customer/site postal-address copies with legacy snapshot compatibility, full manual one-off entry, bounded hierarchy search and Qt error handling. Only synthetic tests.
- Review/safety: PR #8 remains isolated and unmerged; next verify exact-head Windows CI (25+ tests and Qt probe) and independent code review. No M1 deployment or PR #5 -> main merge was authorized; native interactive installed-Windows and backup restore acceptance still pending.

## Completion/checkpoint procedure
Update this file and `docs/CHECKPOINTS.md` whenever work is ready for review or a chat handoff. Record exact commit, PR, CI/run, behavior tested, known gaps, next specific action, and rollback; add an ADR for any architectural deviation. Never merge a PR without user authorization. Review exact commit CI and verify GitHub state before claiming work complete.

## M1 merged, M2 feature development checkpoint — 2026-10-26
- M1 PR #5 merged into main at `933cb537ad259d709ea5f1f23b9e56433122e4cf`; the handoff-bot follow-up moved live main to `f9e8abdc94411cc52657eded1c37a0217f428053`. Main M0, M1 Windows and continuity workflows for the merge commit completed successfully. This supersedes earlier *historical* M1 draft status above.
- M2 feature branch `feature/m2-project-module-engine` started from `f9e8abdc94411cc52657eded1c37a0217f428053`. Implementation includes canonical report metadata, modular/heterogeneous block commands and derived one-tree outline, local atomic `.rmproj` project bundles with hashed photo assets, schema validation and undo/redo. See `docs/M2_PROJECT_ENGINE.md`.
- The model and project package are pure Python and do not integrate with the Windows scratchpad UI yet (M3). No web/AI automation, no customer uploads, no installer/deployment, no changes to main.
- At this checkpoint exact-head CI, independent security/code review and native installed Windows acceptance are **pending**. Never claim Windows user acceptance merely from hosted CI.
- Next: verify M2 branch exact SHA and Windows CI, review archive/validation safeguards, fix any findings in feature branch, and get explicit authorization before merge.


## M2 review corrections — PR #10 stacked on PR #9 (2026-10-26)
- Independent PR #9 review at `3daebbf53c81558664a9d6dac41e760425a19108` documented three blocking issues: orphan photo persistence (F01 High), invalid edits producing unopenable projects (F02 High), unsupported ZIP errors escaping input failure (F03 Medium). Review is COMMENTED and not approval.
- Stacked correction PR #10: https://github.com/kandyman991/ReportMaker/pull/10 targeting `feature/m2-project-module-engine`. Feature branch `review/pr9-m2-safety-corrections`, **not** main. Corrects asset pruning, pure recursive serialization validation and strict ZIP compression errors, adds 8 synthetic tests and M2 recovery/version-policy documentation.
- Verified M0 Windows core and **48 tests** at correction code/doc head `fbb2bf056333a512db601e7bdbc864ac1de11af7`, GitHub run #40377387550 SUCCESS; later documentation commits require exact-current-head validation. Review ledger: `docs/PR9_REVIEW.md`.
- PR #10 and PR #9 remain **unmerged**, with no installed-PC acceptance or deployment. Next: independent bounded review of PR #10's exact head and CI, then explicit authorization if integration is desired.


## M3 current development handoff (2026-10-26)
- M2 PR #9, with PR #10 corrections, is merged in live `main` at `092c84e3f0443cf1cf4022b89459046aeee0cb2b`; post-merge hosted Windows core, M1 and continuity workflows succeeded. Mechanical handoff bot made `main` commit `76131fbe25235fc6c85736fd7aaa6f61206ed247`.
- Draft M3 PR #11: https://github.com/kandyman991/ReportMaker/pull/11; branch `feature/m3-visual-report-editor` forked from `76131fbe25235fc6c85736fd7aaa6f61206ed247`. M3 adds native Report Information form, single canonical tree/summary, mixed content editor, photo/table support, visual preview, New/Open/Save/Save As and dirty guards.
- First hosted Windows M0 architecture+M3 offline GUI test and all **48 tests** passed at code head `b9f047c833570f596102d448563d3a08e39e5154` (GitHub run #40397071840). Later source/docs commits REQUIRE exact-final-head CI verification.
- Restrictions: `.rmproj` only; no DOCX/PDF, no automated ChatGPT account control, no production customer data, no installer publishing. Installed-PC mouse/drag/DPI/browser test pending. Review PR #11 independently; **no merge without explicit authorization**.


## M4 feature development checkpoint — 2026-10-26
- Verified live main before branch creation: `bb5f716974818f72fefb446820980cc09698e7f2`. Draft [M4 PR #13](https://github.com/kandyman991/ReportMaker/pull/13) targets main from `feature/m4-editable-docx-pdf-export`, not merged.
- M4 adds `src/reportmaker/export.py`: editable Word paragraphs/tables/inline images/bookmarks and updateable PAGEREF section page fields, plus locally multipaginated PDF with multipass Contents, using a single `module_outline` projection of the saved model. GUI toolbar exports respect pending field validation, dirty state, source path and overwrite guards.
- Original language/source strings exported at M4. Full language-selection/translation/stale approval and document/template branding belong to M5/M6. Word's page reference fields require recalculation **in desktop Word after pagination**; the generated `?` placeholder is intentional before update. PDF page numbers are calculated locally. See `docs/M4_EXPORT.md`.
- Current reviewed-for-CI M4 **implementation** commit `438fab02fa6982429227e418957e5ef3ac613342` passed [hosted Windows core, DOCX/PDF tests and Qt export smoke #40410579198](https://github.com/kandyman991/ReportMaker/actions/runs/40410579198), [M1 Windows smoke #40410579254](https://github.com/kandyman991/ReportMaker/actions/runs/40410579254) and [continuity #40410579187](https://github.com/kandyman991/ReportMaker/actions/runs/40410579187). This documentation-only checkpoint commit will advance the PR head; verify its CI separately before final review.
- Independent review, actual installed-Windows Word/PDF acceptance and approved installer remain PENDING. Consolidated checklist `docs/WINDOWS_ACCEPTANCE_M0_M4.md` contains M0–M4 items, all not yet approved. No customer data/browser profiles shared; no production services changed; no merge/installer/release authorization.
- Next: exact-final-head CI, independent review of output corruption/field numbers/Unicode/table and export failure handling. Fix findings on a separate review PR or reviewed branch; never merge without explicit authorization.


## M4 PR #13 review and stacked corrections (2026-10-27)
- PR #13 `feature/m4-editable-docx-pdf-export` reviewed at `77f12e217c612e03b75db1b66873fce1f55ee5dc`; all three hosted Windows CI workflows passed at that exact head, but installed Windows acceptance remains open.
- Four independently identified issues (PDF TOC literal text loss, non-Latin snapshot metadata font, uncaught PDF table LayoutError, missing per-photo byte bound) corrected on `review/pr13-m4-export-corrections` targeting PR #13, never main. See `docs/PR13_REVIEW.md` for reproduction and test coverage.
- Check final correction SHA/CI, review stacked PR, only then decide whether to integrate corrections into PR #13 and seek explicit main merge authorization. No installer/release or real customer data involved.
