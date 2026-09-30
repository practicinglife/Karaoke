Param(
	[string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $repoRoot
try {
	if (!(Test-Path ".\data")) {
		New-Item -ItemType Directory -Path ".\data" | Out-Null
	}

	Write-Host "[release] Building Windows executable..."
	& .\build.bat
	if ($LASTEXITCODE -ne 0) {
		throw "build.bat failed with exit code $LASTEXITCODE."
	}

	if (!(Test-Path ".\dist\KaraokeTicker.exe")) {
		throw "KaraokeTicker.exe was not produced."
	}

$innoCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (!(Test-Path $innoCompiler)) {
	Write-Warning "Inno Setup compiler not found at '$innoCompiler'. Skipping setup build."
	return
}

Write-Host "[release] Building Windows installer..."
& $innoCompiler "/DAppVersion=$Version" ".\packaging\windows\KaraokeTickerSetup.iss"

if (!(Test-Path ".\dist\KaraokeTickerSetup.exe")) {
	throw "KaraokeTickerSetup.exe was not produced."
}

Write-Host "[release] Windows artifacts ready in .\dist"
}
finally {
	Pop-Location
}
