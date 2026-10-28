# M0 — V2 architecture blueprint and binding decisions

**Review status:** M0 design proposal. **Source baseline:** `main e50557a5a89a20095ea525eafec281894cccd876`. Cross-reference [dependency audit](M0_DEPENDENCY_AUDIT.md), [interface contracts](M0_INTERFACE_CONTRACTS.md), [compatibility and verification](M0_COMPATIBILITY_AND_TESTS.md), [M1 boundaries](M1_IMPLEMENTATION_PLAN.md), and the approved [33 requirements](BRANCH_EDITOR_REQUIREMENTS.md).

## Decision record

- **M0-D01 — New shell / primary workspace:** Build a new `reportmaker.v2` PySide6 app, starting in a large, **directly editable connected Branch Editor**. Branch root → module → nested submodule, with real text/photographs/tables in canonical vertical order. Never use `VisualReportEditor` or the V1 three-panel splitter in V2.
- **M0-D02 — One shared core:** Use the existing `reportmaker.model`, `engine`, `project_io`, `rich_text`, `reference`, `storage` and related public APIs. No forked serialized `V2Report`, no independently edited outline or sidecar report tree.
- **M0-D03 — V4 compatibility:** **No schema v5 for M1.** V4 already stores mixed nested blocks, stable IDs, multilingual source+translations, rich text and photos. Store expansion, zoom, pan, focus, selection and presentation-only resize in **versioned device-local settings**, separate from `.rmproj` and export. No portable canvas layout promise. Schema change needs a separately approved ADR plus migration tests.
- **M0-D04 — Transactions and drafts:** Only the application command gateway can publish canonical changes; view widgets keep temporary drafts in a coordinator keyed by stable `(report_id, module_id, block_id, field)` and document revision. Edits are committed as one validated operation on Apply, blur or guarded navigation, never on every keypress.
- **M0-D05 — Qt as adapter only:** Core/report data must import with Qt and WebEngine absent. Qt widgets may depend on pure services, never the reverse. Neither photo media nor export obtains content by reading widget state.
- **M0-D06 — Browser unchanged:** Keep the current user-operated embedded ChatGPT website, local WebEngine profile and external-browser fallback, with manual plain-text copy/paste. User-selected browser images may be manually copied/downloaded then imported through existing safe local media path; no API, agent, scripting, DOM, cookie transfer, context sync, or automatic image or AI insertion.
- **M0-D07 — No physical page in branch:** Canvas zoom/pan/display resize only affects workspace state. Page geometry, template profile and print formatting use existing export/page services. Derived TOC and numbering come only from `module_outline`; dedicated Conclusions remains last.
- **M0-D08 — Safety limit:** No fixed business tier (e.g. only 3 submodule levels). Keep the currently validated **256-level defensive depth cap** as a security/resource guard for M1; document its limit and require iterative serialization or explicit lower proven-safe bound if load/save at depth 256 fails. Do not advertise absolute unbounded recursion or silently weaken validation.
- **M0-D09 — Failed-closed rendering:** The existing exporter rejects edited `PhotoVisual` when unsupported; V2 must disclose export incompatibility without data loss and must not claim full annotated export before M6 validation.
- **M0-D10 — V1 continuity:** Existing `src/reportmaker/ui.py`, `visual_editor.py`, `__main__.py` behavior, V1 entry point, installers, assets, and root architecture stay unchanged in M0/M1. M1 adds a separately addressable V2 entry path; no V2 default installer until M7 review.

## Package organization (proposed, subject to M1 file-size review)

