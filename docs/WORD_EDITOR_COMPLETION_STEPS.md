# Word editor — staged completion and acceptance

Checkpoint 2026-10-27. Draft rich-text editor PR #25 is stacked on preview contrast PR #22.

## Engineering rules

The report/project canonical hierarchy and language provenance stay authoritative. Direct page editing must use guarded report commands, not independent HTML. The generated Summary/TOC always derives from the module tree. Keep private Word templates, photographs and customer data on the user's computer; only synthetic tests in this public repository. No main merges or installer/release publication without user authorization.

## Step 1 — PDF text fidelity (PR #28)
- [x] Paragraph borders rendered, including shaded paragraphs.
- [x] Correct continuous decimal and alphabetic numbering with resets and cross-block continuation.
- [x] PDF-level tests inspect graphics operators and extracted text.
- [x] Hosted Windows exact-code-head CI success for 1ff7d6544e251f9f43b9743afe833172eed4eaff: M0 run 40496286608; M1 run 40496285234. 97 passing tests.
- [x] Independent code-only review (GitHub disallows self-approval), authorized PR #28 merge into PR #25 at 5b34d499fe1389a2b1b9fe66d3e425c120cc9866; combined Windows M0 #40497310164 and M1 #40497310288 SUCCESS.

## Step 2 — Direct editable document page (new staged PR)
- [x] Native continuous paper page with direct local text/heading/table-cell/caption editing mapped to canonical block IDs; module/TOC structural regions protected. Style in ribbon selects canonical block.
- [x] One validated ProjectEditor command, source-language translation staleness, Undo/Redo, Save/Open preserved.
- [x] Plain-text-only clipboard; page file/HTML/structural drag/drop disabled, photo placements untouched, DOCX/PDF derive from canonical model.
- [x] Synthetic Qt GUI/model tests for selection, edit, rollback, undo, save/reopen, TOC synchronization and DOCX/PDF export; original offscreen preview smoke retained.
- [ ] Installed Windows mouse/keyboard, high-DPI, real Word/PDF and multi-page visual acceptance (not represented by Qt offscreen tests). See EDITABLE_PAGE_CONTRACT.md.
- [x] Implementation in staged draft PR #29, code SHA 0d08f351bb5a4c5bc430562a8c8aa9cd4710a9a6; exact Windows M0 #40499581827 and M1 #40499582022 SUCCESS; local 102 tests + offline GUI smoke PASS.
- [ ] Independent review of PR #29 and approval before integration into PR #25.

## Step 3 — Safe local DOCX/DOTX template import (new staged PR)
- [ ] Bounded OOXML ZIP and relationships inspection; no external content fetching, macros, embedded scripts or silent template data transmission.
- [ ] Capture page size, margins, headers, footers, embedded logos, supported paragraph styles and page elements as a portable template, independent of report facts.
- [ ] Visual template editing, explicit unsupported-object warnings, safe persistence/schema versioning, reversible import and DOCX/PDF parity.
- [ ] Synthetic fixtures plus private installed Windows testing of the user's sample only locally.

## Step 4 — Integration and Windows release acceptance
- [ ] Review/reconcile PR #22, #25 and their accepted corrections against current main, exact-head required CI and history.
- [ ] Install exact built candidate on Windows and verify font faces/sizes, page editing, save/reopen, database, images/HEIC, DOCX in Word, PDF print, template import, dark/light themes and DPI.
- [ ] Publish/promote one current release only when critical installed-Windows acceptance passes and user approves.

Steps 2–4 remain pending and are not implied by Step 1 CI.
