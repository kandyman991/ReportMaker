# Issue #105 — verifiable signature/attestation and physical Windows release gates

**Status (2026-10-31): NON-RELEASE. No production release or merge approved.** The current V2 Windows build remains an isolated, unsigned preview. The retired M0/RC2/RC3 publishers must remain disabled. No existing release/tag/asset must be modified or deleted.

## Separate facts: unsigned build, attested JSON, and signed installer

1. The Windows preview uses fully SHA-256 locked wheels (Python 3.14.10), a generated CycloneDX SBOM, a frozen-file SHA listing, and **unsigned** installer SHA-256. Hash matching is not a signature and does not establish who published an installer.
2. PR #128 added a **trusted-main-only, explicit opt-in** `attest_nonrelease_metadata` job. It may cryptographically attest **exactly the JSON provenance and SBOM** after hosted Windows packaging; it cannot sign the installer. It has not been dispatched merely by preparing this PR. Never run it on a PR head or reinterpret a skipped job as a successful attestation.
3. On a separately owner-approved signing host, sign a *copy* of the independently verified unsigned installer using a reviewed commercial/publicly trusted Authenticode identity, RFC 3161 SHA-256 timestamp, protected key material (prefer protected HSM/cloud signing with human release approvals). The **signed installer has a different SHA-256**. Record both unsigned and signed hashes; do not replace provenance's unsigned hash with the signed one.
4. Independently check the signed **bytes** on an actual Windows host against the approved certificate thumbprint. Neither GitHub metadata attestations nor an unsigned installer checksum can substitute for Authenticode, and a valid Authenticode signature alone does not prove a full release approval or completed GUI acceptance.
5. A future separate owner-authorized production-release PR must introduce protected environment approval, identity/key custody and revocation procedure, direct signed-installer provenance/attestation, independent signature/download testing, and release rollback. **There are no owner-provided signing credentials or connected physical Windows hosts in the current environment.**

### Verify real GitHub metadata attestations — fail closed

Prerequisites: a recent GitHub CLI supporting `gh attestation verify`, authenticated for repository access, **actual separately authorized trusted `main` workflow_dispatch** with `attest_nonrelease_metadata=true`, and the *two exact JSON files* downloaded from that same successful run. Current Legion Ubuntu's `gh 2.46.0` **does not implement `gh attestation`**; upgrade the CLI through an approved channel before using this verification path. Do not update GitHub tools on a production box blindly.

```sh
# Use the exact actual committed sha from the approved main workflow run.
MAIN_SHA='<trusted-main-run-sha>'
# Download ONLY windows-v2-provenance.json and windows-v2-sbom.cdx.json
# from that particular run into a fresh directory.
python scripts/verify_v2_metadata_attestations.py /path/to/metadata \
  --expected-main-commit "$MAIN_SHA"
```

The verifier requires:
- exactly two expected JSONs; no symlinks or binary installer;
- reviewed main source, configuration and branch SHA to match the caller-pinned SHA;
- Python 3.14.10, 22 SHA-locked wheels and matching CycloneDX identities, Windows Qt and 3,000+ frozen-file hashes;
- a successful **online GitHub cryptographic verification** of *each exact JSON file*, scoped to `kandyman991/ReportMaker`, `kandyman991/ReportMaker/.github/workflows/v2-m7-packaging.yml`, `refs/heads/main`, and exact commit digest;
- the exact JSON SHA-256 as verified subject in GitHub's attestation; rejects missing, altered, unverifiable or wrong-subject files.

There is intentionally **no offline `--bundle` acceptance path**: GitHub's documentation warns that offline verification alone cannot detect repository-name reassignment. The verified JSON's *installer hash is only a claim* made by its builder, **not** proof of a signed installer.

Source: <https://cli.github.com/manual/gh_attestation_verify>.

### Verify a future signed installer — fail closed, no signing performed

On a **genuine Windows** host with Windows SDK SignTool installed, after independently approving the signer certificate (NOT a self-signed test certificate) and recording both SHA-256 values:

```powershell
./scripts/verify_windows_installer_authenticode.ps1 `
  -Installer "C:\\QA\\ReportMaker-V2-SIGNED-Setup.exe" `
  -ExpectedSignedSha256 "<signed-installer-sha256>" `
  -UnsignedBuildSha256 "<unsigned-build-sha256-from-provenance>" `
  -ApprovedSignerThumbprint "<reviewed-publisher-certificate-SHA1-thumbprint>"
```

The script makes **no signing request** and has no credentials. It first checks the original Windows build provenance's exact main source/config revision and unsigned installer checksum, then checks `Get-FileHash`, Windows native Authenticode trust, signer certificate thumbprint, timestamp certificate, plus SignTool `verify /pa /all /tw /v` with zero/warning-free exit. This script is **not executable as acceptance evidence on Linux**. If the signing service returns a certificate or timestamp mismatch, release is blocked. Microsoft references: <https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-verify-a-file-signature> and <https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures>.

### Qt WebEngine / Chromium triage remains HOLD

The locked Windows preview reports Qt/PySide6 **6.12.0**, Qt WebEngine **6.140.0** (Chromium **140.0.7339.225** baseline with reported vendor security patch **152.0.7977.83**). Chrome 156 Oct 27/29 advisories listed the five previously recorded critical candidates. **Do not declare those CVEs exploitable in the embedded Qt binary** solely on version distance; Qt backports Chrome security fixes and now releases WebEngine separately. See <https://www.qt.io/blog/qt-webengine-will-release-separate>, <https://wiki.qt.io/QtWebEngine/ChromiumVersions>, and <https://chromereleases.googleblog.com/2026/10/>.

A stronger strict gate in `scripts/check_webengine_release_risk.py` now requires **Qt-maintained HTTPS primary references** (not arbitrary user-supplied URLs or `example.com`) for each CVE's fix/non-applicability and the general backport review. It still requires actual reviewed running Windows Qt/Chromium provenance and remains **HOLD**. A link is necessary but **not sufficient**: independent reviewers must verify whether the fixes are included in the exact Qt wheel and if enabled HTML content can reach affected browser code. Review added Chromium/Qt advisories before approving any dependency version bump.

### Physical Windows 33-case acceptance — all pending

The canonical JSON `docs/v2/M7_ACCEPTANCE_MATRIX.json` remains the sole source of 33 cases.

```sh
python scripts/physical_windows_acceptance_checklist.py --output physical-windows-pending.md
```

The generated checklist is **not completion evidence**. On a real Windows PC use `scripts/validate_windows_physical_acceptance.py --init` with known exact source and installer hash, then perform each case in the installed GUI using synthetic data. Record per-case observations and real SHA-256'd screenshots/logs, and run the verifier against the matching build provenance. Obtain independent evidence review. Do not use the hosted Windows CI runner or the Linux Legion as a replacement for a physical Windows test host. See `docs/security/PHASE2_RELEASE_SAFETY_105.md`.

**Current status:** signing identity unavailable; no signed installer; no successfully verified GitHub attestation; Qt vendor evidence incomplete; **33/33 physical cases pending**. These are **release blockers**, not blockers for reviewing this isolated non-release PR. Issue #105 stays OPEN.
