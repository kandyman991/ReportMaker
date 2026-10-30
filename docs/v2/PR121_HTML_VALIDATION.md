# PR #121 HTML studio correction ledger

Date: 2026-10-30. Original reviewed head: `6b4698c94492e85359e84c932390a0d0c895b7ea`.
Verified base/main: `bfd5720e914b6b75f57b4a4260991bbe896abe13`.
Review source: https://github.com/kandyman991/ReportMaker/pull/121#pullrequestreview-5714520434.

The correction preserves Gemini's design and original commit. The HTML layer is a
presentation client of the existing CommandGateway/ReportSession. It does not add
a project serializer, model, translation engine, image editor or exporter.

## Launch and rollback

`python -m reportmaker.v2 --html` opts into the HTML candidate.
`python -m reportmaker.v2 --native` explicitly selects the existing native V2 UI;
native remains the default pending installed acceptance. The frozen executable
accepts the same flags. `python -m reportmaker` remains V1.

`--html --offline-self-test` exercises actual Chromium, QWebChannel, canonical
commands, focused drafts and Undo/Redo. `--offline-self-test` retains native smoke.
The editor is offline. The isolated Assistant offers a separate, user-initiated
website; it has no report bridge. No project file is changed by switching UI.

## Findings and regression coverage

| Finding | Correction | Evidence |
| --- | --- | --- |
| F01 | Optional validated heading level in the atomic rich command, including field batches | Level-only revision; invalid levels; text+level one-step Undo/Redo |
| F02 | Detached copies preserve localized cells; source edits call `update_original`; shape operations reuse `change_grid` | Row/column add/delete, stale markers, Undo/Redo, save/reopen, Italian DOCX/PDF and stale-export rejection |
| F03 | Existing `rebase_rich` preserves unchanged character ranges and refuses ambiguous styled boundaries | Bold, Unicode offsets, translations, explicit failure without mutation |
| F04 | Input events stage field drafts; one atomic backend batch precedes queued actions, shortcuts, PDF proof and close; Apply/Discard/Cancel; failures retain input | Focused Ctrl+S/caret, validation recovery, Discard, Undo/Redo, New/Open, close Cancel, delayed action with real key input |
| F05 | Both builders include QtWebChannel and packaged assets; archive requires web modules, Qt extensions and assets; frozen/installed smoke selects HTML | Actual freeze, inventory, installer and hosted CI results must be recorded against the final head |
| F06 | Private off-record `rmstudio://app` origin, allowlisted resources, blocked navigation/downloads/network/frames, CSP without inline scripts/eval, one versioned dispatch slot | Hostile text and IDs, inline-script CSP, rejected navigation/fetch, hidden internal slots, stale and unknown actions |
| F07 | Native fallback retained; dedicated pure and real Chromium tests | `test_v2_web_commands.py`, `test_v2_web.py` invoking `_web_studio_cases.py` |
| F08 | Revision projection cache, changed-card payloads, DOM reconciliation, lazy photo URLs, immutable-byte digest cache and 32 MiB thumbnail LRU | 100 modules/photos, unchanged card identity, bounded cache, no image rehash on wording changes |

Additional independent-review corrections: manual snapshots retain non-visible
contact/address fields; H4–H6 remain selectable; live input values reconcile on
Discard/Undo; native recovery permits closing an unavailable renderer; controls
remain read-only across draft flush and asynchronous actions; page/profile
ownership and explicit deferred-delete processing cover Chromium shutdown.

## Review and local evidence

Read-only independent subagent review followed `docs/AUDIT_PLAYBOOK.md`. Six
concrete findings above were corrected. Independent real Chromium reproduction
verified Discard and the delayed-action race with `QTest.keyClicks`. No additional
concrete blocker was found in that bounded evolving-tree review. A final exact-SHA
review and fresh CI remain required; this is not release approval.

Environment: physical Windows 10 build 19045, AMD64, Python 3.12.14,
PySide6 6.12.0 / WebEngine 6.12.0.140, Pillow 13.0.0, pillow-heif 1.8.1,
PyInstaller 6.22.3. Local synthetic logs are under ignored `.local/`.