```text
src/reportmaker/                     # SHARED EXISTING, no duplication
  model.py  rich_text.py  reference.py
  engine.py  project_io.py  storage.py
  media_import.py  export.py  template_import.py
  rich_editor.py  photo_editor.py  photo_gallery.py
  page_editor.py  ui.py  visual_editor.py  # V1 only; not imported by V2
  v2/
    __init__.py
    __main__.py                        # explicit V2 launch, no V1 replacement
    app.py                             # fresh QMainWindow; Branch Editor default
    session.py                         # report session, revision, dirty/open/save
    commands.py                        # typed intents -> ProjectEditor adapter
    projections.py                     # read-only stable-ID view rows/outline
    drafts.py                          # edit session, conflict/commit policy
    presentation.py                    # local versioned view state (not report)
    branch/
      canvas.py                        # scroll/viewport, connectors, lazy layout
      module_card.py                    # container + inline title
      content_card.py                   # paragraph/heading/table/image surfaces
      drop_planner.py                   # BEFORE/AFTER/INSIDE proposals
    adapters/
      rich_text.py                      # Qt rich editor/ribbon against field draft
      media.py                          # safe existing import/photo gallery/render
      persistence.py                    # load/save/legacy Save As coordinator
      preview.py                        # export plan/preview boundary
      metadata.py                       # snapshot/customer information facade
      browser.py                        # same manual embedded browser + fallback
    tabs/
      editor.py                         # later, same canonical block IDs
      gallery.py                        # later, same project media library
      chatgpt.py                        # later, existing WebEngine behavior
```

This is an **ownership map**, not an authorization to create all files in M1. Avoid empty scaffolding and needless wrappers; M1 implements only the minimum files in [M1 implementation plan](M1_IMPLEMENTATION_PLAN.md). `browser.py` may initially be an extracted narrow Qt widget implementation, but it must mirror existing V1 user-controlled behavior and not import `ui.MainWindow`. The separate V2 app can defer top-level tabs other than the Branch Editor until scheduled milestones.

## Runtime ownership

| Owner | Owns | Must not own |
| --- | --- | --- |
| `ReportSession` | One `ReportProject` working session, `ProjectEditor`, project generation token/revision, current path, source version, dirty/save lifetime; local user-confirmed transitions | Browser account, independently serialized UI tree |
| `CommandGateway` | Validated report mutations; pending projection notifications; atomic undo/redo; stable-ID addressing; permissions for Conclusions/root | QWidget pointers or printable HTML |
| `EditSessionCoordinator` | One outstanding draft per editor+stable field; base revision; conflict/discard/commit prompts and clipboard commit guard | A second source of report truth or silently synchronized report clone |
| `ProjectionBuilder` | Read-only branch rows, derived counts, outline and selection via IDs | Persisted navigation list, new mutable model |
| `PresentationStore` | Device-local expansion, focus, zoom, pan and view dimensions; versioned keys | Printable report changes, private browser data, `.rmproj` schema |
| `BranchCanvas` | Layout, connectors, scroll, visible widgets, keyboard/drag hit testing | Saving the structure or changing report directly |
| `MediaAdapter` | Shared project-owned asset library, approved imports, thumbnails, placement edits; session-token checks | Direct website/HTML image fetch, external original modification |
| `PreviewExportFacade` | Read-only validated `ReportProject` snapshot and output profile; explicit fidelity/errors | Branch geometry or unsaved draft omission |
| `BrowserTab` | User-controlled Qt WebEngine and fallback, user-driven clipboard only | Report model access, scripts/DOM/API, transfer of report data |

## End-to-end data flow

```text
Keyboard / selection / insert / drag / file drop
    -> BranchCanvas, ModuleCard or ContentCard (ephemeral widget)
    -> EditSessionCoordinator (draft + base revision, guarded flush)
    -> DropPlanner / CommandGateway (stable IDs; explicit typed intent)
    -> ProjectEditor.apply (deepcopy candidate + validate + atomic publish)
    -> ReportSession revision increments; change event of affected IDs
    -> ProjectionBuilder (same model, derived outline/counts)
    -> BranchCanvas incremental refresh / Editor / Gallery / Preview invalidation
    -> user Save/Save As: ReportProject(report, project-owned assets/library)
    -> project_io.save_project -> .rmproj ZIP v4
    -> export.prepare_export/export_project -> independent DOCX/PDF
```

