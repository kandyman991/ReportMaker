# M2 — Project and module engine (review boundary)

Source of truth: `ARCHITECTURE.md`, `docs/REPORT_COMPOSITION_CONTRACT.md`, and ADR-0006.
The M2 branch adds a **pure-model** editor and an **editable local project format**.
This is not the M3 visual report editor, and not a DOCX/PDF export or an M1 installer.

## Canonical hierarchy and metadata
- `Report` stores creation date, localized title, intervention dates, ticket,
  technician list, a **multi-selection** of intervention categories and explicit
  Other detail. Languages are free-form validated tags; no fixed UI/export locale enum.
- A persisted report contains a **detached** `CustomerSnapshot`, either captured
  by M1 from the database or manually entered. Only `customer_id` may link to a
  master record. An existing customer must not be looked up again on project load.
- Intervention modules have stable IDs and ordered heterogeneous blocks:
  paragraph, heading, photo, table, manual page break and nested module.
- `conclusion` is a separate required module, always the last logical section;
  deletion/reordering is prohibited. `module_outline()` is the only derivation
  used for hierarchical numbering, navigation and the later table of contents.
  No independent editable summary data is serialized.
- `ProjectEditor` applies staged, validated mutations. A failed edit leaves the
  previous model and history untouched. Successful edits support bounded undo/redo,
  including parent moves that retain nested content and language variants.
  Duplicate modules receive new IDs but share immutable logical photo assets.

## Portable project package
- File extension: `.rmproj` (conventional, not a security boundary).
- Internal ZIP entries: exactly `manifest.json` and
  `assets/<logical-asset-id>` for each included photo byte stream.
- `manifest.json`: `format = "reportmaker.project"`, `version = 1`,
  canonical `report` metadata/tree, photo asset ID/length/SHA-256 records.
  Unknown schema versions are rejected, not silently rewritten or downgraded.
  The package intentionally contains no independent TOC/summary, customer SQLite
  master tables, browser profile, cookies, ChatGPT data, credentials or remote URLs.
- Serialized localized content retains original/source language, translations
  and stale-language markers. Modules own their captions and photo IDs.
- Saving uses a temporary file in the destination directory, flush/fsync, then
  atomic replace. Failed validation leaves previous project bytes unchanged.
  Import/restore is read-only, with no extraction of archive entry paths.
- Project load verifies the allowlisted archive entries, file-size bounds,
  recorded SHA-256, logical asset IDs, schema shapes, unique hierarchy IDs and
  no cycles. Corruption/unrecognized versions yield a clear error.
- Default project directory is under the per-user application data path,
  independent of Chromium/Qt WebEngine profile paths. There is no cloud sync.
- M2 does not yet provide a graphical Open/Save dialog or drag/drop editor:
  those are integrated and acceptance-tested in M3.

## Media lifetime and no-hidden-photo contract (PR9-F01)
- The report's currently reachable `PhotoBlock.asset_id` values are the only
  assets eligible for serialization. Unreferenced/orphan assets are omitted from
  the saved ZIP/manifest and will not reappear when the project is reopened.
- The in-memory `ReportProject.assets` map can temporarily contain bytes from
  deleted blocks, so Undo can restore the picture. Saving does **not** mutate
  that in-memory undo cache; reuse/duplication of a photo ID in surviving modules
  preserves exactly one shared asset entry.
- Old M2 v1 ZIP files that already contain orphan entries remain readable if
  their complete manifests and digests validate. Import drops orphan bytes from
  the active project; the next save produces a scrubbed archive.
- Deleted content is removed from a newly saved project, not securely erased
  from old copies, filesystem snapshots or backups. Users must manage those
  copies independently.

## Import safety, validation and version compatibility (PR9-F02/F03)
- All metadata and each localized original/translation/stale marker are
  validated *without mutating the report* at editing and save boundaries.
  Invalid edits cannot silently repair a missing title or enter undo history.
  An accepted valid mutation round-trips through the same storage constraints.
- ZIP version 1 permits `ZIP_STORED` and `ZIP_DEFLATED` only. Encryption,
  unsupported compression, corrupt streams and invalid schema/provenance yield
  a controlled ValueError; no archived path is ever extracted.
- Format compatibility matrix:
  
  | Input | Behavior |
  |---|---|
  | M2 `.rmproj` v1, valid | Load, edit, save (v1) |
  | M2 v1 with legacy extra/unreferenced assets | Load safely and prune orphans in memory and next save |
  | Missing/malformed manifest, unsupported ZIP method or damaged data | Reject, leaving source unchanged |
  | Future schema version (v2+) | Reject without migration/downgrade; retain original bytes |
  | M0/M1 report model and SQLite customer DB | Continue to work; M2 never alters DB schema |
  
  Any future migration requires an explicit ADR, fixture corpus and
  revision-specific regression gates before enabling it.

## Backup, crash recovery and known limitations
- Atomic same-directory replace and fsync guard against incomplete destination
  writes; this is **not** an automatic project backup or a historical revision
  history. An existing valid destination is preserved when validation fails.
- M2 deliberately does **not** create `.bak` or versioned files by default;
  doing so could retain deleted photos in a hidden earlier revision and violate
  user expectations. Users can explicitly make a private filesystem copy of
  a successfully saved project before editing. Synthetic tests verify loading
  such a copy after a corrupted current file.
- The M3 graphical editor must offer clear opt-in backup/recovery controls and
  disclose where old photos remain. A crash/power-loss/hardware test on an
  installed Windows machine is still outstanding; CI tests cannot prove it.
- No production customer reports or photos are used in CI or public assets.

## Minimal Python usage
```python
from reportmaker.project_io import ReportProject, save_project, load_project
from reportmaker.engine import ProjectEditor, module_outline

# report: an already-created, valid Report with a detached customer snapshot
project = ReportProject(report=report, assets={"photo-1": image_bytes})
save_project(project, "demo.rmproj")
reopened = load_project("demo.rmproj")
editor = ProjectEditor(reopened.report)
print(module_outline(editor.report))
```

Only synthetic/fake images and fabricated customers may enter public tests.

## M2 exit gates
- [x] Pure hierarchical model, editing commands, metadata and block types implemented.
- [x] Local atomic bundled project save/load; portable photos and hash checks implemented.
- [x] Undo/redo, duplicate IDs, conclusion-last, derived outline and corruption regressions added.
- [ ] Verify exact-head Windows hosted CI (all M0/M1 + M2 tests).
- [ ] Independent code review (archive input hardening, validation, migrations and history).
- [ ] Native installed Windows end-to-end report editing acceptance (scheduled with M3).
- [ ] Reviewed user-visible file open/save UI (M3).
- [ ] Windows M2 installer explicitly approved and tested (not implied by CI).

## Rollback and safety
This feature branch is not merged to main. It does not install, send, scan
local report directories or migrate existing SQLite data. Abandoning the branch
leaves M1 main and its installer/release policy unchanged. Do not merge or
publish an installer without user authorization.
