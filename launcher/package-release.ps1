param(
    [string]$GameBuildDir = "..\out\build\win-amd64-release",
    [string]$Configuration = "Release",
    [string]$OutputDir = "..\alpha-release"
)

$ErrorActionPreference = "Stop"

$msbuild = "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe"
if (-not (Test-Path $msbuild)) {
    Write-Error "MSBuild not found. Install Visual Studio 2022 Community or update the path."
}

$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    Write-Error "Inno Setup 6 not found at $iscc. Install it via winget: winget install JRSoftware.InnoSetup"
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$GameBuildDir = (Join-Path $root $GameBuildDir | Resolve-Path -ErrorAction Stop).Path
$OutputDir = [System.IO.Path]::GetFullPath((Join-Path $root $OutputDir))

$gameFiles = @("dantes_inferno.exe", "rexruntime.dll", "rexgpu-xenos.dll")
foreach ($f in $gameFiles) {
    $src = Join-Path $GameBuildDir $f
    if (-not (Test-Path $src)) {
        Write-Error "Missing game binary: $src"
    }
}

$extractXiso = Join-Path $root "..\tools\extract-xiso\extract-xiso.exe"
if (-not (Test-Path $extractXiso)) {
    Write-Error "Missing extract-xiso.exe at $extractXiso"
}

Write-Host "Building C# solution..."
& $msbuild (Join-Path $root "DantesInferno.sln") /p:Configuration=$Configuration /p:Platform=AnyCPU /v:minimal
if ($LASTEXITCODE -ne 0) { throw "C# build failed." }

$versionFile = Join-Path $root "DantesInfernoLauncher\bin\$Configuration\version.txt"
if (-not (Test-Path $versionFile)) {
    Write-Warning "version.txt not found in launcher bin - creating default."
    Set-Content $versionFile "0.0.0" -Encoding UTF8
}

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Write-Host "Compiling Inno Setup installer..."
& $iscc (Join-Path $root "installer.iss") 2>&1
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }

Write-Host ""
Write-Host "Installer created at: $OutputDir\DantesInfernoInstaller.exe"
$installerExe = Join-Path $OutputDir "DantesInfernoInstaller.exe"
if (Test-Path $installerExe) {
    $size = (Get-Item $installerExe).Length
    $sizeMB = [math]::Round($size / 1048576, 2)
    Write-Host "Size: $sizeMB MB"
}
