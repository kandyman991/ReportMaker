# M0 — Component interface contracts

**Status:** Proposed cross-component API contract for M1; conceptual Python signatures, not implemented functions. **Baseline:** `e50557a5a89a20095ea525eafec281894cccd876`. This document specifies behavior/invariants and allowed dependencies; implementation can choose dataclasses or equivalent explicit types without changing these semantics.

## 1. Canonical document and read projections

Use existing `model.Report`, `Module`, `NestedModuleBlock`, `ParagraphBlock`, `HeadingBlock`, `PhotoBlock`, `TableBlock`, `PageBreakBlock`, `LocalizedText`, `PhotoVisual`, and `engine.validate_report_tree`, `module_outline`. The storage model remains `project_io.ReportProject`.

```python
@dataclass(frozen=True)
class NodeAddress:
    report_id: str
    module_id: str                   # owner/structural container
    block_id: str | None = None      # None for module title or container
    field: str = "title"             # title/text/caption/table_cell/metadata
    row: int | None = None
    column: int | None = None

@dataclass(frozen=True)
class BranchRow:
    stable_id: str
    parent_module_id: str | None
    kind: str                        # module/paragraph/heading/photo/table/break
    depth: int
    mixed_sibling_index: int         # index into canonical parent's blocks, NOT filtered children
    source_revision: int
    # read-only presentation fields; not a new report model

def project_branch(report: Report, *, expanded: frozenset[str]) -> tuple[BranchRow, ...]: ...
def find_node(report: Report, address: NodeAddress): ...   # lookup by ID; no UI indices
```

No projection is persisted to `.rmproj`. It can be memoized only by session revision and local visibility state. `module_outline(report)` remains the **only** numbered outline for TOC, Editor and exports. Use iterative traversal for large/deep trees; descendant summaries count canonical descendants, including collapsed rows. A selected row is keyed by stable ID; viewport index is transient.

## 2. ReportSession and transactional CommandGateway

```python
@dataclass(frozen=True)
class CommandIntent:
    kind: str                     # one registered operation, not an arbitrary callable from UI
    target: NodeAddress | None
    args: dict                    # schema-validated by operation type
    expected_revision: int
    project_generation: str       # refreshed on New/Open

@dataclass(frozen=True)
class ChangeSet:
    revision: int
    changed_ids: frozenset[str]
    structure_changed: bool
    assets_changed: bool
    outline_invalidated: bool

class ReportSession:
    def report_snapshot(self) -> Report: ...   # detached read-only-by-convention copy, not live mutable model
    @property
    def revision(self) -> int: ...
    @property
    def generation(self) -> str: ...
    @property
    def assets(self) -> Mapping[str, bytes]: ...
    @property
    def media_library(self) -> Mapping[str, str]: ...

class CommandGateway:
    def validate(self, intent: CommandIntent) -> None: ...
    def execute(self, intent: CommandIntent) -> ChangeSet: ...
    def undo(self, expected_generation: str) -> ChangeSet | None: ...
    def redo(self, expected_generation: str) -> ChangeSet | None: ...
```

M1 can implement a narrow set of kinds: `add_module`, `add_nested_module`, `add_paragraph`, `rename_module`, `set_paragraph`, `undo`, `redo`. Internally delegate to `ProjectEditor.add_module/add_block/rename_module/apply`; a logical edit must use **one** `apply`. No direct mutation from widgets; UI never calls `report.modules.append()`. Invalid/stale intent fails without changing report, revision, undo/redo history, draft or assets. Successful commit increments revision once and publishes one `ChangeSet` on the UI thread; queued callbacks with prior project generation are rejected. **Never expose `ProjectEditor.report` or another live mutable `Report` reference to UI widgets**: Qt reads detached snapshots/read projections. Create or memoize such snapshots at a validated session revision/refresh boundary, not per keystroke or per card, and invalidate on every successful change/undo/redo. The gateway alone owns canonical mutations.

`ProjectEditor` owns report Undo/Redo and deep-copy validation. **Not yet implemented:** a comprehensive transaction including media maps. Before M4 asset-changing commands, introduce a coordinated session transaction that validates candidate report+asset library, publishes them together and restores both on Undo/Redo. Do not claim that V1 `ProjectEditor` undoes asset bytes.

## 3. DropPlanner, root and mixed indices

```python
class Placement(Enum):
    BEFORE = "before"
    AFTER = "after"
    INSIDE = "inside"

@dataclass(frozen=True)
class DropPlan:
    source_id: str
    target_id: str
    placement: Placement
    destination_parent_id: str | None
    destination_mixed_index: int
    expected_revision: int
    project_generation: str
    valid: bool
    reason: str = ""
```

