# Phase 2 / issue #105 — Windows V2 supply-chain hardening

**Status: proposed isolated PR, not a release, production signoff, or V1 retirement.** Based on `main@d77102e9abc6b88bc6a21ba4ef604a62b0a8a996` after the approved #123 merge. Independent Windows CI/review/owner authorization are still mandatory. PR #124 is a separate, unmerged Linux CI change and is **not** a dependency of this branch.

## What is protected in this increment

1. The **only changed frozen Windows path** is the isolated V2 M7 preview/CI workflow and the matching local acceptance builder. Historical M0, RC2 and RC3 Windows publishing workflows/assets/tags are untouched. The V2 workflow still builds, freezes, validates, installs, compares every frozen file and uninstalls, and only uploads an unsigned **test** installer on separately opted-in manual dispatch. No automatic release or default UI promotion.
2. The reviewable input `packaging/windows/requirements-lock-input.txt` combines the existing pinned PyInstaller build requirement with `setuptools` and `wheel` (the project's PEP 517 build backend). The version-range desktop dependencies are read from `pyproject.toml`. `requirements-win312-x64.lock` is an **entire 22-package, version-and-SHA-256 hash-locked** Windows AMD64 Python 3.12 environment, compiled 2026-10-31 using `uv 0.13.6`. No unverified sdist/source distributions are allowed in the Windows V2 build.
3. Windows CI and the local Windows M7.3 builder install those requirements with pip `--require-hashes --only-binary=:all:` before installing the **reviewed local ReportMaker source only** using `--no-deps --no-build-isolation -e .`. The lock verifier rejects duplicate, unconstrained, un-hashed and missing essential dependencies; hosted CI also rejects changed tracked source and untracked package inputs before freezing, and the final provenance check rejects added, missing or drifted packages.
4. The Windows V2 hosted preflight runner is `windows-2022` x64 / Python **3.12**. The exact Python patch level and mutable GitHub-hosted runner image version are recorded in the generated provenance. This reduces configuration drift but **does not pin OS patches or Python patch bits**, and it does **not** prove binary-identical installers.
5. Preview builds generate a **CycloneDX 1.5 software-bill-of-materials** and sanitized JSON provenance including full checked-out source SHA (synthetic PR merge commit in GitHub Actions), separately recorded reviewed PR branch-head SHA, workflow/config commit and SHA-256 of the actual packaging configuration file, Python version, runner image, lock digest, versions plus SHA-256 for every wheel downloaded by pip, Qt and Qt WebEngine runtime, **embedded Chromium version and Chromium security-patch version**, frozen file SHA-256 inventory, and installer SHA-256. PR validation uploads **metadata only** with limited retention. Installer uploads retain the manual QA-only opt-in and one-day expiry; no secrets or private index URLs are copied into provenance.
6. Publication-relevant Actions in the isolated V2 workflow and the new weekly Qt security watcher are pinned to reviewed full SHAs: checkout v4 `11d5960a326750d5838078e36cf38b85af677262`, setup-python v5 `a26af69be951a213d495a4c3e4e4022e16d87065`, upload-artifact v4 `ea165f8d65b6e75b540449e92b4886f43607fa02`. Re-resolve tag -> SHA, inspect the action's changes and its security advisory, then review the upgrade as a PR before changing any action pin.
7. Weekly and on-demand read-only Qt watcher compares the pinned PySide6 against the latest PyPI version, failing when a newer version requires review. **It cannot detect all unpatched Chromium CVEs** or infer that a release is safe: review the [official Qt security advisories](https://wiki.qt.io/Qt_Security_Advisories), Qt WebEngine changelog, and [PySide6 releases](https://pypi.org/project/PySide6/) each week and before an installer. Cross-check `qt_runtime.chromium_security_patch` and rebuild/QA all Windows V2 payloads. No automatic upgrades.

## Lock generation and controlled refresh

Run from repository root with an independently reviewed `uv 0.13.6` installation:

```sh
uv pip compile pyproject.toml packaging/windows/requirements-lock-input.txt \
  --extra desktop --python-platform x86_64-pc-windows-msvc \
  --python-version 3.12 --generate-hashes --only-binary :all: \
  -o packaging/windows/requirements-win312-x64.lock
python scripts/windows_supply_chain.py \
  --lock packaging/windows/requirements-win312-x64.lock --verify-only
pip-audit -r packaging/windows/requirements-win312-x64.lock \
  --no-deps --disable-pip --progress-spinner off
```

Compare **all** resolved transitive versions and wheel hashes against the previous lock, review release/CVE advisories, rebuild from a fresh Windows image and capture both run manifests. A changed hash or dependency needs a reviewed explanation. The hash file may include hashes of multiple *available* wheels for a distribution; the Windows `pip --report` artifact pins the **actual** chosen wheel hash. If no Windows wheel is available, stop rather than fall back to source building.

## Remaining release/security blockers (issue stays open)

- **Critical:** The latest Python 3.12 security patches are source-only on Windows; the hosted `setup-python@v5` with `python-version: '3.12'` may install a previous Windows binary. A separately reviewed **Windows Python 3.14.x migration**, updated Windows AMD64 lock, Qt compatibility, PyInstaller checks, package freeze, and physical acceptance are needed before considering release security complete.
- **Historic publishing Actions** in `windows-installer.yml`, `windows-rc2.yml`, and `windows-rc3.yml` still have moving tags. Do **not** edit RC3 casually: its workflow triggers on changes to its own file on `main` and contains an immutable source-pinned publisher. Choose an independent mitigation/retirement plan and owner-approved release-gate PR; historical published assets must remain immutable.
- **Repeat-build comparison** requires two independent clean Windows builds with manifests, interpreter and OS-image details. Since Inno Setup and the OS are not hermetically pinned here, matching resolved dependency versions **does not imply bit-for-bit executable reproducibility**.
- Full Qt/Chromium CVE triage, signed publication provenance / attestation, V1 fallback protections, physical installed-Windows 33-case acceptance (#96) and #98/#99 retests remain outside this non-release security increment.

## Required PR gates

Exact-head GitHub continuity/M0/M1; dedicated V2 Windows x64 **hash-locked frozen-installed-uninstall** preflight; full Linux regression and synthetic integrity tests; lock audit; independent architecture/security/data integrity review; user-authorized merge. No merge, release, deletion or default UI switch without those gates.
