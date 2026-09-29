#define AppName "PORTAL-XLINK"
#define AppVersion "1.0.0"
#define AppPublisher "Adarsh"
#define AppExeName "PORTAL-XLINK.exe"

[Setup]
AppId={{8C349C90-1F61-46FA-9D69-DFD65DD5EE23}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=PORTAL-XLINK-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}

[Files]
Source: "..\..\dist\PORTAL-XLINK\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "--backend remote"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "--backend remote"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#AppExeName}"; Parameters: "--backend remote"; Description: "Launch {#AppName}"; Flags: postinstall nowait skipifsilent