`plan_drop` reads a canonical snapshot, type-checks targets and emits a visually explicit target: BEFORE/AFTER each sibling or INSIDE a structural `Module`. Validity is recomputed at `execute`. For a nested module, the draggable source is the **module ID**, and the wrapper remains a stable persisted node when moving nested→nested; inserting root→nested creates a wrapper; nested→root removes its wrapper with the original module ID unchanged. Existing engine behavior must be regression-tested for this and for mixed indices. Duplicate produces **new** IDs for every copy; movement never regenerates original IDs.

`INSIDE` is rejected for paragraph/photo/table/break leaves, self, descendant, and Conclusions as intervention parent. A normal BEFORE/AFTER must never imply implicit nesting. Conclusions is fixed as final top-level section and cannot be deleted/reparented; moving content into Conclusions must respect the locked contract. `Unmerge` means outdent the nested module to after its former parent, where valid. This contract is planned for M2; **M1 basic module/paragraph insertion must already respect mixed indices**.

## 4. EditSessionCoordinator and rich-text adapter

```python
@dataclass(frozen=True)
class DraftKey:
    editor_id: str                 # branch/page/metadata
    address: NodeAddress

@dataclass
class Draft:
    base_revision: int
    base_fingerprint: str          # hash of source value + relevant format
    edited_value: object          # text + RichFormatting, or typed cell/title
    dirty: bool = True

class EditSessionCoordinator:
    def begin(self, key: DraftKey) -> Draft: ...
    def update(self, key: DraftKey, value: object) -> None: ...  # local only
    def commit(self, key: DraftKey) -> ChangeSet: ...
    def guard_transition(self, reason: str) -> bool: ...  # resolve all relevant dirty drafts
    def cancel(self, key: DraftKey) -> None: ...
```

Drafts survive selection changes, failed validation, stale drops and rejected saves. On commit, compare the canonical **field fingerprint**, not only global revision: unrelated changes can coexist, same-field conflicts require an explicit Review/Keep Draft/Discard/Rebase choice, never silent last-writer-wins. The coordinator must run before switching projects, tabs, committing a structural move that affects the address, saving/exporting and rebuilding an active editor. No unsaved field is flushed implicitly if that would invalidate another editor's current draft. Project-generation token distinguishes identically named IDs in unrelated reports.

Text adapter: `create_editor(LocalizedText, RichFormatting)` → `SafeRichTextEdit` with `apply_rich`; `capture_rich` returns (`str`, `RichFormatting`) using existing UTF-16 indexing. `set_paragraph` calls `LocalizedText.update_original` to retain translations and flag stale languages; copy/paste is **explicit untrusted plain text**, not HTML/JS. `RichTextRibbon` is contextual while editing and must retain selection/focus, including non-BMP Unicode. Use appropriate native Qt focus/selection tests before claiming robustness.

M1 needs basic inline title/paragraph drafts and transaction batching; full formatting ribbon/table drafts/cross-tab conflicts are completed in M3, but session and conflict semantics are fixed from M1.

## 5. Persistence adapter and metadata/customer service

```python
class ProjectPersistence:
    def open(self, path: Path) -> ReportProject: ...       # use load_project; validate before replacing session
    def save(self, session: ReportSession, path: Path) -> Path: ...  # guard drafts; use save_project
    def save_as(self, session: ReportSession, target: Path) -> Path: ...  # confirm overwrite

class CustomerMetadata:
    def resolve_snapshot(self, choice: object) -> CustomerSnapshot: ...
    def apply_report_info(self, report_id: str, fields: object,
                          expected_revision: int) -> ChangeSet: ...
```

`load_project` reads valid v1–v4 and rejects unknown future versions, malformed ZIP/paths, unsafe assets, invalid IDs and metadata. An older project's original path is **never** overwritten: `loaded_version != 4` with `loaded_from` forces Save As to **different path**; preserve original bytes for rollback. A failed Open/New/Save leaves active report, all draft values, media references and undo intact. A successful Save marks the saved version/revision but does not mutate report content. All project-owned asset bytes and unused declared library members persist by existing hash-verified v4 rules.

Customer/store lookup may use `storage.CustomerStore`; report snapshots are frozen (local/manual one-off customer permitted, no DB record required). Metadata commands preserve created date, intervention from/to, ticket, personnel, multiple intervention categories and open-ended output language tags. GUI fields do not link directly to mutable database objects.

## 6. MediaAdapter and Gallery/photo editor

