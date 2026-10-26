# Roadmap

## M0 — Foundation (PR #1 merged, incorporating PR #3; manual acceptance partial)
- [x] Document immutable product constraints and architecture decisions.
- [x] Define typed flexible module/report data model and pure-model tests.
- [x] Create Windows-first application shell, ChatGPT browser spike, clipboard paste and external browser fallback.
- [x] Add Windows CI gates for core tests and syntax checking.
- [x] Full-height embedded browser and independently collapsible/maximizable panes with local layout persistence and Windows layout smoke gate.
- [ ] Interactive Windows compatibility acceptance: launch, resize, close/reopen, sign in if supported, reject/error handling, fallback, data location, clipboard and no browser-log leaks.
- [x] Add reproducible Windows installer build workflow (PyInstaller onedir + Inno Setup and self-test).
- [x] Publish rolling Windows M0 **GitHub prerelease** without GitHub Actions artifact storage; scoped legacy-artifact cleanup after successful publication.
- [ ] Install/uninstall and normal embedded browser sign-in acceptance on an actual Windows desktop.
- [x] Add GitHub-backed curated handoff + mechanical state snapshot + continuity regression gates (continuity-only bootstrap).
Exit: docs/tests green AND native Windows manual checklist completed. M0 is not complete solely because CI is green.

## M1 — Customer database (PR #5 merged into main 2026-10-26; installed-PC acceptance remains pending)
- [x] Local SQLite schema v1/transactional migration, customers/sites/machines, search/edit, serials and machine intervention history.
- [x] Write-once detached reference snapshots and one-off manual customer references.
- [x] Local SQLite online backup, integrity check and documented import/export/privacy policy.
- [x] Native PySide6 customer manager and hosted Windows offline Qt smoke gate, synthetic-only tests.
- [ ] Independent code review, installed Windows interactive acceptance and M1 prerelease build strategy.
- [ ] Full saved report/project integration is M2, not M1. JSON/CSV import remains a separate reviewed policy task.

## M2 — Project and module engine (PR #9 merged into main 2026-10-26)
- [x] Canonical report metadata and mixed intervention types; ordered heterogeneous blocks, nested modules and derived summary projection.
- [x] Standalone local project save/reopen, embedded hashed photo assets, schema versioning and fail-closed import.
- [x] Transactional model editing with undo/redo, module duplication/reordering and conclusion-last validation.
- [x] Reviewed correction PR #10 and integrated PR #9; hosted Windows CI passed after main merge.\n- [ ] Installed Windows file dialogs / interactive save-reopen acceptance remains pending.
See `docs/M2_PROJECT_ENGINE.md`.

## M3 — Visual editor (draft PR #11)
- [x] Native three-pane editor, tree and automatically derived Summary from the same canonical M2 hierarchy.
- [x] Drag/drop module nesting/reordering and block reordering; move block between modules; editable text/headings/photos/captions/tables/page breaks.
- [x] Report Information form: creation/range/ticket/personnel, multiple intervention types, language tags, database or detached manual customer snapshots.
- [x] Graphical New/Open/Save/Save As, undo/redo, invalid import protection and unsaved edit prompts.
- [x] On-device HTML document preview, including synthetic image resources, not Word pagination.
- [x] Synthetic hosted Windows GUI smoke gate; no real customer data or account sessions.
- [ ] Independent technical review, exact-final-head CI, installed-Windows acceptance, keyboard accessibility and true WYSIWYG print/pagination validation.
See `docs/M3_VISUAL_EDITOR.md`.

## M4 — Word/PDF output
Fully editable DOCX, rendering and pagination, image anchoring/captions, branded header/footer, table of contents and pagination regression fixtures.

## M5 — Open-ended languages
User-added locales, per-block variants, stale markers, translations and separate/inline/section export styles. No paid AI translation integration.

## M6 — Templates
DOCX template import/fill, style mapping, visual template designer, lossless/unsupported-object warning.

## M7 — Polish and packaging
Signed installer evaluation, backups, diagnostics, security/privacy tests, real-world reference reports (sanitized and private), bilingual/multilingual regression checks.

Milestones can be re-sequenced by reviewed ADR, never silently.
