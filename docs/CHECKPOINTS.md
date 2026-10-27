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

## CP-M1-R1 — Independent PR #5 review and isolated fixes
- Review target: PR #5 at exact head `20f74d48009b8669a43a793397852d4d8f6b168a`. Do not merge.
- Correction branch: `review/pr5-m1-storage-ui-fixes`, branched from PR #5, not `main`. Fixes and synthetic regression tests through `f20c998e4338f6b295ff4f3204cecc59c8675675`; further doc commit only.
- Found five issues (backup false-success, LIKE wildcard matching, noncanonical history dates, UI write-error refresh, uncaught SQLite toolbar error); corrected without changing architecture contracts. Full detail in `docs/PR5_REVIEW.md`.
- Original PR #5 Windows CI success does not validate correction commits; inspect correction PR's exact-head Actions checks and independently review before integration.
- Outstanding: native installed Windows manual acceptance, private backup restore verification and reconciliations with main's merged PR #6 document contract. No production data, installer, deployment or merge.
- Next action: have an independent reviewer assess corrections at their exact commit, then (only with authorization) integrate this correction PR into PR #5's feature branch. Reconcile PR #5 with latest main separately before merging.

## CP-DOC-REPORT-COMPOSITION — contract merged on main via PR #6
- Source: user sketch and explicit clarifications on 2026-10-26.
- Branch: `docs/report-structure-contract-20261026`, based on main `5188f8ff74f50753650cb5975713e9c7bc56576f`.
- Scope: ADR-0006, canonical report composition specification, architecture/agent rules and handoff references. Requirements documentation **only**; not proof of application behavior.
- Review: PR #6 was merged into `main` at `1981d802194bb2619e689533ac35dabde0f706da`; ADR-0006 is binding and retained in this reconciliation.
- Tests: M1–M5 acceptance and regression cases specified in contract; code-level tests must be implemented as corresponding features land.
- Next: retain M1 manual snapshots and implement later M2–M4 metadata, tree/summary and document-export acceptance gates without claiming those features exist yet.

## CP-M1-INTEGRATION — PR #7 and main/PR #6
- M1 parent after PR #7 merge: `685fd6bc884036d29e8ef2658c5dfc192864e8b8`; main reconciliation parent: `4f6cec7b51cfb1282923e3fa05c38d8d0d1f035b`. Next merge commit targets **PR #5 feature branch only**.
- PR #7 closed and merged, resolving PR5-F01–F05; review and synthetic regressions: `docs/PR5_REVIEW.md`.
- Windows M1 Qt + 20 unit tests PASS at PR #7 correction head `62dda31d689a5a208928da78053586f97fc3c981` [#40362467582](https://github.com/kandyman991/ReportMaker/actions/runs/40362467582). Windows M0 PASS on PR #5 post-PR7 head [#40363954099](https://github.com/kandyman991/ReportMaker/actions/runs/40363954099); new combined-head M1 run still needs verification.
- PR #6 composition contract and ADR-0006 are retained with M1 docs. M1 supports manual customers/snapshots; multiselect intervention types, one-tree Summary, project persistence and export remain M2–M4 work.
- Pending: exact-head Windows CI after reconciliation, independent review, native installed Windows forms/backup restore/DPI tests. Synthetic-only; no production data, install or merge into main.

## CP-M1-R2 — Review corrections in independent stacked PR #8
- Source PR #5 reviewed commit: `99e486fffd071a62aa0f0b4a9af40d1127f9f9a2`; correction branch `review/pr5-final-review-corrections`, PR #8, targeting PR #5 feature branch (not main). Initial fix commit `e61c4a4598479d63ecc68111019473c28cf08cbc`.
- R2-F01 High: release workflow no longer auto-publishes M1 from main under M0 tag; manual M0 rebuild pinned to `1981d802194bb2619e689533ac35dabde0f706da`. M1 CI runs on main but does not package or publish release assets.
- R2-F02 Medium: nullable unregistered report customer IDs supported by model, including strict matching of registered snapshots.
- R2-F03 Medium: customer/site postal codes persist in historical snapshots; older serialized reference format compatible.
- UI followups: full manual detail entry; debounced search and batched child queries; read/history errors preserve context and warn rather than escape Qt handlers.
- Added synthetic unit and Windows Qt smoke regressions. First Windows test run exposed an overly broad assertion matching the subquery in customer search, corrected on this branch; verify the next exact commit before approval.
- No real customer/corporate data, browser state or credentials. Independent correction review and installed-PC M1 acceptance remain outstanding. Neither PR #8 nor #5 may be merged without authorization.

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

