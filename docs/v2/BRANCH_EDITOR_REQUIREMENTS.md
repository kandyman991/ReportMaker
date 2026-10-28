# RM-BE-001 — ReportMaker V2 Branch Editor Requirements

**Version:** 1.0 · **Date:** 2026-10-28  
**Status:** All 33 features selected; implementation not started  
**Design reference:** User-approved connected, vertically ordered, directly editable branch sketch/mockup  
**Roadmap:** [M0–M7](ROADMAP.md) · **Architecture:** [V2 contract](ARCHITECTURE.md)

## 1. Product intent and definitions

The **Modules** tab becomes ReportMaker V2's **main working workspace**. Users edit **inside a visual branch**, not in a separate module navigator and unrelated middle workspace. Expanded modules and submodules display actual editable text, photos/captions and tables, with connecting lines showing parentage and top-to-bottom positioning determining canonical document order.

- **Report root:** Metadata and top-level intervention modules, followed by dedicated mandatory final Conclusions.
- **Module / submodule:** The same structural container at different nesting levels, with an editable title and freely ordered mixed children.
- **Content block:** Paragraph, heading, photo, table, page break or another supported typed leaf; visible actual content, not only a title/icon.
- **Branch:** A container and its descendants; collapse affects visibility only.
- **Canvas state:** Expansion, zoom/pan/focus and similar presentation data independent of printable document content.
- **Canonical hierarchy:** Sole authoritative report structure; all views, saved projects, numbering, summary and exports derive from it.

**Reconciliation of feature 33:** The original selected checklist included AI editing of selected content, but the user's **later explicit decision supersedes automation**. The existing embedded ChatGPT website stays as-is: AI writing text moves through manual user-directed plain-text copy/paste only. Ordinary user-initiated browser image copy/download remains allowed, but images enter reports separately through the validated Gallery/clipboard/local-file importer. No API, website automation, automatic synchronization, proposal insertion or background AI operations. BE-I06 below records that final scope.

## 2. Complete functional requirements and acceptance criteria

All entries below are **KEEP**. There are **no DISCARD items**.

### A. Layout and hierarchy (6)

**BE-L01 — Branch Editor becomes the main workspace.** Modules tab provides one large branch editing canvas, replacing V1's permanent separate navigation tree and central detached editor.  
**Accept:** Build and edit a basic report in the branch view without navigating to another text workspace.

**BE-L02 — Visual branch connections.** Draw Main → Module → Submodule connecting lines and nested containers.  
**Accept:** Every expanded module shows an unambiguous parent relationship before and after moves.

**BE-L03 — Unlimited submodule nesting.** Modules can contain submodules recursively, without a product-facing fixed depth tier.  
**Accept:** Deeply nested synthetic projects save/reopen safely; only explicitly reviewed resource/security limits may reject excessive inputs.

**BE-L04 — Actual content visible inside each branch.** Show real editable text, photo thumbnails/captions and table cells in expanded branches. **Expanded cards have intrinsic/natural height** (Compose-style content measurement): they grow or shrink with their complete text, media or table content, and reflow as the workspace width changes. No arbitrary maximum card height, internal editor scrollbar, or visible Branch Editor scrollbar is permitted. A longer report must still support wheel/touchpad and keyboard/caret navigation in the single continuous workspace.
**Accept:** Ordinary editing starts at the visible block without a detached editor; long multilingual text is fully visible without inner scrolling or overlapping the next card at multiple viewport widths; shortened text shrinks; committed text, Undo/Redo and resizing preserve natural geometry; keyboard caret and wheel actions can reach off-screen content.

**BE-L05 — Ordered vertical layout.** Children appear in the exact canonical document sequence, including alternating content blocks and nested submodules.  
**Accept:** The canvas order matches saved and exported report order.

**BE-L06 — Remove redundant navigation tree.** V2 shall not show or persist a permanently separate duplicate module tree.  
**Accept:** Navigation is contained in the branch canvas; no second hierarchy requires synchronization.

### B. Direct content editing (7)

**BE-E01 — Edit text directly inside its branch.** Use safe native rich text editing for paragraphs/headings, including selection and Unicode.  
**Accept:** Typed/selected/formatted text and translation provenance survive save/reopen, with correct undo.

**BE-E02 — Edit module/submodule titles inline.** Rename from the visible module header.  
**Accept:** Canonical title, outline and derived TOC update together; undo restores the previous title.

**BE-E03 — Display photo thumbnails.** Show actual project-owned images and optional captions at their branch positions.  
**Accept:** Thumbnail and applicable placement transformations reappear after reload; missing assets are visibly reported.

