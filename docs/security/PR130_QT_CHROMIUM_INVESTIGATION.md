# PR #130 — Qt WebEngine / Chromium vulnerability investigation (issue #105)

**Investigation date:** 2026-11-01 (Europe/Rome). **Classification:** non-release, security investigation and advisory watcher only.
**Result: RELEASE HOLD.** No Qt dependency bump, production installer, publication, signing, attestation dispatch,
V1 retirement, or physical-Windows acceptance is performed by this PR. The five Chromium CVEs below are
**upstream review candidates**, *not* confirmed exploitable flaws in the exact ReportMaker Qt wheel.

## 1. Reproducible inventory and evidence limitations

- The canonical V2 Windows Python 3.14 AMD64 lock includes `pyside6==6.12.0`,
  `pyside6-webengine==6.12.0.140`, plus the corresponding PySide6 addons/essentials and
  `pyside6-pdf==6.12.0.140`; installation is hashed/wheel-only in the separate supply-chain gate.
  The desktop optional dependency in `pyproject.toml` pins PySide6 to 6.12.0.
- The expected runtime values in `security/webengine_release_review.json` are Qt **6.12.0**,
  Qt WebEngine **6.140.0**, Chromium **140.0.7339.225** *base*, and Qt-reported Chromium
  security-patch level **152.0.7977.83**. These values are *recorded claims*, not direct
  proof that a specific security patch was built into a shipped Windows binary.
  Independently inspect `qt_runtime`, wheel hashes, installed DLLs and build provenance for
  each **exact** new Windows installer; vendor backports require upstream evidence.
- Qt separated its WebEngine release cadence/versioning from core Qt 6.12. Consequently
  comparing **only** PySide6 versions cannot detect an independently published PySide6-WebEngine
  wheel update. `scripts/check_qt_webengine_updates.py` now checks BOTH PyPI projects against
  the actual Windows lock. This is an **update signal**, not CVE detection or clearance.
- PyPI lists the PySide6-WebEngine **6.12.0.140** Windows x64 wheel released **2026-10-08**.
  PyPI currently shows **no provenance attestation** for that file. A locked wheel SHA-256
  does not independently establish a vendor security fix or verified publish provenance.

Official references:
- Qt's separate-release announcement: https://www.qt.io/blog/qt-webengine-will-release-separate
- Qt Chromium version/backport methodology: https://wiki.qt.io/QtWebEngine/ChromiumVersions
- Qt security advisory index: https://wiki.qt.io/Qt_Security_Advisories
- PySide6 WebEngine release and wheel: https://pypi.org/project/PySide6-WebEngine/6.12.0.140/

## 2. Upstream Chromium critical-CVE candidates (not confirmed Qt exposure)

| CVE | Chrome advisory / component | Published stable channel | Qt wheel fix status |
| --- | --- | --- | --- |
| CVE-2026-118306 | Critical memory corruption, FileSystem | 2026-10-27; Chrome 156.0.8078.73/.74 | Unknown; HOLD |
| CVE-2026-118331 | Critical improper input validation, FileAPI | 2026-10-27; Chrome 156.0.8078.73/.74 | Unknown; HOLD |
| CVE-2026-118348 | Critical improper input validation, Skia | 2026-10-27; Chrome 156.0.8078.73/.74 | Unknown; HOLD |
| CVE-2026-118344 | Critical use-after-free, Layout | 2026-10-27; Chrome 156.0.8078.73/.74 | Unknown; HOLD |
| CVE-2026-76024 | Critical memory corruption, MediaStream | 2026-10-29; Chrome 156.0.8078.79/.80 | Unknown; HOLD |

Primary sources:
- https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_0562499947.html
- https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_02107719452.html

A newer Chrome stable release number than the Qt reported patch level is **not** proof that
an individual CVE affects Qt. Conversely, the Qt security-patch *label* is **not**
proof that those October 27/29 fixes were backported. Chrome bug details can be access-restricted.
No publicly verified, CVE-specific Qt source patch/release bulletin was established for
these five CVEs at this review date. They remain `untriaged` and the policy
`release_decision` stays `hold`; do not convert missing evidence into `not_affected`.

## 3. ReportMaker attack surface and compensating boundaries

