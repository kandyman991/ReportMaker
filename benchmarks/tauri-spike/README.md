# ReportMaker V2 — isolated Tauri/React vs Qt prototype

**Experimental only, not an approved frontend migration.** Based on `main 8229321276a7207c5faa455942b38d3a23404b8a` after PR #72. Synthetic reports; no customer data, ChatGPT sessions, browser automation, or production assets.

## What is implemented

- Real React 19 Branch Editor rendering canonical V2 project projections (root, ordered modules, nested modules, paragraphs, photos, headings, tables, final Conclusions); HTML input/text area editing; HTML5 drag zone preview. In **browser** mode edits are prototype-only (not canonical) and drops do not mutate structure.
- A Tauri 2 desktop shell scaffold configured with Windows `dragDropEnabled:false` for HTML5 drag/drop; dedicated least-scope synthetic Python sidecar permissions.
- **When launched as a packaged Tauri shell**, `web/native-bridge.js` sends JSONL through a single native sidecar process, receives detached canonical projections, and applies only `rename_module`, plain `set_paragraph` and `move_node` through `ReportSession` + `CommandGateway`, with revision/generation guards and native command rejection. This integration is *not yet execution-validated in a native Tauri shell*.
- Repeatable Chromium Playwright measurements, local subprocess command bridge measurements, and offscreen PySide6 M2.2 measurements, using the same size-graded synthetic hierarchy.

## Reproduce Linux/browser tests

From repo root, install Python dependencies: `python -m pip install -e ".[desktop]"`.
From `benchmarks/tauri-spike`, run:

```sh
npm ci
npm run fixtures
npm run build
npm run dev
# In a separate terminal while dev server runs:
npm run bench
BENCH_PYTHON=python npm run bridge
# Native Qt comparison (repo root is two directories above):
PYTHONPATH=../../src QT_QPA_PLATFORM=offscreen python bench-qt.py 2
```

First `npx playwright install chromium` may be required. The browser test measures DOM rendering on Linux Chrome Headless, **not** native Tauri WebView2 performance. Qt comparison measures actual V2 widgets and canonical UI transactions, whereas browser edits/drops intentionally do not yet reproduce the full Python commit + post-command redraw. Time includes browser two animation frames; this is a directional comparison, not a like-for-like UI transaction benchmark. Measured memory is Qt RSS versus Chrome **JS heap only** and must not be compared directly.

The 802-row Qt benchmark is opt-in via `BENCH_MAX_ROWS=802` because the first run was cancelled after exceeding the experiment's resource budget (>150s, ~2 GiB process RSS). The default cap is 302 nodes.

## Windows Tauri build gate

The Tauri wrapper requires Rust/MSVC, WebView2, a correctly named PyInstaller sidecar, and a Windows build. The CI-only `v2-tauri-prototype.yml` builds the native Windows executable without publishing artifacts or changing releases. This Linux workstation has no `cargo` or WebKitGTK 4.1 development dependencies; `npx tauri build --no-bundle` fails at `cargo metadata`. **No installed-Windows runtime acceptance has been claimed.**

Before any migration decision, verify packaged sidecar launch and stdout framing, multi-language and rich-text fidelity, draft conflict/selection/undo behavior, Windows DPI, real mouse drag/drop, external Explorer image handling, ChatGPT manual browser login/copy/paste/download, large reports and project save/reopen. The embedded ChatGPT browser is **not implemented** by this prototype.

## Safety/architecture

No webview gets direct report-file access; the Python report remains authoritative. Renderer data are detached projections and native-side commands are revision-checked. Native `shell:allow-spawn` is scoped to the synthetic sidecar. No V1 rewrite, production backend changes, new AI API, user data export, installer, migration, or merge to main.

See `docs/v2/TAURI_PROTOTYPE_BENCHMARK.md` for measured results and decision.
