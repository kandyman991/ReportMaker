# M0 — Compatibility, regression, performance and Windows validation strategy

**Status:** M0 review plan; no test results are claimed by this document. **Source baseline:** `main e50557a5a89a20095ea525eafec281894cccd876`.

## Decision: use the existing .rmproj v4, no migration for Branch Editor UI

- `project_io.VERSION=4` already serializes the nested mixed hierarchy, IDs, titles, original and translated text/stale markers, paragraphs/headings with rich typography, photos with visuals, tables, page breaks, metadata/snapshots and explicit media-library membership. Branch connectors, collapse, navigation and display zoom do **not** need a project-schema extension.
- Maintain **exact** v4 serializer behavior for M1, with existing v1, v2 and v3 load support. The source project's `loaded_version` and `loaded_from` remain session provenance. For any older version, require Save As to a different file; never mutate the source on open or failed save.
- Export/page layout uses supported `ExportStyle` and local template profile; temporary canvas dimensions are device-local UI state. Use a versioned `QSettings` namespace keyed by report ID + local project identity, with stale-ID pruning and fallback defaults. Canvas-only settings are not customer/portable report data. Gallery/browser settings stay private/local.
- Unknown version (including speculative v5), invalid ZIP members, duplicate manifest keys, unsupported compression, bad hashes, unsafe asset IDs, malformed metadata, oversized/untrusted images and invalid nesting fail closed. Do not auto-downgrade.
- V2-authored v4 projects should remain **data-compatible with V1** because no new fields or kinds are written. Test cross-open using a pinned V1 build, not just a shared loader, before promising installed-V1 compatibility; V1 UI may not expose all V2 interactions.
- A future portable canvas-layout or printable layout feature that cannot be represented in v4 requires **separate reviewed ADR + v5 schema** with explicit source v1–v4 read/Save As migration, unknown-future rejection, byte-preserving image assets, rollback/backup, V1-old-project policy and independent export tests. M1 shall not introduce it.

## M0/M1 synthetic test matrix

| Area | Cases and required result | Responsible gate |
| --- | --- | --- |
| Model integrity | 0/1/many modules, Conclusions last, mixed content [text, child module, table, photo, heading, break], stable IDs/unique wrappers, multi-select types, manual customer snapshot, open language tags | Existing `test_model`, `test_m2_project`; new V2 projection tests |
| Structural commands | Insert at exact mixed index, rename, move Before/After/Inside, cross-parent nested subtree, outdent, duplicate all IDs, prevent cycle/self/descendant/Conclusions misuse; failed change leaves revision/history unchanged | CommandGateway tests; M1 subset, full M2 |
| Undo/redo | One operation = one undo; text source/translation-stale, title, subtree and table ownership all restored; redo invalidated only after successful divergent change | New command/session tests; existing `test_m2_project` |
| Legacy project I/O | Valid v1/v2/v3/v4 open, source byte-for-byte unchanged, Save As v4 to different path, reopen all IDs/media/translations; same-path legacy Save rejected; future v5 rejected | `test_m2_project`, `test_m45_media`, new V2 Save As checks |
| Corrupt/untrusted files | Truncated ZIP, duplicate members/keys, symlink path, missing/undeclared assets, bad checksum, malicious width/pixel, unsupported compression and too-deep nested input; active project/drafts unchanged | Existing I/O/media tests plus fuzz/property fixtures |
| Deep hierarchy | Levels 1, 16, 64, 128, 255, 256 and 257; check report validation, `project_io._module_to/_module_from`, `json` recursion, file round-trip, outline, rendering/search, and strict safe rejection above cap | New `test_v2_deep_nesting`; do not relax limit to make tests pass |
| Rich drafts | Unicode and supplementary codepoints, correct selected-text format, focus changes, pending drafts during rename/tab/Save, validation failure retains input, source edit flags translations stale | Existing `test_rich_editor`, `test_editable_page`, new V2 draft tests |
| Concurrent editors | Branch and Page same-block conflict, unrelated-field edits, stale revision, project-switch with queued callbacks, active draft survives invalid export/drop | New coordinator tests; full Editor integration M3/M6 |
| Drag/drop | Accurate BEFORE/AFTER/INSIDE indicators, mixed-index adjustment, invalid leaf/descendant, hover then intervening edit, keyboard alternatives, Copy-only native file source and stale project token | New `test_v2_drop_planner`, Qt tests M2/M4 |
| Media ownership | Preserve external file and approved working-copy bytes; unused gallery items persist, reused asset with distinct PhotoVisual, undo/redo avoids dangling reference, original image not required | `test_m45_media`, `test_m45_visual`, `test_issue48_photo_import`; V2 transaction tests M4 |
| Export/TOC | Derived numbering after reorder; canonical v4 data matches DOCX/PDF, final Conclusions, source language/metadata, editable Word content; edited photo fails explicitly until supported | `test_m4_export`, `test_rich_pdf_fidelity`, later V2 export parity |
| Privacy/browser | No network/API/DOM/report access from V2 BrowserTab, no browser profile/media paths in archive, manual plain-text copy/paste only, user-triggered image import gated | Static firewall and native browser tests; user interaction test M6/M7 |

