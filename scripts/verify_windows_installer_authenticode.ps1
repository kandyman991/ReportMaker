# READ-ONLY. Intended for an actual physical/controlled Windows verification host.
# No private keys, signer credentials, cloud signing, timestamp network requests,
# code-signing step, installer changes, artifact uploads, or GitHub release actions.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$ProvenanceJson,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Fa-f0-9]{40}$')][string]$ExpectedMainCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ExpectedSignedSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Fa-f0-9]{40}$')][string]$ApprovedSignerThumbprint,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$UnsignedBuildSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw 'Windows Authenticode verification requires a native Windows verification host'
}
if (!(Test-Path -LiteralPath $ProvenanceJson -PathType Leaf)) { throw 'Original build provenance missing' }
$provenance = Get-Content -LiteralPath $ProvenanceJson -Raw -Encoding UTF8 | ConvertFrom-Json
if ($provenance.schema -ne 'reportmaker.windows-v2-build-provenance.v1' -or
    $provenance.installer.filename -ne 'ReportMaker-V2-M7-Preview-Setup.exe' -or
    $provenance.python -ne '3.14.10') {
    throw 'Signed installer must be matched to reviewed Windows V2 provenance'
}
$source = $ExpectedMainCommit.ToLowerInvariant()
if ($provenance.source_commit -cne $source -or
    $provenance.reviewed_branch_head_commit -cne $source -or
    $provenance.configuration_commit -cne $source) {
    throw 'Unsigned build provenance does not belong to the approved main source'
}
if ($provenance.installer.sha256 -cne $UnsignedBuildSha256.ToLowerInvariant()) {
    throw 'Unsigned installer hash differs from pinned build provenance'
}
if (!(Test-Path -LiteralPath $Installer -PathType Leaf)) { throw 'Signed installer not found' }
if ([IO.Path]::GetExtension($Installer) -ine '.exe') { throw 'Only Windows .exe installer accepted' }
$actual = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = $ExpectedSignedSha256.ToLowerInvariant()
if ($actual -cne $expected) { throw "SIGNED installer digest mismatch: $actual" }
if ($actual -ceq $UnsignedBuildSha256.ToLowerInvariant()) {
    throw 'Signed installer digest must differ from the recorded unsigned build (signing changes bytes)'
}
$sig = Get-AuthenticodeSignature -LiteralPath $Installer
if ($null -eq $sig -or $sig.Status -ne 'Valid') {
    throw "Windows trust policy rejected Authenticode: $($sig.Status)"
}
if ($null -eq $sig.SignerCertificate) { throw 'Signer certificate missing' }
$signer = $sig.SignerCertificate.Thumbprint.ToLowerInvariant()
if ($signer -cne $ApprovedSignerThumbprint.ToLowerInvariant()) {
    throw "Signer certificate thumbprint $signer is not explicitly approved"
}
$ts = $sig.TimeStamperCertificate
if ($null -eq $ts) { throw 'No trusted timestamp countersignature found' }
# A valid primary signature alone is insufficient; verify *all* embedded
# signatures with Windows SDK SignTool, Authenticode policy and timestamp warning.
$signtool = Get-Command 'signtool.exe' -ErrorAction Stop
& $signtool.Source verify /pa /all /tw /v $Installer
if ($LASTEXITCODE -ne 0) { throw "SignTool Authenticode verification failed or warned ($LASTEXITCODE)" }
[PSCustomObject]@{
    schema = 'reportmaker.windows-signed-installer-verification.v1'
    status = 'verified_on_windows'
    installer_sha256 = $actual
    previous_unsigned_installer_sha256 = $UnsignedBuildSha256.ToLowerInvariant()
    reviewed_source_commit = $source
    approved_signer_thumbprint = $signer
    signer_subject = $sig.SignerCertificate.Subject
    timestamp_signer = $ts.Subject
    host_os = [Environment]::OSVersion.VersionString
    limitation = 'This is verifier output, not a signed attestation. Retain the approved certificate identity and independent release review.'
} | ConvertTo-Json -Depth 4