| Runtime entry point | Relevant source/guard | Scope of investigation |
| --- | --- | --- |
| V2 HTML studio | `src/reportmaker/v2/web_ui.py`: QWebEngineView + QWebChannel | Has a privileged command bridge. `dispatch` checks exact trusted studio entry URL and canonical revision/generation; any renderer compromise requires special scrutiny. |
| Offline studio origin | `src/reportmaker/v2/web_origin.py`, `web_assets/index.html` | `rmstudio://app/index.html`, allowlisted local resources, blocked external navigation/downloads, CSP `connect-src 'none'`, `frame-src 'none'`, `object-src 'none'`. These mitigate web-content exposure but **cannot be treated as Chromium native memory-safety patches**. |
| Assistant browser tab | `src/reportmaker/v2/chat_tab.py` | Explicitly opens a remote website in a separate QWebEngine page/profile (lazily); it is not the studio bridge. Remote content and untrusted media make the Qt WebEngine native attack surface relevant despite the offline studio design. |
| Imported report content/images | Canonical edit commands and generated studio image resources | Skia/Layout/FileAPI reachability cannot be ruled out merely because the studio does not navigate to external websites. Establish actual code-path applicability per advisory before claiming non-exposure. |

**Open questions that require vendor/source or binary-specific evidence:**
1. Which exact Chromium 156 security patches are carried into the **specific** 6.140.0
   QtWebEngine/6.12.0.140 Windows wheel, including downstream backport commits and build flags?
2. Which affected subsystems are compiled and reachable from the installed app's
   assistant website, studio HTML, imported graphics and local file/resource schemes?
3. Is there a newer compatible, vendor-supported WebEngine wheel on PyPI, and does it
   contain documented remediation? Check PySide6 and PySide6-WebEngine independently.
4. Verify WebEngine subprocess sandbox behavior and packaging of QtWebEngineProcess,
   resources, DLLs and compiler options on the **exact** Windows preview installer.
5. Identify any additional *relevant* Chromium high/critical and Qt framework advisories;
   this initial five-CVE baseline is not an exhaustive vulnerability inventory.

## 4. Gates introduced and not introduced

- The weekly GitHub read-only security watcher independently fetches latest PyPI
  `PySide6` **and** `PySide6-WebEngine` metadata; it warns/fails on a newer version.
  It never installs packages, changes the lock, opens an issue automatically, or publishes.
- `scripts/check_webengine_release_risk.py --strict` requires an actual
  `--provenance <windows-v2-provenance.json>`. It compares **all four** relevant Qt
  runtime fields (Qt, QtWebEngine, Chromium base, Qt Chromium security patch), checks
  the installed PySide6 and WebEngine wheel versions, and requires the structured Windows
  build provenance schema, installer SHA-256, source commits, lock digest, and wheel inventory.
  It fails on missing/malformed/duplicate/removed critical CVE review records. This schema
  check does **not** authenticate provenance: independent signed attestation and physical
  installed-payload verification remain mandatory. Default scheduled
  advisory mode remains non-blocking. Test fixtures with fake vendor URLs and runtime
  data prove validation behavior only, **not** security remediation.
- `security/webengine_release_review.json` intentionally remains on `hold`; existing
  locked Qt/WebEngine versions do not change in this PR.
- No claim is made that PyPI reports all CVEs, that a version bump alone resolves
  vulnerabilities, or that machine-readable policy statuses alone constitute independent
  security review.

## 5. Independent review and next release-readiness steps

1. Independent security reviewer checks upstream Chrome advisories, Qt changelog/source,
   actual Windows wheel and vulnerable code-path applicability, documenting **per CVE**
   vendor-owned fix/non-applicability proof and exact tested binary digests.
2. Any required Qt/WebEngine upgrade happens in a **separate reviewed PR** with a fully
   regenerated hashed Windows lock, compatible PySide wheels, PyInstaller frozen
   smoke tests, HTML/ChatGPT navigation/security tests, and fresh exact-head CI.
3. Run the complete independent architecture, security and data-integrity review of
   PR #130 itself; resolve findings on its branch, then rerun all required CI
   at the **final** head SHA. The existing hold must not be cleared solely on this PR.
4. **Do not merge** without a subsequent explicit owner authorization. **Do not publish**
   any release without its separate authorization; #105 remains OPEN. Installer
   Authenticode and attestation, and **33/33 manual physical Windows cases**, remain
   independent unsatisfied release gates.
