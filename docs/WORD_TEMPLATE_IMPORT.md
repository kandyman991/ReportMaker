# Step 3 — Local Word document-page template import contract

Implementation: draft [PR #31](https://github.com/kandyman991/ReportMaker/pull/31), stacked on draft PR #25, not main. **No production release, native installed-Windows acceptance, or main merge is implied.**

## Import behavior
- Toolbar: **Import Word page template**. Select local .docx/.dotx; import refuses encrypted, malformed, suspiciously compressed/oversized, path-traversal, executable, embedded active content and all external OPC relationships. No XML external entities, hyperlinks fetched, macros or browser/AI communication. No ZIP contents are extracted to the filesystem.
- For supported sources, extract the first section's **page dimensions, 4 margins, header/footer distances, static header/footer text, first embedded header image/logo**, and the **Normal** paragraph font/size if present. Header/logo/image bytes are validated and bounded; the input Word file is never rewritten.
- **Issue #35 (RC2 correction):** imported header/footer static text is preserved as multi-line plain text (including Word paragraph breaks, manual line breaks and tabs), with an independent **2,048-character limit per field** shared by DOCX/DOTX import, local template validation, editable layout dialog, portable .rmtemplate and export branding. Over-limit values are rejected explicitly with the field, actual length and permitted limit; no 120-character truncation occurs. Control bytes other than line feed/tab remain forbidden. The existing package/ZIP/XML/entity/image safety budgets are unchanged. Dynamic Word field result text is omitted and disclosed; ReportMaker supplies its own live PAGE field. Imported formatting, tab-stop alignment and anchored objects are not reproduced.

- Explicit review warnings list source body content, unsupported parts, additional artwork, special header variants, floating objects and other unsupported structures. The import dialog permits editing supported fields and shows a **schematic**, not Word-paginated, white-paper view. Pressing Cancel makes no changes.
- Press Save to write a separate .rmtemplate (version 1, validated, atomic JSON profile with bounded embedded logo). The active local profile path is stored only in local application settings. **Edit active page template** updates supported fields after explicit acceptance; **Clear page template** clears selection without deleting the profile.
- No DOCX body text, customer metadata, report modules, web links, external image paths, macros or original Word package is saved in the profile. This is a design profile, not a conversion of an arbitrary document into free-floating editable Qt Word objects.

## Export and persistence
- DOCX and PDF share selected page dimensions, margins, static header/footer content and embedded logo; DOCX Normal paragraph font/size is editable. PDF uses a supported local Unicode font where available, so imported Word typeface is not guaranteed. Original per-run RichFormatting retains precedence.
- Multi-line header/footer text is retained in DOCX and rendered as separate lines in PDF where it fits the specified page margins. For PDF, the embedded header logo keeps its aspect ratio and natural-size cap (2.6 cm wide / 1.05 cm tall), then **scales down further to fit between the header offset and body top margin** instead of clipping or blocking export. A tight imported letterhead may therefore have a smaller logo in PDF than in Word; increase the top margin or reduce the header distance to give it more room. **Character-limit validation does not guarantee physical page fit:** header/footer text that is too tall, or a header offset that leaves no room, is rejected before page rendering with actionable margin/offset guidance; the existing target remains intact and no internal page-callback error is displayed. The editor preview is schematic.
- Report content and canonical module hierarchy are unaffected; Summary/TOC is still generated from the same model. .rmproj remains v4 without template data or any new project schema. Templates are portable sidecars and can be swapped independently.
- A selected but missing/invalid template **blocks export** rather than silently reverting to A4. Clearing selection returns to existing local export branding and A4 defaults. Failed saves/exports must not clobber destination.
- Original Word files and local template contents never reach the embedded website, GitHub, CI, or any network connection. Test DOCX/DOTX and images are entirely fabricated.

## Explicit limitations / next fidelity work
- Only one Word section and static header/footer are imported. First-page/odd-even variant headers, floating shapes, text boxes, arbitrary body tables, backgrounds, text wrapping, imported paragraph lists beyond Normal style and page-number objects are **not** faithfully reconstructed. Additional artwork is not imported.
- Editable page remains a native continuous view: native Word layout engine, line breaks/page breaks, custom fonts on a particular Windows installation, and logo placement are not pixel-accurate. The schematic editing dialog is a controlled presentation editor.
- Visual comparison using the user's actual template must happen **locally on installed Windows**, with their consent, without uploading the private Word document to this PUBLIC repository.
- Full source template reproduction, real installed-Windows Word/PDF output comparisons, independent code review, and exact-head Windows CI must be completed before treating Step 3 as production-accepted.

## Gates
1. Synthetic DOCX/DOTX extraction, malicious OOXML relationships/macros/paths/entity cases, portable profile corruption and no-clobber behavior.
2. Exact Windows hosted M0/M1 Qt and pure Python test suites at staged PR head.
3. Independent code review, correction PR if needed, then user-approved integration into PR #25 only.
4. Installed Windows end-to-end template render/layout/DPI/Word/PDF acceptance; reconcile PR #22; separately authorize any main merge and release.
