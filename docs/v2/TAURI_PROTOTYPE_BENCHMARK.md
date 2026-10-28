# Experimental benchmark — Tauri/React vs existing PySide6 Branch Editor

**Date:** 2026-10-28. **Status:** experimental prototype, no framework migration approved.
**Baseline:** main `8229321276a7207c5faa455942b38d3a23404b8a`, following merged PR #72. The only changed application is under `benchmarks/tauri-spike`; approved V2 and V1 source remain untouched.

## Method

- Available machine: Linux x86_64, Python 3.14.4, PySide6 6.12.0, Node 22.22.1, React 19, Vite 7, Playwright Chrome Headless 156. Measurements were taken on the same machine in the same session, but the Qt and browser workloads are *not feature-identical*.
- Synthetic structured ReportMaker project, 82/302/802 visible rows from `Report` / `project_branch`, containing ordered paragraph, photo, table, heading and nested-module rows; dedicated Conclusions last.
- Qt measurement uses the **real** V2 M2.2 `V2MainWindow` and `BranchCanvas`, including actual user Apply draft and Move Down through the command gateway. Two runs per size, median, offscreen platform, includes queued Qt events and full widget rebuilding. 802 experiment was halted due to a resource ceiling rather than reporting a misleading completion time.
- React measurement uses a simpler JSX card/input/drop-preview UI in headless Chromium via Playwright. Three runs per size, median; mount includes fetching synthetic JSON and two requestAnimationFrames; refresh clones row DTOs to force list rendering, edits remain browser-local, and the move benchmark rearranges display-only data. React benchmark is not an exported-report or bridge-integrated edit benchmark.
- A **separate** persistent JSONL Python subprocess bridge test exercises the unchanged core `rename_module`, `move_node` and Undo gateway (82-node project), including stale revision rejection and canonical order validation. Thirty rename commands, one unformatted paragraph edit and fifty read operations, plus malformed-message recovery. This proves a transport shape, not native Tauri IPC.
- Browser JS heap and Qt process resident memory measure different things and are deliberately not compared directly.

## Measured results

| Operation | Qt 82 rows | React 82 rows | Qt 302 rows | React 302 rows | React 802 rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial mount / paint, ms | 433.25 | 55.30 | 2739.83 | 52.90 | 105.30 |
| Warm full refresh, ms | 287.04 | 30.20 | 1703.30 | 65.30 | 103.30 |
| Edit + apply, ms | 579.12 | 31.50* | 3834.12 | 29.60* | 31.50* |
| Move, ms | 566.20 | 29.40* | 3744.82 | 30.50* | 31.30* |

`*` React edits/moves are **prototype-local rendering events**, not full command/draft/undo/save transactions; do not interpret these as end-to-end speedups.

- **Qt 802 rows**: incomplete. Process deliberately stopped after >150 seconds of sustained full CPU with ~2 GiB RSS. It is an unvirtualized-widget scalability warning, not a precise per-operation number.
- **Pure canonical projection** (Python `project_branch` median, 10 runs): 82 rows 0.115 ms; 302 rows 0.410 ms; 802 rows 1.064 ms. This suggests the dominant Qt issue is widget creation/rebuilding rather than generating the canonical hierarchy.
- **JSONL bridge (82 rows)**: median read round trip 3.961 ms (p95 4.665); rename command 6.992 ms (p95 8.121); move 9.208 ms; Undo 1.774 ms. Stale writes rejected and canonical undo verified.
- Chrome JS heap after sampling: 8.88 / 11.63 / 13.92 MiB at 82/302/802 nodes. **Not** equivalent to total WebView2/Tauri process memory.

## Decision

**Worth advancing to a Windows Tauri shell proof, but do not migrate V2 yet.** React's layout performance looks promising, while the current Qt full-widget rebuild appears to be a bottleneck. However, comparing the Qt full editor to React's simpler projection is not feature parity. A Qt virtualization/partial-update prototype could also close much of this gap, and neither native shell startup/packaging overhead nor WebView2-specific behavior has been measured yet.

**Mandatory remaining gates:**
1. Successfully compile and actually run a packaged Tauri + Python sidecar on Windows x64; test roundtrip correctness and app lifetime (child crashes, save, reconnect, no session leak).
2. End-to-end native UI parity: editable title/paragraph/rich text with safe drafts, Undo/Redo, subtree drag, real mouse and focus behavior, 100/125/150% DPI, large tree virtualization, keyboard access.
3. Windows Explorer image drops and project-owned asset preservation, clipboard import and native WebView2 HTML5 drag constraints.
4. Existing user-controlled ChatGPT browser/manual copy-paste and image copy/download, with no API, scripts, scraping or automated insertion.
5. Fair matching-feature benchmarks on installed Windows; include total process RSS and save/reopen correctness. Record performance and failure thresholds before ADR approval.

The Tauri shell scaffold exists and the React production build succeeds; a local native Tauri build was attempted and blocked by missing `cargo` / WebKitGTK requirements. Do not claim the Tauri runtime, WebView2, or native ChatGPT path is validated. No changes to main, V1, project schema, installer or release.

**Recommendation:** keep the existing Qt Branch Editor authoritative; use this experiment as evidence for a subsequent decision ADR after native Windows and matched-feature validation.