### Deep nesting is an explicit gate, not an assertion of compatibility

`engine.validate_report_tree` uses an explicit stack and accepts depths up to 256. `project_io._module_to/_block_to` and `_module_from/_block_from` recurse, as can downstream Qt layout. A 256-level tree can consume significantly more Python stack frames than its module depth. **Do not assume the current v4 loader/writer safely round-trip at depth 256.** Prior to promoting deep hierarchy as supported, construct valid synthetic projects at each boundary and measure save/load/JSON/export behavior on Python 3.12 Windows and 3.11 supported runtime. If the implementation cannot safely reach 256, provide an iterative transform or explicit documented conservative **security** limit through an approved correction; fail atomically, not with an uncontrolled exception or partial project. Never promise truly infinite resources.

### Undo/redo and pending drafts

M1 implements a revisioned `ReportSession`, narrow `CommandGateway` and `EditSessionCoordinator`. Must test: one small text edit makes one undo step (not one per key); Save requires dirty drafts resolved; failed validation leaves draft and canonical unchanged; cross-project callbacks rejected by session generation; a successful Undo invalidates affected projections but not unrelated editor selection. M3 adds same-field Branch/Page conflict tests before allowing concurrent editing.

The V1 `ProjectEditor` snapshots **only Report**, not `assets/media_library`, and copies/validates the full report on every `apply`. Media transactions must be added as coordinated atomic operations in M4 and tested with undo/redo; manually changing asset maps from the Qt gallery is **not** a V2-compatible mutation boundary.

## Performance test design

Use deterministic synthetic projects with **100, 1,000 and 5,000 total mixed blocks** and real-looking but entirely fabricated data/media; include 10–20% nested modules, repeated asset placements and a deep-branch adversarial fixture. Test on Windows x64 installed app, at 100%, 125% and 150% display scaling; capture CPU, peak RSS, number of live Qt editors, render latency, typing latency, opening/Save/Undo/Redo timings and UI hang/crash events. Record hardware, Qt/Python versions, project size and SHA.

**Proposed acceptance targets** (initial budgets, must be calibrated with measured Windows evidence, not existing results):
- Ordinary typing in an active visible paragraph is responsive (<50 ms p95 per keystroke and no canonical full-copy per keypress).
- A normal collapsed 1,000-block project renders/scrolls without a proportional number of active QTextEdit/QTableWidget instances; viewport scroll should feel fluid (target >=30 fps during continuous scroll).
- Root/branch expansion and switching remain responsive without losing focus/selection; long operations provide progress or controlled cancellation, rather than freezing silently.
- Peak memory and open/save times are recorded and compared with V1; unacceptable regressions become blockers even when correctness passes. No unmeasured numerical performance claim is made.
- 5,000-block + deep fixture and worst-case photos are stress cases, not an unconditional promise to meet the interactive typing budget while fully expanded.