**BE-E04 — Edit, replace and annotate photos.** Access supported crop/rotate/straighten/flip/annotation tools and explicit replacement from each image block.  
**Accept:** Editing does not mutate original asset bytes, supports independent placements and updates preview/export without silent loss.

**BE-E05 — Display and edit tables inline.** Edit cells, add/remove rows and columns without leaving the branch.  
**Accept:** Table data and structure round-trip and appear in DOCX/PDF; unaffected translations remain intact.

**BE-E06 — Add blocks at any valid position.** Insert paragraph, heading, image, table, page break or nested module in the selected container/index.  
**Accept:** Insertion occurs precisely between the chosen neighboring mixed blocks.

**BE-E07 — Formatting toolbar only while editing.** Show rich-text controls for active text instead of permanently displaying them on every text block.  
**Accept:** Formatting preserves focus/selection; inactive blocks stay visually uncluttered.

### C. Structure and movement (7)

**BE-S01 — Drag-and-drop reordering.** Reorder/reparent modules, nested modules and movable content blocks.  
**Accept:** Moved subtrees preserve IDs, text, photo placements, tables and translations across undo and save/reopen.

**BE-S02 — Explicit drop-position indicators.** Show **Before**, **After** and **Inside** targets. Inside is valid only for a structural container.  
**Accept:** No silent nesting/merging. Reject drops into leaf nodes, the source, its descendants and invalid Conclusions targets without mutation.

**BE-S03 — Expand and collapse branches.** Independently show/hide descendants.  
**Accept:** Content is not deleted and exported report content remains complete.

**BE-S04 — Move up/down controls.** Provide an alternative to mouse drag.  
**Accept:** Correct sibling ordering with boundary conditions disabled and undo supported.

**BE-S05 — Duplicate, delete and unmerge.** Duplicate with fresh IDs, delete with confirmation/undo and implement Unmerge as **Outdent** (move selected nested module one level out after its former parent).  
**Accept:** No hidden data loss. Do not promise reconstruction of arbitrary historical merge without retained information.

**BE-S06 — Remember expansion/collapse state.** Store by stable module identity and restore when reopening.  
**Accept:** Saved expansion states return without altering final document content.

**BE-S07 — Collapsed module summaries.** Show counts for descendant modules/submodules, text blocks, photos and other block types.  
**Accept:** Summaries are derived from current canonical data and refresh after moves/insertion/removal.

### D. Navigation and usability (7)

**BE-U01 — Focus mode.** Isolate one module/subtree as the workspace.  
**Accept:** Exit restores previous context; structure and export remain unchanged.

**BE-U02 — Zoom, pan and fit-to-screen.** Navigate large canvas layouts.  
**Accept:** Windows-DPI-consistent navigation; canvas zoom does not change print scale.

**BE-U03 — Search inside branches.** Find titles, text and photo captions, including in collapsed descendants.  
**Accept:** Result selection reveals/focuses the correct stable node.

**BE-U04 — Context menus.** Right-click context-specific insert, rename, move, duplicate, delete, format, image/table commands.  
**Accept:** Menus reuse the validated command engine; invalid commands are unavailable.

**BE-U05 — Block resizing.** Adjust text area, image display and table width with safe layout.  
**Accept:** No overlap/reparenting; defined persistence and print semantics are upheld.

**BE-U06 — Drag images from Windows Explorer.** Accept supported local images at a branch insertion point using safe copy/conversion, never deleting/moving originals.  
**Accept:** Imported asset survives project reopen without original external file; unsafe/remote/HTML input is rejected; pending edits remain safe.

**BE-U07 — Paste images from clipboard.** Accept verified native pixels or supported local image-file list at an intentional insertion location.  
**Accept:** New image block created, or an existing image replaced only on explicit request; no arbitrary website HTML is interpreted as image data.

### E. Integration and data integrity (6)

**BE-I01 — One canonical report structure.** Branch Editor, Editor, Gallery association, summary and export use the same stable IDs and report objects through controlled commands.  
**Accept:** Changes appear consistently, with no independent persisted list or silently discarded conflicting edits.

**BE-I02 — Automatic numbering and TOC.** Derive numbering/summary from canonical hierarchy, with Conclusions as final logical/export section.  
**Accept:** Rename, insert, delete, reorder and nesting recompute derived numbering and TOC immediately.

**BE-I03 — Keep separate Editor tab.** Preserve precision document/page formatting and supported content editing.  
**Accept:** It edits the same canonical blocks; cross-tab draft conflicts require explicit resolution.

**BE-I04 — Keep Photo Gallery and ChatGPT tabs.** Gallery uses project-owned media; ChatGPT keeps existing user-controlled embedded browser and fallback.  
**Accept:** Gallery placement links to canonical photo blocks; ChatGPT has no automatic access to report content.