## CP-M2-START — project/module engine on isolated feature branch
- Date: 2026-10-26. Base main: `f9e8abdc94411cc52657eded1c37a0217f428053` (after M1 merge + handoff bot).
- Branch: `feature/m2-project-module-engine`. First engine commit `c7663807d2e00635ac395d91a793938518630d97`; project bundle commit `bed6a61eac776674b747e273fc47fe5b0fbccbc8`; synthetic M2 tests commit `e363c98b7470b9cce5bd136effd6b887dfc6afe6`; later documentation commits may move HEAD.
- Binding contracts: ADR-0006 and `docs/REPORT_COMPOSITION_CONTRACT.md`. Metadata includes creation date, title, multi-select types/Other, personnel, snapshots, languages. Blocks remain freely ordered/nested. One canonical hierarchy derives editor navigation and automatic Summary; Conclusions remain last.
- M2 implementation: pure command engine with undo/redo; version-1 project ZIP manifest with locally embedded photo data and verified digests; atomic replacement; fail-closed schema/corruption handling. No DOCX/PDF, M3 visual editor, AI API, external upload or user production data.
- Test evidence: `tests/test_m2_project.py` is synthetic-only; exact final branch CI outcome and native Windows acceptance must be verified **after** this checkpoint. Prior M1 merged-main workflows were successful; do not substitute them for M2.
- Privacy/deployment: no production files, credentials, website cookies, native install or public installer. No merge authorization.
- Next: open M2 draft PR, verify exact-head Windows CI and independent review, correct findings before seeking merge authorization. Documented format limits in `docs/M2_PROJECT_ENGINE.md`.


## CP-M2-R1 — isolated corrections for PR #9 review findings (2026-10-26)
- Original reviewed PR9 head: `3daebbf53c81558664a9d6dac41e760425a19108`; independent review https://github.com/kandyman991/ReportMaker/pull/9#pullrequestreview-5656832565 (COMMENTED, **not approval**).
- PR9-F01 High: unreferenced media packaged invisibly -> serialize only reachable assets; keep in-memory bytes for undo and shared references; legacy v1 orphan imports scrub on resave.
- PR9-F02 High: edit may save invalid metadata/translated text -> pure, comprehensive metadata and nested localized validation at edit and save boundaries, with no post-construction silent default restoration.
- PR9-F03 Medium: malformed unsupported ZIP compression may raise other exception -> compression/encryption allowlist and controlled corruption errors.
- Stacked correction PR #10 https://github.com/kandyman991/ReportMaker/pull/10; branch `review/pr9-m2-safety-corrections` targets PR #9 feature branch, not main. Review ledger `docs/PR9_REVIEW.md`; package compatibility/backup policy `docs/M2_PROJECT_ENGINE.md`.
- Verified hosted Windows core run #40377387550 SUCCESS and 48 tests at exact head `fbb2bf056333a512db601e7bdbc864ac1de11af7` before later docs-only commits. The initial malicious ZIP fixture failure #40377228870 was corrected and is not a production test failure.
- Synthetic fixtures only, no customer data, no installer/production changes. M1 main remains untouched.
- Open: independent targeted correction review; final exact SHA/CI recheck; manual installed-Windows acceptance; M3 UI Save/Open and private opt-in backup decision. **No merge, release or deploy without user authorization.**


