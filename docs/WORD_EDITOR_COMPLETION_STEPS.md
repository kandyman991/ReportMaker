# Word editor — staged completion and acceptance

Checkpoint 2026-10-27. Draft rich-text editor PR #25 is stacked on preview contrast PR #22.

## Engineering rules

The report/project canonical hierarchy and language provenance stay authoritative. Direct page editing must use guarded report commands, not independent HTML. The generated Summary/TOC always derives from the module tree. Keep private Word templates, photographs and customer data on the user's computer; only synthetic tests in this public repository. No main merges or installer/release publication without user authorization.

## Step 1 — PDF text fidelity (PR #28)
- [x] Paragraph borders rendered, including shaded paragraphs.
- [x] Correct continuous decimal and alphabetic numbering with resets and cross-block continuation.
- [x] PDF-level tests inspect graphics operators and extracted text.
- [x] Hosted Windows exact-code-head CI success for 1ff7d6544e251f9f43b9743afe833172eed4eaff: M0 run 40496286608; M1 run 40496285234. 97 passing tests.
- [ ] Independent correction review, then user-authorized merge into PR #25, then combined exact-head CI.

## Step 2 — Direct editable document page (new staged PR)
- [ ] Page selection and local text/heading/table/caption editing mapped to canonical block IDs; structural module/TOC regions protected and separately controlled.
- [ ] Source-language and stale-translation semantics preserved; changes applied with command-engine Undo/Redo and Save/Open.
- [ ] Clipboard is plain-text/untrusted, structural drag/drop guarded, photo placement preserved, DOCX/PDF derives from canonical content.
- [ ] Synthetic GUI tests for layout, selection, editing, undo, printing, save/reopen and TOC synchronization.

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