**BE-I05 — Live printable-page preview.** Preview reflects committed structure, formatting, photo edits and export settings; mark approximate pagination when relevant.  
**Accept:** Refresh never discards pending drafts; supported content and annotations appear in produced DOCX/PDF, with native output checks.

**BE-I06 — Manual ChatGPT-assisted copy/paste only, superseding automated AI editing.** User selects/copies a branch block, manually pastes into the ordinary ChatGPT site, manually copies a response, reviews and intentionally pastes it into the chosen branch. Ordinary manual browser image copy/download remains available; images must be explicitly added through the separate validated Gallery/clipboard/file import workflow.  
**Accept:** No OpenAI API, browser script/DOM access, scraping, automated data synchronization, hidden proposals or unattended insertion. Text is pasted as user-directed plain text and normal editor undo applies; leaving a response unused causes no report modification. Browser images are not inserted automatically; manual image imports follow BE-U06/BE-U07 and project-media safety rules.

**Feature count:** 6 layout + 7 editing + 7 structure + 7 usability + 6 integration = **33 selected requirements**.

## 3. Non-functional acceptance contract

1. **Canonical integrity:** unique IDs, valid node ownership/order, no cycles, dedicated final Conclusions, multi-select intervention types and optional manual customer snapshots.
2. **Atomic changes:** structural commands, rich text and table changes are validated; invalid operations keep report, pending drafts, media and undo intact.
3. **Cross-tab editing:** unsaved Branch Editor / page Editor drafts are reconciled explicitly, never silently overwritten.
4. **Multilingual:** open language identifiers, original wording, per-language variants and stale-on-source-edit behavior remain intact.
5. **Photo safety:** controlled offline import, project-owned immutable working assets, per-placement non-destructive edits, reusable assets and private review layer excluded from customer exports.
6. **Persistence:** current portable project format v4 represents canonical hierarchy; only introduce versioned v5 if justified, with safe legacy v1–v4 read and Save As preserving original.
7. **Export:** Branch canvas geometry is not printed pagination; consistent DOCX/PDF content, tables, photo annotations and derived numbering required.
8. **Performance:** render large/expanded/deep reports without unbounded active editors or rerendering on each keystroke; cursor/focus preserved.
9. **Windows:** native installed Windows acceptance for mouse drag, clipboard, keyboard, zoom/DPI, fonts, external file drop and embedded browser.
10. **Privacy/security:** synthetic CI fixtures only, no customer images/reports/CAD or browser profiles in Git; no unrequested network/browser transfer.

## 4. Regression scenarios

| Scenario | Required result |
| --- | --- |
| Deep module nesting and mixed block order | Save/reopen/export preserve exact structure |
| Edit text/heading/title inline | Correct formatting, Unicode selection, stale translations |
| Move module before/after/inside | Correct canonical index/parent, full subtree retained |
| Drop on leaf/self/descendant | Rejected, no accidental merge or data loss |
| Outdent, move arrows, duplicate, delete, undo | Safe reversible structural operations; fresh duplicate IDs |
| Collapse/expand, focus, search, zoom | Correct selected node and UI state; print unchanged |
| Inline table row/column/cell changes | Data and translations preserved, output correct |
| Explorer/clipboard image import | Copy-only local assets, original untouched, reload works |
| Multiple placements of shared photo | Independent annotations and correct export |
| Conflicting branch and page drafts | Explicit resolution, no silent loss |
| Generated numbers/TOC after restructure | Correct derived outline, Conclusions last |
| Preview and DOCX/PDF after image edit | No missing/flattened annotations or hidden errors |
| Manual ChatGPT browser copy/paste and image handling | No automatic integration; user-initiated text paste only, with any manually copied/downloaded browser image separately validated and imported |
| Legacy and corrupt project inputs | Safe migration or rejection, source unchanged |
| Native installed Windows validation | Real DPI, focus, drag/drop, paste and file workflows pass |

## 5. Definition of done and authorization boundary

All **33** requirements must satisfy their acceptance criteria with repeatable tests and evidence on the exact code SHA, including real installed-Windows tests for platform-dependent interactions. The Branch Editor must let a user construct and edit a complete report without V1's separate tree/content workflow. Source projects, customer privacy, multilingual text, image safety, Conclusions-last, exports, and manual ChatGPT browser-only interaction are mandatory.

**This documentation PR does not authorize M0 implementation, merging into main, changing the V1 installer, or publishing a release.** Following review/approval, the next milestone is M0's dependency inventory and interface contracts.
