# Phase 2 / issue #105 — historical publisher Action pins and repeat-build evidence

**Scope: review-only, non-release security increment; no historical release or installer publication.** Source base is the owner-merged PR #126. No Windows application, report, storage/migration, release tag, M0/RC2/RC3 artifact or V1 fallback is changed.

## Historical publisher safety decisions

| Publisher | Trigger and risk | Change in this PR | Gate |
| --- | --- | --- | --- |
| `windows-installer.yml` (M0, rolling) | Manual dispatch on main; **can overwrite** the M0 rolling release and delete expired Actions artifacts | Pin checkout v4 to `11d5960a326750d5838078e36cf38b85af677262`, setup-python v5 to `a26af69be951a213d495a4c3e4e4022e16d87065`; prevent persisted checkout credentials | Do **not** manually dispatch or change its source SHA |
| `windows-rc2.yml` | Manual dispatch on main; immutable RC2 release and publisher use `contents: write` | Pin two checkout v4 calls and setup-python v5 to the same reviewed full SHAs; no trigger changes | Do **not** manually dispatch; preserve source and tag |
| `windows-rc3.yml` | **Critical:** modifying this file on `main` triggers its one-time release publisher; source pinned, release exists | **Intentionally no change**. Add static SHA-256 regression check of workflow and `ReportMaker-RC3.iss` (normalize Windows CRLF checkout), with a dedicated future release-control approval gate | Must not change these files without an independently reviewed way to disable unintended publication and explicit owner authorization |

Action revisions are the tag-resolution commits verified at the 2026-10-31 review. A full SHA is a frozen revision, *not* proof that the Action or its transitive packages are risk-free. The existing old publisher Python 3.12 / mutable Windows runner / un-hashed transitive dependencies remain **not release-hardened**; no new historical release is authorized.

## Repeat-build verification (read-only, no installer publication)

The existing isolated V2 workflow can build two genuinely **independent clean hosted Windows** previews by using `workflow_dispatch` with `manual_qa_installer=false`. The workflow will upload **metadata only**, never the installer. Execute the *same reviewed head* in two separately identified successful runs, record both run IDs and download their distinct `ReportMaker-V2-SUPPLY-CHAIN-<github.sha>` artifacts to different local directories. Do not use the M0/RC2/RC3 publisher workflows.

For example, after ensuring the V2 workflow exists on the target branch:

```sh
gh workflow run v2-m7-packaging.yml --repo kandyman991/ReportMaker \
  --ref SECURITY_BRANCH -f manual_qa_installer=false
# After completion, record RUN_ID_1, download its supply-chain JSON metadata.
gh workflow run v2-m7-packaging.yml --repo kandyman991/ReportMaker \
  --ref SECURITY_BRANCH -f manual_qa_installer=false
# After completion, record RUN_ID_2 and download to a different directory.

python scripts/compare_windows_build_provenance.py \
  /path/to/run-1/windows-v2-provenance.json \
  /path/to/run-2/windows-v2-provenance.json \
  --json-out /path/to/secure-comparison-report.json
```

The comparator:
- Fails on malformed manifests, duplicate wheels/payload entries, missing SHA-256s or Git commit IDs, mismatched source/config commits, interpreter, runner image/version, Qt/Chromium versions, lock SHA, actual wheel filenames and hashes, installer hash or any **one** frozen-payload SHA. It compares future toolchain fields automatically.
- Ignores only `generated_utc`: generated timestamps must differ across builds. Records concise counts and a sample of differences without a 3,000-file log flood.
- Returns exit code **0** for matching byte hashes across all recorded items, **1** for genuine recorded differences, and **2** for malformed input.
- Makes **no claim of full hermetic reproducibility**: OS image and Inno Setup compiler are not hermetically pinned, and manifest matching cannot prove external inputs, digital signatures, Windows installer GUI quality or real production readiness. A matching metadata pair is supporting evidence, not a cryptographic attestation from an independent trusted builder.

## First independent build comparison and deterministic-build correction

Two explicitly non-releasing `workflow_dispatch` runs on branch head `af672cacdf824a30b6936bf157fef9d9b56a86d7`, run IDs `41225402662` and `41225409877`, both **passed** Windows V2 freeze/install/native+HTML offscreen smoke, full installed-payload comparison and uninstall. Both produced metadata only, with the same Windows image, Python 3.14.10, 22 wheel hashes and 3,199 frozen payload paths. However, actual SHA-256 **differed** for two PyInstaller-generated files: `ReportMakerV2.exe` and `_internal/base_library.zip`; Inno installer SHA-256 also differed. This is a reproducibility **finding**, not a functional Windows installation failure. The comparator correctly returned exit code 1.

The isolated V2 CI and matching local build helper now set `PYTHONHASHSEED=1` and `SOURCE_DATE_EPOCH` to the checked-out Git source commit timestamp immediately before PyInstaller. PyInstaller [documents](https://pyinstaller.org/en/stable/advanced-topics.html#creating-a-reproducible-build) both controls for bytecode hashing and Windows PE timestamps. Using a Git commit timestamp avoids injecting each runner's clock into the bundle. **This correction is not validated as reproducible until two fresh, matching-head Windows builds are compared**; if the installer alone still differs, investigate the Inno toolchain and embedded metadata independently. No binary is modified in place.

## Second comparison — frozen payload now byte-identical

On the corrected Python-build head `8611060a4f0368eae6d849cfec6323f0d9a43061`, independent Windows non-release runs `41226203261` and `41226210228` both passed. Their SHA-256 manifests showed **all 3,199 frozen payload files byte-identical**, plus all 22 wheel hashes and source/config/interpreter/runner metadata identical. The installer SHA-256 **still differed**, so the comparison correctly returned exit code 1: installer reproducibility is *not* yet established.

The official [Inno Setup security documentation](https://jrsoftware.org/is6help/topic_securitymeasures.htm) identifies `notimestamp` for `[Files]` as a way to omit nondeterministic source-file timestamps. The V2-only `ReportMaker-V2-M7.iss` now uses it while preserving its V1-isolated AppId and all install behavior. This is **a pending correction**, not a claim of installer reproducibility; new exact-head hosted Windows build/install/uninstall and two independent metadata-only runs must pass and agree before the installer is called byte-repeatable. The RC2/RC3/M0 historical installer definitions and all published assets remain untouched.

## Required independent PR and release gates

1. Static tests: full SHA pins in only manual M0/RC2 publishers; source SHA and manual triggers unchanged, RC3 publisher+installer unchanged at known reviewed SHA-256 values.
2. Tested provenance comparison: altered binary, wheel, source, environment or future toolchain metadata must cause a failing result; malformed/duplicate manifests must be rejected.
3. Exact-head hosted CI continuity and M0/M1 tests, Linux complete regression and V2 native/HTML smoke. Two manual, metadata-only Windows builds should be compared before claiming actual reproducibility (otherwise record it as open).
4. Separate architecture/security/data-integrity/release-impact review; correct findings and re-run exact-head checks, then request **owner merge authorization**.
5. **Do not dispatch historical release publishers**, publish installers, touch RC3 trigger/installer, delete release assets, retire V1, close #105 or change default HTML. Publication-critical legacy RC3 pinning requires a distinct owner-approved release-control mitigation.

The issue remains open pending RC3 release-control hardening, repeat-build evidence and/or further determinism remediation, physical Windows acceptance, signed provenance and full Qt/Chromium CVE triage.
