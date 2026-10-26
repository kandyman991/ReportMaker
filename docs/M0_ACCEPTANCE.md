# M0 acceptance checklist

M0 = architectural foundation plus browser integration feasibility. CI alone does not prove Windows usability.

Automated (Windows CI, synthetic data only):
- [ ] python -m unittest discover -s tests -v passes.
- [ ] python -m compileall -q src passes.
- [ ] Install pinned PySide6 desktop dependencies and import Windows Qt WebEngine UI module.
- [ ] Run online-free `python -m reportmaker --layout-self-test` on Windows (pane height, collapse, maximize, restoration, persistent settings); repeat inside the frozen .exe.
- [ ] Report validation rejects inverted dates/invalid language selections and conclusion stays last.
- [ ] Arbitrary module block ordering and nesting represented without Qt dependencies.
- [ ] Contract guard protects Windows/browser-only/no-API/any-language invariants.

Manual — REQUIRED on actual Windows computer:
- [ ] Install dependencies in a Python virtualenv; launch python -m reportmaker.
- [ ] Three-pane shell opens and dividers resize all panes (including dragging a pane to zero width) without clipping.
- [ ] Embedded ChatGPT site fills at least 70% of the usable panel height, rather than a narrow strip.
- [ ] Modules, Editor and ChatGPT can each be collapsed/reopened from the always-visible toolbar.
- [ ] Each panel maximizes and restores; the previously selected widths and visibility are preserved.
- [ ] Pane sizes and collapsed state survive exit and relaunch; Reset layout restores all three.
- [ ] Report scratchpad text remains in memory after panel hide/maximize/restore (not saved on exit).
- [ ] Browser loads https://chatgpt.com over HTTPS; any redirects remain visible to the user.
- [ ] User attempts normal login themselves. Record pass/fail/blocked; do NOT share tokens or passwords.
- [ ] Closing/reopening browser retains normal persistent site state if permitted; failure is acceptable with external fallback.
- [ ] External browser fallback opens actual chatgpt.com and can be used if embedded view fails.
- [ ] Manually copy a harmless text sample and click Paste as plain text; verify no automatic AI traffic.
- [ ] Check writable profile location, profile isolation and that logs do not contain authentication details.
- [ ] Verify clean app exit, no account control/network activity besides the embedded site, no reports/customer data uploaded.
- [ ] Download M0 installer artifact from GitHub Actions; extract and run Setup.exe without Python, Git or PowerShell.
- [ ] Installer does not prompt for administrator access on a normal per-user Windows desktop.
- [ ] Start Menu shortcut starts the application; optional desktop shortcut works.
- [ ] Installed binary contains Qt WebEngine resources; verify browser renders a real web page or shows fallback.
- [ ] Uninstall removes installed application files and shortcuts but preserves user-local profile by design.
- [ ] Verify Windows SmartScreen/signing state, source provenance, artifact SHA-256 and no credential leaks.
- [ ] Perform normal login compatibility test with the *user* at the Windows desktop; packaged about:blank smoke-test is not this test.

Keep results in a review comment with OS/Python version and observed behavior. Never save credentials or raw browser diagnostic captures.
