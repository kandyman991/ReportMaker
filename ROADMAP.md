# Roadmap

## M0 — Foundation (implementation remains in draft PRs #1 and #3)
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

## M1 — Customer database
SQLite schema/migrations, customers/sites/machines, search, edit, history and report snapshots; backup/import/export policies.

## M2 — Project and module engine
Ordered heterogeneous blocks, nested modules, photo assets, persistence, undo/redo, conclusion-last invariant, import/export project format.

## M3 — Visual editor
Module tree, freely ordered drag/drop content, photo/text/table editing, resizable panes, visual document preview and accessibility.

## M4 — Word/PDF output
Fully editable DOCX, rendering and pagination, image anchoring/captions, branded header/footer, table of contents and pagination regression fixtures.

## M5 — Open-ended languages
User-added locales, per-block variants, stale markers, translations and separate/inline/section export styles. No paid AI translation integration.

## M6 — Templates
DOCX template import/fill, style mapping, visual template designer, lossless/unsupported-object warning.

## M7 — Polish and packaging
Signed installer evaluation, backups, diagnostics, security/privacy tests, real-world reference reports (sanitized and private), bilingual/multilingual regression checks.

Milestones can be re-sequenced by reviewed ADR, never silently.
