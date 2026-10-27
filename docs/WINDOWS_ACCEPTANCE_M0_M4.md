# Consolidated native Windows acceptance — M0 through M4

**Status: ALL ITEMS PENDING unless independently recorded with installed-Windows evidence.**
Use synthetic report data and photographs only. Do not upload company reports, screenshots of private machines or browser session/credentials to GitHub. Hosted \`windows-latest\` tests validate automated code paths, **not** installer/interactivity acceptance.

Prerequisites: an explicitly approved and installed M4 preview build (M0 release does not contain M3/M4); Windows x64, Microsoft Word desktop to evaluate DOCX fields, a local PDF viewer and at least one synthetic test \`.rmproj\`. Record installer version/source commit, Windows version/DPI, Word version and pass/fail per group.

## M0 shell / browser
- [ ] Install, launch from Start menu without Python/Git, exit, restart and uninstall/reinstall. Confirm no unexpected permissions and no lost local project data.
- [ ] Resize/collapse/restore/maximize all three panes; verify splitter widths and visibility persist across restarts at 100%, 125% and 150% display scaling.
- [ ] ChatGPT browser panel uses ordinary website, only manually operated. Test normal sign-in/restart persistence and fallback to default browser. Never share credentials/logs/cookies for evidence.

## M1 customer database
- [ ] Create/search/update synthetic customer, multiple sites and machines, serial and contact data. Inspect machine intervention history.
- [ ] Verify frozen report snapshots stay unchanged when a master customer is edited or deleted.
- [ ] Create and reopen fully manual one-off customer/site/machine report; it must not create a master record.
- [ ] Validate safe local backup/restore with app closed when applicable, including failure/cancel scenarios.

## M2 project engine
- [ ] Save/open/save-as \`.rmproj\` with mixed/nested text/photo/table/page-break blocks, translation metadata and both intervention type checkboxes selected.
- [ ] Verify corruption/open failure preserves the previously open project; failed save does not alter a valid existing file.
- [ ] Verify moved/duplicated/nested content retains associated photo and translations, including after reopen, and Conclusions are last.

## M3 visual editor
- [ ] Mouse drag-and-drop module parent/child and content blocks in mixed order, then verify tree and Summary reflect identical ordering and numbering.
- [ ] Confirm live preview displays image, caption, multiline paragraphs and table edits; test keyboard shortcuts/focus and long documents with scrolling.
- [ ] Check pending valid and invalid edits with Save/Discard/Cancel, Undo/Redo, New/Open/Close, across restarts; no drafts silently lost.
- [ ] Exercise customer database snapshot selection and return to manual mode; no hidden address/contact/serial reused for renamed identity.

## M4 Word and PDF
- [ ] In the **installed** program, export both DOCX and PDF from a synthetic project with nested 1, 1.1, 1.1.1 modules, paragraphs, photo/caption, ragged table, page break, multiple intervention types, Other details, manual customer snapshot and Conclusions.
- [ ] Configure **Export branding** using a synthetic company name, optional synthetic logo (PNG with transparency and JPEG alternative) and footer note. Confirm the branding repeats on every Word/PDF page, logo aspect ratio and legibility, and a cleanly reserved header/footer at 100% print scale. Restart the application and verify local profile restoration without affecting any report or browser data.
- [ ] Replace the configured logo with a missing/corrupt or oversized test asset. Export must fail with a visible warning and must preserve existing Word/PDF files. Clear the logo, retry both exports and confirm no stale logo remains.
- [ ] Check Word footer PAGE fields, dynamic PAGEREF section references after Ctrl+A/F9, and PDF's independent final page count. Explicitly inspect header/footer and Summary against a 10+ page synthetic report; Word/PDF do not need identical pagination.
- [ ] Inspect landscape and portrait test photos including EXIF rotation, very small and large resolutions. Neither renderer should enlarge small sources or crop/overflow images; captions should remain alongside their images where the page permits, including after a manual page break.
- [ ] Inspect long company names, non-Latin labels, wide/ragged tables and a non-splittable oversized table row. Report controlled errors, truncation, orphaned captions or font substitutions rather than accepting a visually broken document.
- [ ] Open DOCX in desktop Word. Verify paragraphs, headings, table cell contents and inline photographs can actually be edited. Confirm source report contents still match the unedited \`.rmproj\`.
- [ ] In Word, select all Ctrl+A and update fields F9, or accept Word's update-fields prompt; validate each Summary section page number against its final rendered page after any pagination. Update again after changing text length. Never treat \`?\` as a resolved page number.
- [ ] Open PDF in local viewer; verify Summary page numbers, all pages/footers, mixed nesting, page breaks, photos and tables. Inspect visually at 100% and test printing.
- [ ] Verify at least Italian accented characters, newline layout and the desired additional script/language; record unsupported glyphs, word-wrapping issues and font fallbacks.
- [ ] Use Save As dialog to confirm Cancel and overwrite behavior. Export with invalid pending data/missing photo should fail visibly without replacing earlier good output.
- [ ] Confirm that exporting a dirty in-memory report does not reset dirty indicator or overwrite \`.rmproj\`, that separate DOCX/PDF files are created locally, and that reopening source still has its original saved values.

## Exit criteria
A dated installation-test record tied to an **exact installer and source SHA**, recorded per checklist category with redacted/synthetic-only evidence, is required before calling M0–M4 installed-Windows acceptance complete. Any failure is addressed in a reviewable PR; no release or merge follows automatically from this checklist.