- Pure HTML command regressions: 11 passed, including multilingual output.
- Real renderer suite: 12 cases passed with a successful subprocess exit after
  explicit Qt deferred-deletion cleanup. Earlier shutdown access violations were
  failures and were investigated, not suppressed.
- Initial full Windows offscreen run: 636 tests, 3 failures/1 error/1 skip. The
  offscreen platform initially had no fonts. Native Windows rerun skipped 244
  offscreen-only tests and is not full-suite acceptance. Complete rerun with
  `QT_QPA_PLATFORM=offscreen` and `QT_QPA_FONTDIR=C:\Windows\Fonts` is required.
- `pip-audit` 2.10.1 initially found advisories only in local pip 25.0.1; after
  updating that venv build tool to 26.2.2, the scan returned no known vulnerabilities.
  This is advisory evidence for the resolved environment, not proof of all security.

## Mandatory gates and limits

Do not merge until final-head Linux/full Windows regression, independent review,
CI and installed acceptance are verified. The new Linux workflow runs the full
discovered suite, including actual QWebChannel interaction. The existing Windows
packaging workflow retains payload hash, uninstall and V1-exclusion checks.

Physical 33-case Windows acceptance, Word/PDF visual fidelity, Explorer/clipboard,
Windows scaling, real Assistant isolation and physical #98/#99 retests are not
certified by synthetic source/frozen smoke. HTML remains opt-in. V1 installers,
user reports and legacy source archives are not replaced.

Known presentation limits: text inputs show source wording rather than WYSIWYG
rich typography; supported edits preserve formatting through the established
remapper, and ambiguous edits fail visibly. Live Sheet is schematic; PDF Proof
uses the existing exporter and is invalidated after canonical changes. Revision
projections still traverse the canonical report; the thumbnail cache and changed
card transport reduce repeated media/render work without claiming virtualization
of arbitrarily large projects. Native V2 remains available for richer editing.

## 2026-10-30 — Word ribbon and Windows packager follow-up (from `88c4b6b`)

Current PR source base: `88c4b6b83fa38b606ea2daecbda569377713ce27`.
GitHub hosted Windows `windows-v2-frozen-installed-smoke` job 124191028065
on this base **failed**, after freeze, at its archived HTML resource inventory:
`web_assets/index.html`, `studio.css`, `studio.js`, `transport.js`,
and `events.js` were absent from the frozen payload. Consequently the
installer, binary comparison, HTML installed smoke and uninstall steps were
not executed. This failure was not waiver-eligible.

Follow-up changes on the same PR branch:

- Both local and hosted Windows builders explicitly bundle reportmaker data
  resources and QtWebChannel, and validate **both** native and HTML V2
  startup paths after freezing and installation. The archive must contain
  each HTML resource; no V1 launcher or legacy module is included.
- The hosted Windows source gate now executes real HTML renderer/QWebChannel
  tests and canonical rich-text command tests, rather than testing native
  V2 alone.
- The Word ribbon's selection indicators use UTF-16-to-codepoint mapping,
  check *every character* of a selection for an active style, and respect
  the caret position without borrowing styling from an unrelated text run.
- Sorting multiple lines with styled rich text is rejected **without any
  canonical mutation** until a style-aware reorder exists; unstyled sorting
  remains supported. This prevents silent loss of run and paragraph styling.
- Added packaging regression assertions and actual Chromium user-interaction
  coverage for ribbon clicks, partial selections, Undo/Redo and .rmproj
  translation/rich-format persistence.

Linux initial focused checks: 14 HTML canonical command tests PASS; 7
packaging contract tests PASS; real Chromium suite PASS after the first
selection-indicator correction. The caret follow-up and full Linux regression
are separate exact-tree validation gates. The hosted Windows installer
gate and all physical M7 acceptance remain pending until the updated commit
is pushed and its checks complete. There is **no** new installed-Windows
acceptance, production V2 promotion, or merge authorization.