`Open`: validate `load_project` and create replacement session **before** committing to a tab transition; unresolved drafts require explicit user action. Legacy v1–v3 projects remain read-only-as-source for upgrade; Save As writes new v4 archive to a different path.

**Undo**: one committed logical edit = one `ProjectEditor` operation; notify all interested views. The base V1 editor only snapshots `Report`; asset import/placement edits require an envelope-level transaction policy, described in the interface document. Do not imply media undo is solved by `ProjectEditor` alone.

## Visual model and interaction boundaries

- `Report.modules` gives ordered top-level modules; `Module.blocks` gives ordered **mixed** leaf blocks and `NestedModuleBlock` structural children. Dedicated `Report.conclusion` is a fixed final top-level section, not draggable beneath a module.
- The Branch Editor draws visible lines based on parent/child edges; the canvas itself must not persist parent pointers, node order or numbering. Leaves have live inline editors at their branch positions.
- `Before/After/Inside` are semantic target types with a highlighted preview and keyboard-accessible equivalent. No implicit merge, no `Inside` on leaves, no cycles/self/descendant drops; revalidate against the current revision at commit time.
- Connector/virtualization code should use an iterative visible-row traversal and a geometric renderer rather than one unbounded Qt widget per model descendant. Collapsed branches are still included in exports and canonical search.
- Editor and Branch Editor do not open separate projects, fork report bodies, or flush one another's drafts without coordination.
- Shared Qt rich-text helpers receive plaintext + typed `RichFormatting`; exported HTML from Qt must never be accepted as arbitrary canonical report markup.
- Photo thumbnail render reads stored working asset bytes + per-placement `PhotoVisual`; reusable assets are not duplicated on insertion. Explicit file/clipboard imports validate before creating a new `PhotoBlock`.

## High-priority architectural risks and resolutions

1. **V1 UI contamination (high):** disallow `reportmaker.v2 → visual_editor` (including transitive) in code review/CI; do not copy splitter/tree/block list. **Resolved by separate shell and import firewall.**
2. **Draft conflicts and lost selection (high):** revisioned drafts; same-field conflicts require user choice rather than last-writer-wins. **Resolved as contract; implementation M1/M3.**
3. **Full-report snapshots and layout cost (high):** debounce typed inputs; measure 1k+/5k+ nodes and batch commands; avoid full refresh on every keystroke. **Risk remains unmeasured until M1 benchmark.**
4. **Deep recursion v4 (high):** recursion in serializer/parser despite iterative validator. **M1 must test near 256 and fail safely, retaining input.** No schema change assumed.
5. **Photo visual export (known functional gap):** `export.prepare_export` raises for transformed photos. **M6 integration blocker**, not an M0 architecture blocker.
6. **Asset+report undo consistency (high):** multi-store session boundary required before complex image placements. **M4 implementation blocker**, M1 can safely defer imports.
7. **Windows Qt drag/focus/DPI/clipboard (high):** CI/headless Qt tests only support code quality; real installed-Windows interaction acceptance is separate and remains open.
8. **Template fidelity / private notes (medium):** imported letterhead and separate internal review notes are not guaranteed complete; preserve existing safe APIs, keep final feature claims gated to M6/M7.
9. **Browser UX (existing issue #64):** copying/downloading images through embedded site has reported limitations. Preserve browser-only contract; do not attempt undocumented page scripting or claim this M0 resolves it.
10. **No V2-specific package test gates yet (medium):** add import-firewall, model/Qt and Windows probe gates with first M1 code, without modifying V1 production entry point.

## M0 exit decision

The 33 feature requirements and M0 boundaries can be met **without changing the root architecture contract or `.rmproj` schema**. No ADR is required for the agreed application UI separation. Any later request for synchronized portable canvas size/position, expanded format or an AI integration would be a **new reviewed decision**, not a silent M1 implementation change.