```python
class MediaAdapter:
    def import_local(self, sources: Sequence[Path], *, copy_only: bool = True,
                     expected_generation: str) -> tuple[str, ...]: ...
    def import_native_clipboard(self, payload: object, *, expected_generation: str): ...
    def place_asset(self, module_id: str, asset_id: str, mixed_index: int,
                    *, expected_revision: int) -> str: ...  # new PhotoBlock ID
    def thumbnail(self, asset_id: str, visual: PhotoVisual, max_edge: int): ...
    def update_placement_visual(self, block_id: str, visual: PhotoVisual): ...
```

Use `media_import.convert_picture/stage_pictures/commit_staged_pictures`, `photo_gallery.local_picture_paths/clipboard_image_png`, `photo_editor.render_photo` and validated model visuals. No direct website image transport or MIME HTML parser. Reject remote URLs, symlink/junction bypass, Move-only drag, stale queued sessions and oversized/unsupported images; file drop must be **CopyAction**. Source originals are never modified. Existing bounds include 64 MiB local source, 60 MP decode, 16 MP native clipboard, 64 image batch, 32 MiB project asset, 256 MiB combined assets and 2,048 archive entries; revalidate at integration.

Media imports and report placement must not create orphan asset links or lose undo/redo. M1 does **not** need image placement; the separate image/gallery work is M4 after the transaction boundary is in place.

## 7. Editor, Preview and Export facades

```python
class DocumentEditorTab:
    def select(self, address: NodeAddress, current_revision: int) -> None: ...
    def commit_pending(self) -> ChangeSet | None: ...

class PreviewExportFacade:
    def preview(self, revision: int, export_profile: object) -> object: ...
    def export(self, format: Literal["docx", "pdf"], path: Path,
               revision: int, export_profile: object) -> Path: ...
```

The Editor tab uses the same node addresses, draft coordinator and command gateway. `page_editor.EditableDocumentPage` may be adapted after conflict arbitration is centralized; avoid full `rebuild` while page fields are pending. `export.prepare_export` / `export.export_project` operate only on a validated committed `ReportProject`, use `engine.module_outline` and approved export profile; never scrape branch widget HTML or persist page-number guesses. Preview indicates schematic vs export-faithful pagination, never promises pixel-identical Word.

Current `export.prepare_export` **fails on any non-default PhotoVisual**. Retain explicit error until annotated output is implemented and compared in both DOCX and PDF (M6). Never silently export untouched image when a user added annotations.

## 8. PresentationStore and browser

```python
class PresentationStore:
    def load(self, project_identity: str) -> object: ...
    def save(self, project_identity: str, state: object) -> None: ...
```

Persist under a versioned Qt `QSettings` namespace, keyed by stable report ID plus normalized local project identity (or session-scoped unsaved ID). Prune stale module IDs when loading; store expansion sets, zoom, pan, focus, selection and temporary display dimensions; never store report text, customer data, original photo paths, private media, passwords or cookies in this store. **First Save / Save As identity rule:** only after a successful archive write, copy or rekey the active presentation state to the new project identity and retain the old identity's saved state if the old file still exists. On cancelled/failed Save As, neither active identity nor settings may change. Reopening the new path must restore expansion state by stable module ID, while opening a different report starts from that report's own settings/defaults. Keep it local: another PC may open the same v4 report with default canvas settings. Print layout changes require a separate canonical/export contract and ADR if persistence is needed.

Browser tab contract is **unchanged V1 UX**: ordinary `QWebEngineView`, user-controlled login, local `QWebEngineProfile`, native website controls and default-browser fallback. No access to `ReportSession`/metadata, no OpenAI SDK/API, scripting/DOM, cookies export, prompts or automatic insertion. User-initiated copied **text** goes into normal plain-text editor clipboard; native/browser **images** must be separately imported through `MediaAdapter`, only on user action.

## 9. Contract tests and change-control

Every M1 adapter API gets a synthetic test for success, invalid intent, stale revision/generation, undo/redo, saved/reopened data and intact draft on failure. Import-smoke must reject `reportmaker.visual_editor` in V2 import graph; dependency tests can check `sys.modules` as a supplement (not the sole static guard). Use exact typed field semantics and no Qt in pure model/commands/storage. Assert that V2 import transitively loads **neither** `reportmaker.ui` **nor** `reportmaker.visual_editor`; check both via static imports and an isolated-process runtime import smoke test. Add a first-Save/Save-As settings-identity regression and a test proving view-side changes to a read snapshot cannot mutate the canonical report. Changes to these contracts require an updated M0 document or reviewed ADR; contract evolution must not silently alter the 33 approved features.
