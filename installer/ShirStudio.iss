#define MyAppName "שיר סטודיו"
#define MyAppVersion GetEnv("APP_VERSION")

[Setup]
AppId={{6E1B7C2A-4F3D-4B8E-9A51-5C2D7F0E9B13}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Shir Studio
DefaultDirName={autopf}\ShirStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=ShirStudio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\ShirStudio.exe

[Languages]
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"

[Tasks]
Name: "desktopicon"; Description: "צור סמל על שולחן העבודה"; Flags: checkedonce

[Files]
Source: "..\dist\ShirStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\ShirStudio.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\ShirStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ShirStudio.exe"; Description: "פתח את {#MyAppName} עכשיו"; Flags: nowait postinstall skipifsilent
