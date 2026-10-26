#define MyAppName "ReportMaker"
#define MyAppVersion "0.0.1"
#define MyAppExeName "ReportMaker.exe"

[Setup]
AppId={{24EFAC39-A017-405C-BEE1-EA15E90F8CE0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=ReportMaker
DefaultDirName={localappdata}\Programs\ReportMaker
DefaultGroupName=ReportMaker
PrivilegesRequired=lowest
OutputDir=..\..\dist-installer
OutputBaseFilename=ReportMaker-M0-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
MinVersion=10.0.17763

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\ReportMaker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ReportMaker"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\ReportMaker"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch ReportMaker"; Flags: nowait postinstall skipifsilent
