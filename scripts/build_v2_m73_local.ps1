# Build an isolated V2 preview locally on a physical Windows x64 PC.
# No GitHub upload, release, credential capture, browser access or V1 modification.
[CmdletBinding()]
param(
    [switch]$Install,
    [string]$OutputDirectory = (Join-Path $env:LOCALAPPDATA "ReportMaker-M73-LocalPreview"),
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA "ReportMaker-M73-PhysicalAcceptance"),
    [string]$IsccPath = ""
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($PSVersionTable.PSEdition -ne "Desktop" -and -not $IsWindows) {
    throw "This script requires Windows x64, not Linux/macOS"
}
if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess) {
    throw "M7.3 requires 64-bit Windows and a 64-bit PowerShell process"
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    $output = [IO.Path]::GetFullPath($OutputDirectory)
    if ($output.StartsWith($root + [IO.Path]::DirectorySeparatorChar,
                            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Keep the installer and build spec outside the Git working tree"
    }
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    $specDir = Join-Path $output "_spec"
    New-Item -ItemType Directory -Path $specDir -Force | Out-Null
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git is required to record the exact source SHA"
    }
    $sourceSha = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch "^[a-f0-9]{40}$") {
        throw "Not a valid checked-out ReportMaker commit"
    }
    $dirty = @(& git status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -gt 0) {
        throw "Tracked worktree must be clean; do not test an uncommitted build"
    }
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Python 3.12 x64 launcher 'py' is required"
    }
    $venvDir = Join-Path $root ".venv"
    if (-not (Test-Path $venvDir)) {
        & py -3.12 -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw "Unable to create Python 3.12 environment" }
    }
    $python = Join-Path $venvDir "Scripts\python.exe"
    & $python -c "import platform,struct; assert platform.system()=='Windows' and struct.calcsize('P')==8"
    if ($LASTEXITCODE -ne 0) { throw "Python must be Windows x64" }
    & $python -m pip install --disable-pip-version-check -e ".[desktop]"
    if ($LASTEXITCODE -ne 0) { throw "Desktop dependency installation failed" }
    & $python -m pip install --disable-pip-version-check -r packaging/windows/requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Pinned PyInstaller dependency installation failed" }
    $env:QT_QPA_PLATFORM = "offscreen"
    & $python -m reportmaker.v2 --offline-self-test
    if ($LASTEXITCODE -ne 0) { throw "Native V2 source smoke failed" }
    & $python -m reportmaker.v2 --html --offline-self-test
    if ($LASTEXITCODE -ne 0) { throw "HTML V2 source offline test failed" }
    & $python -m PyInstaller --noconfirm --clean --windowed --onedir --name ReportMakerV2 --specpath $specDir `
        --hidden-import PySide6.QtWebEngineWidgets `
        --hidden-import PySide6.QtWebEngineCore `
        --hidden-import PySide6.QtWebChannel `
        --hidden-import PySide6.QtSvg `
        --exclude-module reportmaker.__main__ `
        --exclude-module reportmaker.ui `
        --exclude-module reportmaker.visual_editor `
        --exclude-module reportmaker.page_editor `
        --exclude-module reportmaker.rich_editor `
        --exclude-module reportmaker.template_dialog `
        --exclude-module reportmaker.customer_ui `
        --exclude-module reportmaker.customer_probe `
        --exclude-module reportmaker.editor_probe `
        --exclude-module reportmaker.export_probe `
        --exclude-module reportmaker.layout_probe `
        --collect-all pillow_heif `
        --collect-data reportmaker `
        packaging/windows/v2_launcher.py
    if ($LASTEXITCODE -ne 0) { throw "V2 freezing failed" }
    $frozen = Join-Path $root "dist\ReportMakerV2"
    $frozenExe = Join-Path $frozen "ReportMakerV2.exe"
    if (-not (Test-Path $frozenExe)) { throw "Frozen V2 executable missing" }
    & $python scripts/verify_v2_frozen_archive.py $frozenExe
    if ($LASTEXITCODE -ne 0) { throw "V2-only frozen archive check failed" }
    $smoke = Start-Process -FilePath $frozenExe -ArgumentList "--offline-self-test" -WindowStyle Hidden -Wait -PassThru
    if ($smoke.ExitCode -ne 0) { throw "Frozen native V2 offline test failed" }
    $smoke = Start-Process -FilePath $frozenExe -ArgumentList @("--html", "--offline-self-test") -WindowStyle Hidden -Wait -PassThru
    if ($smoke.ExitCode -ne 0) { throw "Frozen HTML V2 offline test failed" }
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue

    if (-not $IsccPath) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
        )
        $IsccPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $IsccPath -or -not (Test-Path $IsccPath)) {
        throw "Install Inno Setup 6 locally or provide -IsccPath; the script never installs tools silently"
    }
    & $IsccPath "/DSourceRoot=$root" "/DOutputRoot=$output" "packaging/windows/ReportMaker-V2-M7.iss"
    if ($LASTEXITCODE -ne 0) { throw "Local isolated V2 installer build failed" }
    $setup = Join-Path $output "ReportMaker-V2-M7-Preview-Setup.exe"
    if (-not (Test-Path $setup)) { throw "Preview installer missing" }

    $manifest = [ordered]@{
        scope = "M7.3 local-only Windows preview; not native UI acceptance"
        source_sha = $sourceSha
        installer_sha256 = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
        frozen_exe_sha256 = (Get-FileHash -LiteralPath $frozenExe -Algorithm SHA256).Hash.ToLowerInvariant()
        installed_exe_sha256 = $null
    }
    if ($Install) {
        $target = [IO.Path]::GetFullPath($InstallDirectory)
        if (Test-Path $target) { throw "Target already exists; choose an unused private M7.3 install directory" }
        if ($target.StartsWith($root + [IO.Path]::DirectorySeparatorChar,
                                [StringComparison]::OrdinalIgnoreCase)) {
            throw "Do not install into the Git working tree"
        }
        $args = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$target`"")
        $installResult = Start-Process -FilePath $setup -ArgumentList $args -Wait -PassThru
        if ($installResult.ExitCode -ne 0) { throw "Isolated V2 preview installation failed" }
        $installedExe = Join-Path $target "ReportMakerV2.exe"
        if (-not (Test-Path $installedExe)) { throw "Installed V2 executable missing" }
        # Compare every payload file as in hosted CI, not just the launcher.
        $files = @(Get-ChildItem -LiteralPath $frozen -Recurse -File)
        if ($files.Count -lt 2) { throw "Missing frozen dependency payload" }
        foreach ($file in $files) {
            $relative = $file.FullName.Substring($frozen.Length + 1)
            $installedFile = Join-Path $target $relative
            if (-not (Test-Path -LiteralPath $installedFile -PathType Leaf) -or
                (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne
                (Get-FileHash -LiteralPath $installedFile -Algorithm SHA256).Hash) {
                throw "Installed V2 payload mismatch: $relative"
            }
        }
        $env:QT_QPA_PLATFORM = "offscreen"
        $installedSmoke = Start-Process -FilePath $installedExe -ArgumentList "--offline-self-test" -WindowStyle Hidden -Wait -PassThru
        if ($installedSmoke.ExitCode -ne 0) { throw "Installed native V2 offline smoke failed" }
        $installedSmoke = Start-Process -FilePath $installedExe -ArgumentList @("--html", "--offline-self-test") -WindowStyle Hidden -Wait -PassThru
        Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
        if ($installedSmoke.ExitCode -ne 0) { throw "Installed HTML V2 offline smoke failed" }
        $manifest.installed_exe_sha256 = (Get-FileHash -LiteralPath $installedExe -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Host "Installed isolated V2 test candidate: $installedExe"
    }
    $file = Join-Path $output "m73-local-build.json"
    $manifest | ConvertTo-Json | Set-Content -LiteralPath $file -Encoding utf8
    Write-Host "Local installer: $setup"
    Write-Host "Exact source SHA: $sourceSha"
    Write-Host "Local manifest: $file"
    Write-Host "No installer was published and no native RM-BE case was accepted."
}
finally {
    Pop-Location
}
