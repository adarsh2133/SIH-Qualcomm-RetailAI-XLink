$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $projectRoot

$buildPython = Join-Path $projectRoot ".venv-build\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $buildPython)) {
    python -m venv (Join-Path $projectRoot ".venv-build")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the isolated Windows build environment."
    }
}

& $buildPython -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the desktop build dependencies."
}

& $buildPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name PORTAL-XLINK `
    --collect-all customtkinter `
    --collect-all PIL `
    --hidden-import PIL.Image `
    app.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed to build the Windows desktop application."
}

$compilerCandidates = @()
if (${env:ProgramFiles(x86)}) {
    $compilerCandidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
}
if ($env:ProgramFiles) {
    $compilerCandidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
}
if ($env:LOCALAPPDATA) {
    $compilerCandidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
}
$compiler = $compilerCandidates |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
if (-not $compiler) {
    throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php"
}

& $compiler (Join-Path $PSScriptRoot "portal-xlink.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed to create the installer."
}

Write-Output "Installer ready: $projectRoot\dist\PORTAL-XLINK-Setup.exe"
