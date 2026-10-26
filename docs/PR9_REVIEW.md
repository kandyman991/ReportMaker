# PR #9 independent review and isolated correction PR #10

Date: 2026-10-26. Repository: `kandyman991/ReportMaker` (PUBLIC).
Original review: https://github.com/kandyman991/ReportMaker/pull/9#pullrequestreview-5656832565
Reviewed original head: `3daebbf53c81558664a9d6dac41e760425a19108`
Original base on main: `f9e8abdc94411cc52657eded1c37a0217f428053`.
The review was COMMENTED (not approved). PR #9 remains open/unmerged.

Correction branch: `review/pr9-m2-safety-corrections`.
Stacked PR: https://github.com/kandyman991/ReportMaker/pull/10
Base: PR #9's `feature/m2-project-module-engine` (NOT main). No merge authorized.

## Findings and narrowly scoped corrections

### PR9-F01 — High — invisible orphan media in saved reports
- Original reproduction: an unused `ReportProject.assets["unreferenced"]` value
  was bundled despite no surviving `PhotoBlock` referring to it.
- Correction: `_assets_checked` serializes only photo IDs reachable through
  the report's current ordered hierarchy. Unreferenced image bytes stay in
  memory to permit Undo but are omitted from newly saved portable projects.
  Surviving/duplicated blocks sharing an asset ID preserve a single asset.
- A legacy v1 project already containing extra media remains readable when
  its whole archive verifies. Import drops unreferenced media from the live
  project and a subsequent save scrubs it from the archive.
- Test coverage: delete single photo, delete containing parent, keep shared
  duplicate alive, undo/redo and reread, direct orphan injection, legacy v1
  orphan import and resave. No true customer images ever used.
- Boundary: this does not erase bytes in earlier backups, previous files,
  filesystem snapshots or storage-device recoverable blocks. Avoid hidden
  automatic .bak files that could silently preserve deleted images.

### PR9-F02 — High — accepted but non-roundtrippable editor edits
- Original examples: ticket integer, null module title, malformed localized
  original/translation/stale markers; `Report.__post_init__` could quietly
  synthesize a title during repeated validation.
- Correction: `validate_report_metadata` and `validate_localized_text`
  perform explicit read-only checks on every scalar/collection and nested
  localized element, with report/module/block IDs, date types, references,
  headings and safe logical photo IDs validated at the same boundary.
- The constructor continues supplying an M0/M1 default title **on initial
  construction only**. Every subsequent editor mutation validates without
  mutating the candidate. On failure, undo/redo stacks and prior saved bytes
  remain unchanged.
- Test coverage: multiple injected invalid ticket/date/translated/table/photo
  mutations; non-regenerated null title; valid edit roundtrip equality; failed
  save preserving previously valid package.

### PR9-F03 — Medium — unhandled ZIP compression/decompression errors
- Original reproduction: an archive with unsupported compression allowed
  `NotImplementedError` to escape `zipfile`, outside the project's expected
  input-failure ValueError contract.
- Correction: allowlist ZIP_STORED/ZIP_DEFLATED, reject ZIP encryption and
  unsupported methods before reads; normalize decompression/ZIP parse errors
  without extracting any entries to the filesystem.
- Test coverage: standard-library BZIP2 ZIP rejection; manually altered ZIP
  central/local unsupported-method fields; corrupted archive with manual
  local-backup copy recovery.

## Evidence
- The first F03 fixture used a double-escaped binary signature and failed one
  CI run (#40377228870). The **test fixture** was corrected without relaxing
  import validation, and the Windows tests re-ran successfully.
- Verified Windows M0/core workflow:
  https://github.com/kandyman991/ReportMaker/actions/runs/40377387550
  SUCCESS at `fbb2bf056333a512db601e7bdbc864ac1de11af7`.
  Unit suite: **48 tests PASSED**, PySide6 import, Qt pane smoke and compile
  checks passed.
- No production or user-specific data, secrets, browser sessions, login
  automation, AI API, installer publication, deployment or Windows machine
  modification. User's installed-PC acceptance is NOT yet verified.
- After adding documentation commits, validate workflow result on the **exact
  latest correction PR head**; older successful runs are not evidence for
  a different changed implementation.

## Compatibility and recovery
See `docs/M2_PROJECT_ENGINE.md` for v1 compatibility matrix, legacy-orphan
scrubbing and explicit opt-in backup policy. No v2 migration is implemented.
Atomic replace guards against partial writes but does not provide automatic
history or power-loss assurance. Recovery from a previously saved private
copy is tested; installed-PC crash/reopen and interactive Windows editor
Save/Open remain outstanding.

## Next action / restrictions
1. Independently re-review **only** these fixes and surrounding safety
   boundaries, using exact head+CI of PR #10 (avoid unnecessary full-cycle
   review of unchanged M0/M1).
2. If review passes, seek explicit user authorization to integrate PR #10
   into PR #9's feature branch; then verify PR #9's combined exact-head CI.
3. Seek separate authorization before PR #9 -> main merge, release, deploy
   or native installer use. No merges authorized in this review/correction.
