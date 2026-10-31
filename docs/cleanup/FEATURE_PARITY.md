# Phase 1 — V1 / native V2 / HTML Studio feature-parity register

**Source baseline:** `main@8b52776984f6190fa2a0f657af9376f4f1cc5d5f`, 2026-10-31. **Purpose:** gate retirement, not imply user/Windows acceptance.

**Legend:** **S** = implemented/covered in inspected source or tests (not physically accepted); **P** = partial, wrapped through native dialog, or known limitations; **G** = identified gap; **U** = unverified. A cell is not evidence of end-user acceptance. All three versions must be evaluated with realistic synthetic projects on physical installed Windows before promotion.

| Capability | Legacy V1 | Native V2 | HTML Studio | Evidence / action |
| --- | --- | --- | --- | --- |
| Canonical hierarchy, nested modules, conclusions, derived TOC | S | S | S | `model.py`, `engine.py`, `tests/test_m2_project.py`; HTML delegates to `CommandGateway` in `v2/web_ui.py` |
| Ordered text, headings, photos, tables, breaks | S | S | S | `tests/test_m4_export.py`, `v2/branch/canvas.py`, `v2/web_ui.py`, `web_assets/studio.js` |
| Native structured `.rmproj` save/reopen and migration | S | S | S | Shared `project_io.py` and V2 persistence adapter; HTML delegates to native session; validate older archive fixtures separately |
| Manual and DB-linked customer/site/machine snapshots | S | S | S | `reference.py`, `storage.py`, `v2/report_info.py`, `v2/web_edits.py`; HTML linked-field lock F09 fixed in PR #121 |
| Metadata: dates, ticket, personnel, multiple intervention types | S | S | S | `model.py`, `tests/test_m2_project.py`, HTML header dispatch; inspect all controls on Windows |
| Original/translation/stale provenance for arbitrary language tags | S | S | P | Shared data/export; HTML uses native dialogs for translation and exposes source wording, not a full HTML translation editor |
| Rich paragraph formatting and selection toolbar | S | S | P | `rich_text.py`, `v2/editor_tab.py`, `v2/web_edits.py`; HTML supports rich commands but input is not fully WYSIWYG (PR #121 validation) |
| Complex style-preserving multiline sorts | U | U | G | HTML rejects styled sort rather than silently stripping formatting; plan a style-safe operation only if required |
| Draft Apply/Discard/Cancel, Undo/Redo and stale revision protection | U | S | S | `v2/session.py`, `v2/commands.py`, `tests/test_v2_save_applies_drafts.py`, PR #121 Chromium tests |
| Gallery, clipboard paste, external drag/drop | S | S | P | `photo_gallery.py`, `v2/gallery_tab.py`, `v2/web_ui.py`; HTML import/paste exposed, external file drag/drop not independently accepted |
| Ten photo annotation tools and per-placement visuals | S | S | P | Shared `photo_editor.py` retained; HTML invokes native `V2PictureEditorDialog` instead of duplicating tools |
| Word/DOCX template import, branding, header/footer | S | S | P | Shared `template_import.py`; HTML opens V2 native import dialog; fidelity issue #45 remains |
| **Visual template editing dialog** | **S** | **G** | **G** | V1 `visual_editor.edit_document_template` / `template_dialog.edit_template_layout`; explicit parity decision **required before V1 removal** (#116) |
| Editable DOCX, derived paginated PDF and multi-language bundle | S | S | S | Shared `export.py`, `v2/language_bundle.py`, `tests/test_m4_export.py`, `tests/test_v2_m6_bundle.py`; page fidelity still must be visually accepted |
| Live page proof and precise PDF proof | U | S | S | `v2/preview_tab.py`, `v2/pdf_proof.py`, `v2/web_ui.py`; HTML live view is schematic, PDF proof uses exporter |
| Isolated user-controlled ChatGPT website/fallback | S | S | S | `v2/chat_tab.py`, `v2/web_ui.py`; HTML drawer reuses isolated ChatTab; actual login unsupported/unverified |
| Native Windows packaged/frozen/install/uninstall | Historical build | Hosted preflight S | Hosted preflight S | `v2-m7-packaging.yml`, `docs/v2/PR121_HTML_VALIDATION.md`. **Neither V2 GUI has completed the 33-case physical installed-Windows matrix (#96)** |
| Windows high-DPI, clipboard, Explorer drag/drop, light/dark contrast | U | U | U | Physical acceptance outstanding; native #98/#99 and Linux #100–103 require separate applicable retests |
| SOLIDWORKS SLDASM assembly visualization | G | G | G | Future feature #51; **out of scope** for repository clean-up |

## Evidence and classification discipline

1. **S means source-implemented with at least an existing code/test path, not observed parity.** An HTML button calling a native dialog counts as **P** for fully HTML-native UX.
2. Feature ownership is not inferred from directory names. The 11 shared root modules identified in #116 are still used by V2: `engine`, `export`, `media_import`, `model`, `photo_editor`, `photo_gallery`, `project_io`, `reference`, `rich_text`, `storage`, `template_import`.
3. V1-only candidates are `__main__` (must route, not just delete), `ui`, `visual_editor`, `page_editor`, `rich_editor`, `template_dialog`, `customer_ui`, and `customer_probe`, `editor_probe`, `export_probe`, `layout_probe`. These remain for rollback and specific legacy regression coverage until signed off.
4. HTML currently constructs a **hidden native V2 main window** for its session/dialog orchestration (`v2/web_ui.py:V2WebMainWindow`). This is a technical debt item for Phase 4, not a license to copy/replace the canonical model.
5. The HTML `rmstudio://app` page's privileged QWebChannel dispatch and isolated ChatGPT website must remain separate. Never allow remote web content to request canonical commands.
6. Prior to Phase 5, use real input fixtures and the native acceptance checklist to turn every **P/U/G** into a recorded decision: validated parity, approved supported limitation, feature port, or explicit retirement. No silent feature loss.

## Focused follow-ups

- **Mandatory decision:** port visual template editing from V1 or explicitly defer it with a reversible external workflow.
- **Required UI exercise:** photo import/annotation, formatting selections, all Word ribbon commands, all gallery affordances, keyboard focus, save/reopen and exports after style edits on both HTML and native V2.
- **Windows release:** redo #96 33-case checklist on the exact accepted build, with #98/#99 and #45 retests; hosted CI/offscreen Linux is not a substitute.