Instrument prototype V2 changes separately from export and file-system timings. Before optimizing, profile `ProjectEditor.apply` deepcopy and `module_outline` validation, currently O(report size) per commit, and V1 `EditableDocumentPage.rebuild` eager widget count. Use incremental revision events, visible-row virtualization and scheduled batch updates, not an alternative report tree.

## CI and native installed-Windows acceptance

**Existing GitHub-hosted gates**:
- `.github/workflows/ci.yml`: `windows-latest` Python 3.12; compile, install `.[desktop]`, Qt WebEngine import, offline Qt layout/visual-editor/export probes, complete `unittest discover`.
- `.github/workflows/m1-customer-ui.yml`: Windows customer Qt probe and complete synthetic unit suite.
- `.github/workflows/continuity-contract.yml`: Ubuntu `scripts/check_continuity.py`.
- V1 workflows are **not** acceptance of a V2 interaction until a dedicated V2 probe/test is added in M1.

**M0 documentation gates:** only `docs/v2/` newly changed; all five M0 docs and approved baseline links resolve; 33 requirement IDs unchanged; no undocumented `src/`, `.github/`, installer, workflow or original architecture modifications; markdown/code-fence and spelling/link review; PR against latest `main`, exact-head CI results recorded. Branch PR CI is requested by normal PR event; do not represent pending runs as green.

**M1 automated gates to add:**
1. `python -m compileall -q src` and `python -m unittest discover -s tests -v` on Windows.
2. `python -m reportmaker.v2 --offline-self-test`: construct root → nested module → inline text, edit title/text, Save/Open/Undo/Redo without network or browser login.
3. Import firewall: static absence of `visual_editor` in `reportmaker.v2` imports and runtime import audit that no legacy UI is loaded.
4. Synthetic v1–v4 migration/Save As regression, deterministic deep fixture and focus/selection regression; tests should not access production/home customer folders.
5. Confirm no automatic network traffic, no client photos/reports, no browser sessions/test credentials and no installer/release mutation.

**Native installed Windows matrix** (separate tracked acceptance, not simulated by GitHub runner): real pointer hit-testing, nested-branch connectors after resize, keyboard tab/focus/Unicode selection, Windows Explorer copy-only drag/drop, clipboard local image/pixels/HTML rejection, image annotations and safe file conversion, 100/125/150% DPI and mixed monitors, offline Open/Save/Save As, Qt WebEngine manual login/copy/fallback, source-format photo fidelity, installed packaged HEIF, Word/PDF side-by-side and error messaging. Document exact installer SHA and screenshots using **fabricated** fixtures only. M1 checkpoint A needs Branch Editor-native interaction; later features remain separate M2–M7 gates.

## Existing gaps / blockers retained

1. Current export intentionally refuses non-default `PhotoVisual` (M6 annotated-export blocker, not reason to mutate M1).
2. `ui.py` V1 browser image copy/download issue #64 is not addressed by M0; preserve its existing behavior, no browser scripting workaround.
3. Existing Word-template fidelity and final pagination cannot be asserted from Qt continuous paper.
4. No V2 Windows profiler measurements, V2 native UI tests, or mixed-component media transaction tests exist yet.
5. Existing protective depth=256 and recursive project serialization require boundary tests before declaring full conceptual deep nesting.
6. Exact main and PR workflow status must be rechecked live at final review; a mechanical handoff snapshot or older run is not CI proof.

**Release gate:** no change to V1 installer, default app entry, releases, `main` or production deployment from M0. User approval and full M7 native Windows acceptance remain necessary before V2 replaces V1.
