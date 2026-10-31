; M7.1 local-only V2 preview installer. Built and tested on hosted Windows CI.
; It has a distinct AppId and path, never upgrades/removes the existing V1 app.
#ifndef SourceRoot
  #error V2 M7 installer requires /DSourceRoot=<absolute checked-out source>
#endif
#ifndef OutputRoot
  #error V2 M7 installer requires /DOutputRoot=<absolute output folder>
#endif

#define MyAppName "ReportMaker V2 Preview"
#define MyAppVersion "0.7.0-m7.1"
#define MyAppExeName "ReportMakerV2.exe"

[Setup]
AppId={{7E079D45-D689-46C4-9E56-E2C4DDE89312}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=ReportMaker
DefaultDirName={localappdata}\Programs\ReportMaker V2 Preview
DefaultGroupName=ReportMaker V2 Preview
PrivilegesRequired=lowest
OutputDir={#OutputRoot}
OutputBaseFilename=ReportMaker-V2-M7-Preview-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
MinVersion=10.0.17763

[Tasks]
Name: "desktopicon"; Description: "Create V2 preview desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\dist\ReportMakerV2\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs notimestamp

[Icons]
Name: "{autoprograms}\ReportMaker V2 Preview"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\ReportMaker V2 Preview"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch ReportMaker V2 Preview"; Flags: nowait postinstall skipifsilent
