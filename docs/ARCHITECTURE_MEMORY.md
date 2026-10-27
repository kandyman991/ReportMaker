# Architecture memory / anti-regression log

2026-10-26 — Initial decisions:
- Chose modular, hierarchical report content instead of fixed form fields after comparing supervision and spiral-maintenance reports.
- Flexible blocks INSIDE each module; photos belong to their module and must move with it.
- Customer-first workflow and conclusion-last invariant.
- Open-ended report languages and independent UI localization.
- Windows is a mandatory runtime.
- Rejected paid AI API/agent integration in favor of user-driven normal website with manual copy/paste.
- Real sample reports are sensitive and must not be placed in this public repository.
- Existing Word templates and custom visual templates must coexist without promising lossless arbitrary DOCX-to-editor conversion.

Rejected architecture patterns:
- Fixed Title -> Description -> Photo Gallery module.
- Hardcoded {Italian, English} language enum.
- DOCX as the only editable canonical project representation.
- Programmatic ChatGPT login, scraping or automated use.
- Claiming embedded login or Windows installer compatibility without Windows testing.

For future changes add a dated entry with evidence, failed alternatives, ADR reference and regression test link.

2026-10-26 — Windows installer decision (ADR-0004): production users must not install Python, Git or use PowerShell. M0 distribution uses an unsigned, per-user Inno Setup installer wrapping an onedir PyInstaller build; GitHub Actions performs an offline Qt WebEngine smoke test. Actual ChatGPT login and installer acceptance remain human Windows tests.

2026-10-26 — M0 layout correction: Windows field test proved that QtWebEngineView loaded ChatGPT but only consumed a narrow portion of the right panel. Require explicit vertical stretch for browser, compact status, resizable/collapsible/maximizable panels, persistent layout preferences, and offline UI geometry regression checks. No browser automation or sensitive site data in tests.

2026-10-26 — Distribution correction: user requested stopping GitHub Actions artifact storage and matching RoadPilot Graph Studio. ReportMaker Windows installer now publishes a rolling GitHub prerelease (`reportmaker-windows-m0`) with installer/checksum and exact commit notes; superseded runs are cancelled, and a post-publication job removes only legacy ReportMaker installer Actions artifacts. No customer/CAD content is included. See ADR-0004 and the Windows distribution regression test.

2026-10-26 — Continuity bootstrap (ADR-0005). User required same handoffs/checkpoints as RoadPilot. Establish curated CHAT_HANDOFF.md + docs/CHECKPOINTS.md, main-triggered handoff/state.json via github-script, read-only history/architecture authority, mandatory checkpoint review gates and M1 entry instructions. Install documentation and automation on main **without merging M0 PR #1/#3**. Browser test screenshots confirm interaction but not exhaustive Windows tests. No sensitive content or GH artifact uploads.

2026-10-26 — M1 first implementation in draft PR #5: customers -> sites -> machines with SQLite foreign keys, RESTRICT deletions, dated history and immutable write-once detached references. One-off references do not require master insertion. Browser profile and report data remain separate. Hosted Windows CI revealed that Python sqlite3 connection context managers commit/rollback but do not close file handles; explicit closing is required for backups and synthetic Windows fixtures. No architecture deviation or paid AI integration. See docs/M1_CUSTOMER_DATABASE.md and exact CI runs in docs/CHECKPOINTS.md.

2026-10-26 — Report composition clarified by user's paper sketch and follow-up (ADR-0006). Report Info includes creation date/title/intervention date range/ticket/personnel and **multiple** intervention types; Summary is a derived table of contents, never an independently maintained structure from the editor's nested module tree. Reports may select an existing customer or enter one manually; both preserve a report-local snapshot. Canonical module source prevents drift after edits. See docs/REPORT_COMPOSITION_CONTRACT.md for acceptance cases. No real client/customer details or image were uploaded to public GitHub.

2026-10-26 — M2 implementation decision: Report data remains independent of layout/Word output. A `.rmproj` ZIP containing a strict versioned JSON model and logical-id hashed local photo assets serves as a portable editable project; no extraction, no network transport and no browser session data. The editor's derived tree/contents view is one shared projection of the same block hierarchy. Undo/redo operates on validated whole-report snapshots. GUI file dialogs and WYSIWYG are M3, not implied by M2 core tests; see `docs/M2_PROJECT_ENGINE.md`.

2026-10-27 — M4.5 Picture Manager decision (ADR-0008, draft PR #16). The user specifically required that high-quality external HEIC/photo originals remain untouched *outside* the project. Working copies are imported into a portable .rmproj media container and can be converted/compressed locally (balanced JPEG Q88, maximum 2500 px long edge by default). Pictures need crop/resize/rotate/annotate support, customer-visible text and shapes, and separate private pinned review threads/replies/status excluded from customer-facing exports. Reuse project media without duplicating stored bytes, with independent placement edits and a reviewable project format migration from M2's block-reachable-only asset rule. Rejected alternatives: editing HEIC in place, storing originals automatically, referencing required external paths, flattening editing layers in the source, exporting private review comments, mandatory all-photo PNG expansion, silently dropping orphan-vs-unused-library distinctions. User deferred consolidated M0–M4 installed Windows acceptance until back at PC; do not mistake hosted CI or this design note for acceptance.
