# Phase 2 / issue #105 — isolated Windows V2 Python 3.14 migration

**Status:** independent-review candidate only. No release, merge approval, V1 retirement, HTML default change, or physical Windows signoff. Starts from post-#125 `main@34242deb5af4a932131b862ac5ff27bf87fe3c40`, independent of open PR #124.

## Why this is a separate gate

The Windows V2 preview currently packages Python 3.12.10 while Python 3.12 security fixes are issued only as source distributions. CPython 3.14.10 (released 2026-10-25) includes a patched Windows binary installer, including eMudhra CA distrust changes. Move the *isolated, non-release* V2 freeze/installed acceptance path to Python **3.14.10 x64**, keep its reviewable, hashed dependency environment, and require real hosted-Windows validation before considering it safe. This neither modernizes RC2/RC3/M0 publication paths nor retroactively fixes any published artifact.

Official references:
- https://blog.python.org/2026/10/python-3152-31410-31318-31216-31118/
- https://devguide.python.org/versions/
- https://pyinstaller.org/en/latest/CHANGES.html (Python 3.14 supported since PyInstaller 6.15)

## Scoped code changes

1. Hosted Windows V2 preview uses `windows-2022`, Python **3.14.10** exact patch and x64 with a runtime version assertion *before dependency installation*. This fails closed if the exact patched installer is unavailable.
2. Re-resolve `packaging/windows/requirements-win314-x64.lock` for CPython 3.14 / Windows AMD64, including PyInstaller and every transitive wheel, with SHA-256 hashes and no sdist fallback. It contains 22 pinned packages. Retain the original `requirements-win312-x64.lock` for traceable historic evidence, **never** use it in the new V2 CI/builder.
3. The matching local physical-Windows builder now uses `py -3.14` and refuses Python versions earlier than **3.14.10**, 3.15+, non-Windows and non-x64. It still requires an entirely new virtualenv; no automatic installation or promotion.
4. Retain existing frozen/installed native + HTML offline smoke, complete payload hash comparison, uninstall gate, provenance and CycloneDX SBOM metadata upload. The automation still does not upload PR installers. Optional manual `workflow_dispatch` uploads remain one-day, unsigned, test-only.
5. No changes to application source, canonical model, storage/migrations, project/customer files, historical publisher workflows, V1, or HTML-default selection.

## Lock regeneration

Use reviewed `uv 0.13.6` with current package metadata; compare all versions and hashes against the prior lock before accepting changes:

```sh
uv pip compile pyproject.toml packaging/windows/requirements-lock-input.txt \
  --extra desktop --python-platform x86_64-pc-windows-msvc \
  --python-version 3.14 --generate-hashes --only-binary :all: \
  -o packaging/windows/requirements-win314-x64.lock
python scripts/windows_supply_chain.py \
  --lock packaging/windows/requirements-win314-x64.lock --verify-only
pip-audit -r packaging/windows/requirements-win314-x64.lock \
  --no-deps --disable-pip --progress-spinner off
```

The dedicated Ubuntu lock-audit runner can use Python 3.12 because it *inspects only lock metadata* and never builds the Windows binary. Only the `windows-v2-frozen-installed-smoke` job determines Windows build compatibility and captures the actual Python runtime version in its provenance.

## Validation and remaining gates

- Local review: full Python regression, Linux native + HTML QtWebEngine/QWebChannel offline smoke, static package/legacy boundary tests, YAML parse, Ruff, lock verifier.
- Hosted exact-head PR: continuity, M0/M1 and **Windows V2 Python 3.14.10** package freeze, installer, installed native/HTML smoke, every-file comparison, uninstall, provenance/SBOM, Windows lock audit.
- Independent architecture/security/data-integrity/release-impact review **after** hosted runs; correct any findings and rerun on the corrected head.
- Physical Windows installed GUI acceptance 33-case gate, Qt/Chromium CVE assessment and repeat clean-build comparison still outstanding. Python version migration is necessary but not sufficient for a production release.
- Do not merge without explicit owner authorization. Issue #105 stays open until historical release-control action pins, repeat-build evidence, provenance attestation/signing decisions and physical acceptance are separately resolved.
