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
SetupIconFile=..\assets\icon.ico
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\ShirStudio.exe

ShowLanguageDialog=yes
UsePreviousLanguage=no

[Languages]
; ההתקנה מוצגת בעברית או באנגלית (ל-Inno Setup אין תרגום ליידיש; את שפת התוכנה עצמה בוחרים בהפעלה הראשונה)
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
hebrew.DesktopIcon=צור סמל על שולחן העבודה
english.DesktopIcon=Create a desktop icon
hebrew.OpenNow=פתח את התוכנה עכשיו
english.OpenNow=Open Shir Studio now

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: checkedonce

[Files]
Source: "..\dist\ShirStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\ShirStudio.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\ShirStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ShirStudio.exe"; Description: "{cm:OpenNow}"; Flags: nowait postinstall skipifsilent
; עדכון מתוך התוכנה (התקנה שקטה): התוכנה נפתחת מחדש בסיום
Filename: "{app}\ShirStudio.exe"; Flags: nowait; Check: WizardSilent
