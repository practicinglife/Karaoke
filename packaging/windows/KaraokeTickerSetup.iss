#define AppName "Karaoke Ticker"
#ifndef AppVersion
#define AppVersion "1.0.0"
#endif
#define AppExeName "KaraokeTicker.exe"

[Setup]
AppId={{A3C21B30-17A4-4FA0-BD4B-5C6C16C4B0E0}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Karaoke Ticker
DefaultDirName={autopf}\Karaoke Ticker
DefaultGroupName=Karaoke Ticker
OutputDir=dist
OutputBaseFilename=KaraokeTickerSetup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern

[Files]
Source: "dist\KaraokeTicker.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Karaoke Ticker"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Karaoke Ticker"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Karaoke Ticker"; Flags: nowait postinstall skipifsilent