## CP-M3-DRAFT — Visual report editor in PR #11 (2026-10-26)
- Base main `76131fbe25235fc6c85736fd7aaa6f61206ed247`; PR #11 draft `feature/m3-visual-report-editor` -> `main`.
- Requirements: ARCHITECTURE.md, ADR-0006, REPORT_COMPOSITION_CONTRACT.md. Editor tree and Summary are two projections of the canonical M2 hierarchy, never independently maintained; conclusion remains mandatory/last, manual customer data and frozen DB snapshots preserved.
- Changes: native tree drag/drop, reordered heterogeneous text/photo/table blocks, block editing, report metadata, Qt document preview, graphical `.rmproj` New/Open/Save/Save As, undo/redo and dirty-document prompts. Browser remains unprivileged, manual only.
- Evidence: hosted Windows M0+M3 offline smoke and 48 synthetic unittest cases SUCCESS at prior implementation revision `b9f047c833570f596102d448563d3a08e39e5154`, [run #40397071840](https://github.com/kandyman991/ReportMaker/actions/runs/40397071840). Additional updates must be verified at current exact head.
- Native installed Windows acceptance: NOT YET performed; actual mouse drag/drop and image rendering, responsive layout, file dialogs, keyboard navigation, persisted browser profile and normal website login all pending.
- Privacy: tests use generated dummy customer and synthetic image; no real reports, browser data, credential provision, releases or deployment.
- Next: verify PR #11 final-head CI and independently review UI state transitions, drag indexes and failure/close handling; correct issues on PR branch. Merge only after explicit user permission.


## CP-M3-R1 — PR #11 independent review corrections (2026-10-26)
- Parent: draft M3 PR #11, `feature/m3-visual-report-editor`, reviewed head `bb6730767ea9466e002c886c2699832e17fd785e`. Reviewer ledger: https://github.com/kandyman991/ReportMaker/pull/11#pullrequestreview-5659096198.
- Stacked PR #12: `review/pr11-m3-editor-corrections` -> PR #11 feature branch, **not main**. Implementation/tests committed through `55d10944dcfbcbfed1d160e9f2de69f95bf0c200`. Future documentation commits can advance branch HEAD; always verify live SHA and exact-head CI.
- M3-F01 HIGH: report-information drafts are applied before Undo/Redo so they remain in undo history rather than being silently overwritten by UI refresh.
- M3-F02 HIGH: pending/invalid drafts present Save/Discard/Cancel without validating the Discard path; Save still invokes guarded model/project validation.
- M3-F03 MEDIUM: changing manual customer, site or machine resets supplementary frozen-snapshot fields scoped to that identity and its descendants; unchanged ancestor details remain intact.
- M3-F04 MEDIUM: required Other intervention description appears in document preview, not just in project metadata.
- Windows hosted offline GUI smoke includes synthetic key-typed pending changes, history navigation, invalid draft Discard, three identity-change levels and project round-trip, and preview description. The exact current-head CI conclusion must be checked live; the historical parent success does not validate these fixes.
- No browser integration changes, real customer data, release, installer or deployment. Actual installed Windows mouse drag/drop, responsive DPI, image rendering, dialogs and full UI acceptance still outstanding.
- Next: independently review PR #12 at exact head; verify hosted Windows CI; only after explicit user authorization integrate PR #12 into PR #11 and repeat final combined-head review. **Do not merge either PR without authorization.**



## CP-M4-DRAFT — editable DOCX / PDF export, PR #13 (2026-10-26)
- Parent main SHA: `bb5f716974818f72fefb446820980cc09698e7f2`. Branch `feature/m4-editable-docx-pdf-export`, draft PR [#13](https://github.com/kandyman991/ReportMaker/pull/13) -> main. Implementation bookmark/font revision `adc84667d30c75c1dec3ba7786aecaf125db393f` (later docs may advance branch HEAD).
- Requirements: `ARCHITECTURE.md`, ADR-0006, `docs/REPORT_COMPOSITION_CONTRACT.md`. Export consumes source/canonical ordered modules; tree/summary are the same `module_outline`; conclusion last; multi-type and detached customer report snapshots unchanged; `.rmproj` remains canonical.
- Implementation: editable DOCX Word title/paragraph/heading/table/inline picture/caption/page break; visible auto-derived section contents with Word PAGEREF fields to refresh after Word pagination; local PDF built from same projection with multipass TOC/page footer; source-only M4 export, M5 language review deferred. Qt Save As actions with atomic replace and guarded pending edits. See `docs/M4_EXPORT.md`.
- Tests: `tests/test_m4_export.py` and offline Qt `--export-self-test`. Hosted Windows M4 export + preexisting M0–M3 core tests, M1 GUI regression and continuity **PASS** at exact implementation commit `438fab02fa6982429227e418957e5ef3ac613342`: [core #40410579198](https://github.com/kandyman991/ReportMaker/actions/runs/40410579198), [M1 #40410579254](https://github.com/kandyman991/ReportMaker/actions/runs/40410579254), [continuity #40410579187](https://github.com/kandyman991/ReportMaker/actions/runs/40410579187). Subsequent checkpoint-only commits can advance branch HEAD; verify the resulting live head and CI before review.
- Installed native Windows: **NOT done**. Required consolidate M0–M4 checklist and actual desktop Word/PDF validation in `docs/WINDOWS_ACCEPTANCE_M0_M4.md`; no installer or prerelease published.
- Privacy: synthetic fixtures only, local asset bytes, no browser/AI/report uploads; M0 rolling prerelease stays pinned. Next: exact-head CI and independent review before seeking merge approval. **NO MERGE/RELEASE AUTHORIZATION.**


## CP-M4-R1 — independent review corrections for PR #13 (2026-10-27)
- Reviewed PR #13 head `77f12e217c612e03b75db1b66873fce1f55ee5dc` against `main`, with verified successful hosted Windows workflows #40410962651, #40410962767 and #40410962905. The project source was not merged.
- Four findings PR13-F01..F04 documented in `docs/PR13_REVIEW.md`: literal PDF Summary title loss, Unicode customer metadata font, unhandled oversized-table PDF LayoutError, and missing per-photo export byte bound.
- Stacked branch `review/pr13-m4-export-corrections` targets the M4 feature branch, not main. Corrective source/tests and synthetic regressions committed for independent review; check live final head and Windows CI after this documentation update.
- Native installed-Windows M0–M4 acceptance remains pending; Word field refresh, company-branded header/footer/layout work and installer approval are still open. No merge or prerelease publication authorized.


## CP-M4-PRESENTATION — optional export branding/layout, PR #15 (2026-10-27)
- Base: live main `4f409c34a98a8dd6c15bfc3a9330218e69dd0b9a`; earlier PR #13 merge `46443b425c1dd6c7e2399b0c8d04293e59895f24` and PR #14 corrections integrated, post-merge Windows CI green. Branch `feature/m4-branding-layout-completion`, draft PR #15 -> main.
- Change: ADR-0007 opt-in local QSettings branding (company name, footer and image path), `ExportStyle` to both DOCX/PDF with repeating headers and page labels, scaled photo/caption layout, strict bounded decoding and no-clobber semantics; `.rmproj` stays canonical. Same derived hierarchy and Conclusion-last invariant.
- Added synthetic DOCX/PDF/Qt smoke regressions and updated `docs/WINDOWS_ACCEPTANCE_M0_M4.md` for installed acceptance. Exact branch CI outcome must be independently retrieved at final head; no claim of Windows-native installed test yet.
- Next: fix any CI findings on PR #15, targeted independent technical review, then seek explicit approval for integration; only afterward run consolidated installed-Windows tests and inspect M4 print/layout with desktop Word. No private reports, public logo assets, credentials, installers or releases involved.

## CP-M45-DESIGN — project-contained media workflow agreement (2026-10-27)
- Decision: User accepted design for M4.5 ahead of M5: imported-only working photo container, preserved external originals, offline HEIC conversion/default JPEG Q88 + 2500 px long edge, alternate presets/formats, non-destructive edits, visible technical annotations and separate private review threads.
- Source: [ADR-0008](adr/0008-m45-media-workspace.md), [M4.5 design and acceptance gates](M45_MEDIA_WORKSPACE.md), ARCHITECTURE.md, ROADMAP.md; draft documentation PR [#16](https://github.com/kandyman991/ReportMaker/pull/16) on docs/m45-media-workspace-contract targeting main base 6a38ae04fda29c69710be31734d6d3a68f906ab4. Verify exact final head and CI live.
- Required schema change: M2 v1 no-hidden-orphans save rule must be extended intentionally to include explicitly declared but unused library images; migration v1->new format, corruption/roll-back and portable source-independent reopening need tests. No code/schema modified by this documentation PR.
- Existing M4 source merged via PR #15, merge SHA 5342e765efd7a80f34a6540fcad30ab8d9e7e3a7. The user postponed consolidated installed Windows M0–M4 acceptance; neither M4.5 planning nor hosted CI can mark it complete.
- Privacy: no original/customer media, credential, browser profile, production data, external network processing, installer, or prerelease changes. Design-only PR, no merge authorization. Next: independently review documentation and seek approval for integration, then plan M4.5 implementation in separate feature PRs.
