; ReportMaker RC2 -- distinct from immutable historical M0 publisher.
; The CI invokes ISCC with /DSourceRoot and /DOutputRoot so the
; frozen application comes from a separately verified, pinned source checkout.
#ifndef SourceRoot
  #error RC2 requires /DSourceRoot=<absolute pinned source path>
#endif
#ifndef OutputRoot
  #error RC2 requires /DOutputRoot=<absolute output path>
#endif

#define MyAppName "ReportMaker"
#define MyAppVersion "0.5.0-rc.2"
#define MyAppExeName "ReportMaker.exe"

[Setup]
; Reuse ReportMaker's original per-user AppId for a supported upgrade path.
AppId={{24EFAC39-A017-405C-BEE1-EA15E90F8CE0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion=0.5.0.2
AppPublisher=ReportMaker
DefaultDirName={localappdata}\Programs\ReportMaker
DefaultGroupName=ReportMaker
PrivilegesRequired=lowest
OutputDir={#OutputRoot}
OutputBaseFilename=ReportMaker-0.5.0-rc.2-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
MinVersion=10.0.17763

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\dist\ReportMaker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ReportMaker"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\ReportMaker"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch ReportMaker"; Flags: nowait postinstall skipifsilent
