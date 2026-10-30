# Issue #116 / Phase 1 — V2-only frozen packaging boundary

**Status:** implementation isolated for independent review. **Do not merge into M7.3 until the exact-head Windows freeze/install/uninstall matrix passes.** No V1 source, installed application or customer data is removed. No installer is automatically uploaded.

## Source and branch

- Implement independently on `retirement/phase-1-v2-only-frozen-package`, stacked on the current secured M7.3 development branch, which remains open as draft PR #97.
- Claude's PRs #112–#115 and `main` are not modified.
- The retirement phase is *not* a product migration, a V2 default-launcher switch, or an authorization to delete V1.

## What changed

1. **Narrowed frozen dependencies.** Removed the blanket `--collect-submodules reportmaker` command from both the hosted Windows V2 packaging workflow and the opt-in local PowerShell builder. PyInstaller follows V2 launcher imports and explicitly keeps the Qt WebEngine modules and `pillow_heif` assets. Eleven legacy-only modules are explicitly `--exclude-module`d (old main entry point; V1 main window/report editor, page/rich/template dialogs, old customer shim and four V1 probes).
2. **Checked the actual EXE.** `scripts/verify_v2_frozen_archive.py` runs the pinned PyInstaller archive viewer recursively on the **frozen V2 executable**, rejecting all prohibited V1 modules and any missing critical V2 or shared modules. Also checks loose bundled application files, failing closed on invalid binaries, empty inventory, viewer errors, or missing requirements. This runs before an installer can be created in both Windows builders.
3. **Source and runtime import barriers.** `tests/test_v2_retirement_boundary.py` walks the AST of all V2 and the eleven essential shared-service Python modules, rejecting direct V1-only imports; an isolated offline V2 startup prevents importing V1-only modules through a guarded `__import__`. Unit tests exercise positive/negative archive inventories and frozen-builder consistency.
4. **Preserved existing release boundaries.** M7.3 Windows CI builds only in a Windows runner and continues to require freeze, installed complete-payload SHA-256 parity, offline smoke and uninstallation. Ordinary PR validation never attaches binaries. The existing **explicitly opted-in** `workflow_dispatch` one-day unsigned QA artifact remains intact; no opt-in is issued by this PR.

## Protected shared modules (must remain)

`engine`, `export`, `media_import`, `model`, `photo_editor`, `photo_gallery`, `project_io`, `reference`, `rich_text`, `storage`, `template_import`.

In particular, V2 subclasses the shared `PictureEditorDialog`, retains all ten annotation tools, uses gallery drag/drop/clipboard safeguards and reads the existing customer database. No media format, schema, user-data location, template import, export, browser/login or undo/draft behavior is changed here.

## Required independent gates

- [ ] Fresh exact-head Linux suite, V2 offline smoke, static/runtime import fence and unit tests green.
- [ ] GitHub Windows PyInstaller freeze completes **without** blanket collection.
- [ ] Recursive frozen EXE inventory confirms **zero** legacy-only modules and **all** required shared/V2 modules, with no loose V1 source files.
- [ ] Exact-head Windows installed complete-payload verification, offline smoke and uninstall green.
- [ ] Independent architecture/security/data-integrity review of the corrected PR.
- [ ] After Claude's concurrent work is assessed, reconcile branch ancestry, rerun the gates, and separately decide whether to integrate.
- [ ] Physical installed Windows 33-case M7.3 acceptance remains a later gate and is not supplied by this PR.

## Explicit non-goals

Do not delete the V1 launcher, V1-only Python files, V1 installers, V1 CI workflows, old saved reports, user data, backups or old releases. Do not change `python -m reportmaker`, V1's installation AppId, V2's distinct preview AppId, or the `CustomerStore` database path. The outstanding visual Word-template editor capability-gap decision remains separate from this packaging-only phase.

## Review note

The frozen-module analysis uses the official PyInstaller recursive archive viewer. Source-level tests cannot substitute for the Windows executable check; **only Windows CI will establish the frozen boundary**.
