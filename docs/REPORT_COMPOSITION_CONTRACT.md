# Report composition and navigation contract — 2026-10-26

Status: **Agreed product requirements**. Origin: user's handwritten report-layout sketch and subsequent clarifications in the ReportMaker project chat. This document is a textual specification of the sketch; no private user/customer image or operational data is stored in this public repository.

## Report information (header)
The editor presents a **Report Information** section before the report body, with:
- Creation date (separate from intervention dates).
- Editable report title (for example, "Report of intervention").
- Intervention duration: `from` and `to`, validating that start is not after end.
- Optional reference ticket number.
- **Intervention types as a multiple-selection field**, allowing any combination of:
  - Supervision
  - Ordinary maintenance
  - Extra/extraordinary maintenance
  - Other (with editable specification when selected)
- Personnel involved (one or more technicians/participants, not just a single mandatory person).
- Customer, site and machine information (see below).
Values are report-specific, editable and stored in the canonical project. UI labels and report rendering must support the open-ended multilingual architecture rather than hardcoding output languages.

## Customer entry: database or manual
- The user can search/select an existing customer and, where available, a site/machine from the local customer -> site -> machine database.
- **Alternatively, the user can type customer/site/machine details directly without creating any database record**; database linkage and foreign keys are optional for these one-off reports.
- Capture a **report-level snapshot** of the resolved customer, site and machine attributes in either mode. Updating or deleting master data later must not silently rewrite previous reports.
- A manual customer must not silently become a master record; any future "save to database" action is separate and explicitly initiated.
- Customer entry mode is not an intervention type; neither mode changes module structure. No customer information is transmitted to the browser-only ChatGPT panel or to GitHub.

## Summary (automatically generated table of contents)
The "Summary" in the sketch is a **module and submodule table of contents**, *not* an AI-produced prose summary.
- It is generated from **the very same canonical hierarchical module structure** that powers the editor's navigation tree; never store or maintain an independent hand-edited list that can diverge.
- Add, rename, nest, reorder, duplicate or remove a module -> editor tree and summary reflect the change immediately and deterministically.
- Support arbitrary nesting depth (module -> submodule -> sub-submodule ...), stable IDs and ordering.
- Derived section numbering is based on hierarchy/order, not user-maintained numbering strings; displayed titles are the same localized title data.
- Optional exported page numbers are computed by the document exporter after pagination, not stored as permanent module metadata.
- The mandatory final Conclusions section is the last logical/export section and appears at the end of the summary.

## Report modules and content
- Any number of independently editable, re-orderable, nestable modules, each with a title.
- Arbitrary freely ordered typed content blocks within any module (text, images with captions, tables, headings, page breaks and nested modules); no forced order or fixed photo gallery.
- Photos, table content, localized variants and submodules move with their parent module.
- A separate dedicated final Conclusions section remains mandatory.
- The visual editor, the generated summary, the saved project and later DOCX/PDF export all consume the **same canonical report model**, with derived views and export layout separate from source data.

## Acceptance / non-regression scenarios (future M2–M4)
1. Check Supervision **and** Extra maintenance together; serialize/restore and export with both values intact. Select Other and preserve its specification.
2. Create a report with a selected DB customer, save a snapshot, modify the master data; the saved report keeps its original snapshot.
3. Create a report using a manually entered customer/site/machine with no DB master; save/reopen successfully with no unwanted master record.
4. Build nested modules 1, 1.1, 1.1.1, rename/reorder a parent, and verify the tree and summary remain identical in order, titles and hierarchy.
5. Delete/move a parent containing a photo/table/translations; ensure no unexpected content loss; Conclusions stays last.
6. Export DOCX with generated contents and page numbers based on final pagination, with no manually maintained second module list.
7. Verify open-ended report language codes and translations apply to header labels, module titles and content without a hardcoded language enum.

## Milestone mapping
- **M1**: customer database, optional manual customer/site/machine references, immutable snapshots and persistence boundaries (M1 preview may not yet save full reports).
- **M2**: canonical report metadata, ordered nested module/block engine, project persistence and conclusions-last invariant.
- **M3**: report-information UI, module tree and auto-derived live summary, flexible editor.
- **M4**: DOCX export/table of contents, hierarchical numbering and final-pagination page numbers.
- **M5**: fully localized text/labels and translation workflows.

See `ARCHITECTURE.md`, `docs/adr/0006-report-composition.md`, `AGENTS.md` and `CHAT_HANDOFF.md`.