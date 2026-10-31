# Phase 1 — repository and regression baseline

**Captured:** 2026-10-31. **Code SHA:** `8b52776984f6190fa2a0f657af9376f4f1cc5d5f`. **Scope:** read-only existing code; synthetic test assets only.

## Repository inventory (GitHub recursive tree, non-truncated)

| Category | Count/observation |
| --- | --- |
| Tree entries | 269, including 16 directories and **253 files** |
| Python `.py` files | 136 |
| Test modules | 63 `tests/test_*.py` (plus `tests/_web_studio_cases.py` helper) |
| GitHub Actions workflows | 17 |
| `docs/` files | 80 |
| Remote branches | 81 on 2026-10-31 |
| Open PRs | #120 and historical draft #21 |
| HTML Studio | #121 **merged**, remains opt-in (`--html`) |
| Project file format | `reportmaker.project`, `project_io.VERSION = 5` at this SHA |
| Python | `>=3.11,<3.16`; `pyproject.toml` reports `0.0.1` (stale product metadata; no version edit here) |
| Runtime dependencies | `python-docx>=1.2,<2`, `reportlab>=4.2,<5`, `Pillow>=13,<14`, `pypdf>=5,<7`; optional desktop `PySide6==6.12.0`, `pillow-heif>=1.8.1,<2` |
| Build dependency | `pyinstaller==6.22.3` in `packaging/windows/requirements-build.txt` |

Tree-size hotspots: `src/reportmaker/v2/branch/canvas.py` about 144 KB, `src/reportmaker/visual_editor.py` about 104 KB, `docs/CHECKPOINTS.md` about 115 KB, `CHAT_HANDOFF.md` about 98 KB, `v2/app.py` about 49 KB, HTML `studio.js` about 45 KB. Size alone is not a reason to delete code.

**Observed separation:** V1 entry `python -m reportmaker` uses old `ui.MainWindow`; native V2 entry `python -m reportmaker.v2` uses `V2MainWindow`; HTML entry `python -m reportmaker.v2 --html` uses `V2WebMainWindow` with a hidden native V2 window. Shared backends must remain. `tests/test_v2_retirement_boundary.py` and `scripts/verify_v2_frozen_archive.py` already enforce no legacy-only V1 module leakage in V2 freeze; keep those tests.

## Build, CI and release blockers

- #105: Windows transitive dependency lock hashes, GitHub Action SHA pins, Qt Chromium security-update cadence and build provenance not completed.
- #106: no supported Linux **application test** CI matrix, despite Linux continuity helper jobs. Add without removing Windows acceptance gates.
- #116: V1 retirement requires visual template editor parity decision, native installer co-existence/migration/rollback, user-data protection; **no deletion permitted by Phase 1**.
- #96: the 33-case *physical installed-Windows* matrix is not complete; physical #98/#99 retests pending.
- PR #120 branches from pre-HTML main and is diverged; review after HTML merge, do not silently merge or discard. Historical draft PR #21 must be evaluated before closure.
- HTML `--html` is opt-in; default promotion and release are distinct decisions. No physical installed-Windows acceptance is inferred from Qt offscreen/hosted Windows smoke.

## Reproducible Linux source verification

**Legion device:** `mircea-gitmachine`. Isolated read-only source worktree: `/home/mircea/ReportMaker-work/cleanup-phase1-baseline-20261031`; existing tested venv from `pr121-final-independent-20261030/.venv/bin/python`, Python 3.14.4, PySide6 6.12.0, Pillow 13.0.0. The worktree was explicitly set to the exact SHA above; the remote's `origin/main` tracking ref was older and **not** used as the final baseline.

Test commands from worktree root (run with private synthetic fixtures only):
```sh
export PYTHONPATH="$PWD/src" QT_QPA_PLATFORM=offscreen
export QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu"
PY=/home/mircea/ReportMaker-work/pr121-final-independent-20261030/.venv/bin/python
"$PY" -m compileall -q src
"$PY" -m reportmaker.v2 --offline-self-test
"$PY" -m reportmaker.v2 --html --offline-self-test
"$PY" -m unittest discover -s tests -v
```
The **full suite result must be recorded from the final run**, not copied from earlier PR audit history. Qt can emit Vulkan/GLX diagnostic warnings on a headless offscreen Linux device even when the smoke exits 0. An initial trial using `QTWEBENGINE_DISABLE_SANDBOX=1` without `--disable-gpu` crashed Chromium with exit 133; the Chromium smoke should use the same `--disable-gpu` configuration as `tests/test_v2_web.py`. This is an environment-specific observation, not a Windows product failure.

## Golden fixture and data-integrity contract

Use synthetic examples already in `tests/test_m2_project.py:example`, `tests/test_m4_export.py:synthetic_project`, `tests/test_v2_m6_bundle.py`, `tests/test_v2_web_commands.py` and the versioned migration cases in `tests/test_v2_m7_migration.py`. Preserve/create golden *assertions*, not platform-dependent DOCX/PDF byte-for-byte hashes:
- **`.rmproj`:** project format/schema version, safe ZIP members, atomic existing-file protection, old read/Save-As policy, stable module IDs, nested ordering, translations/stale sets, customer snapshots, multi-type intervention metadata, retained photo library assets and non-destructive annotations.
- **DOCX/PDF:** editable text, bookmarks/TOC and derived numbering, heading/table/image ordering, conclusions last, header/footer/template styles, page proof text and file replacement protections.
- **Media:** synthetic in-memory PNG/JPEG/HEIC where supported, checked pixel bounds and safe metadata, unchanged external originals, asset deduplication and private review comments omitted from exported customer output.
- **Windows-specific:** do not normalize away printer pagination, actual DPI, Explorer/clipboard behavior, installed payload hashes or uninstall/rollback; record these separately with physical evidence.
- **Security:** no production customer data, proprietary CAD, real photographs, access credentials, browser profiles or logged-in screenshots in the repository or test artifacts.

## Evidence ledger

| Gate | Status | Evidence / qualification |
| --- | --- | --- |
| Git tree and direct dependencies | **Done** | GitHub recursive tree, `pyproject.toml`, scripts/workflows inspected at baseline SHA |
| Capability ownership/parity register | **Initial source inventory done** | `docs/cleanup/FEATURE_PARITY.md`; physical functionality still unverified |
| Native V2 offline source smoke | **Passed** | On Legion Python 3.14.4 offscreen at baseline SHA |
| HTML Chromium/QWebChannel source smoke | **Passed** | On Legion with `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu`; exited 0 |
| Python compileall | **Passed** | On Legion at baseline SHA |
| Full Python regression suite | **In progress / exact result to be appended** | Test output in temporary Legion log, not committed |
| Synthetic `.rmproj` / export protection | **Existing coverage identified** | M2, M4, M6, web commands and migration tests; fresh full-suite results to follow |
| Native desktop visual acceptance on Legion | **Not run here** | Offscreen is not real rendered interactive GUI acceptance |
| Hosted Windows exact-PR-head CI | **Not run yet** | Will execute on proposed PR where configured |
| Physical Windows 33-case acceptance | **Not run** | Separate #96 gate; cannot be claimed by Phase 1 |

## Next Phase 1 actions

Complete and record full-suite outcome, run/add a focused synthetic golden contract regression, review fixture coverage gaps and file follow-ups; independently review exact PR head and check hosted CI. The baseline documentation is *not* acceptance of V1 retirement, default HTML promotion, or Windows release.
