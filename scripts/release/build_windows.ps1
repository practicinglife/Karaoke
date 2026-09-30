Param(
	[string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

Write-Host "[release] Building Windows executable..."
& .\build.bat

if (!(Test-Path ".\dist\KaraokeTicker.exe")) {
	throw "KaraokeTicker.exe was not produced."
}

$innoCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (!(Test-Path $innoCompiler)) {
	Write-Warning "Inno Setup compiler not found at '$innoCompiler'. Skipping setup build."
	exit 0
}

Write-Host "[release] Building Windows installer..."
& $innoCompiler "/DAppVersion=$Version" ".\packaging\windows\KaraokeTickerSetup.iss"

if (!(Test-Path ".\dist\KaraokeTickerSetup.exe")) {
	throw "KaraokeTickerSetup.exe was not produced."
}

Write-Host "[release] Windows artifacts ready in .\dist"
