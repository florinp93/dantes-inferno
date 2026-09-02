param(
    [string]$GameBuildDir = "..\out\build\win-amd64-release",
    [string]$Configuration = "Release",
    [string]$OutputDir = "..\launcher-release"
)

$ErrorActionPreference = "Stop"

$msbuild = "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe"
if (-not (Test-Path $msbuild)) {
    Write-Error "MSBuild not found. Install Visual Studio 2022 Community or update the path."
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$GameBuildDir = (Join-Path $root $GameBuildDir | Resolve-Path -ErrorAction Stop).Path
$OutputDir = [System.IO.Path]::GetFullPath((Join-Path $root $OutputDir))

Write-Host "Building C# solution..."
& $msbuild (Join-Path $root "DantesInferno.sln") /p:Configuration=$Configuration /p:Platform=AnyCPU /v:minimal
if ($LASTEXITCODE -ne 0) { throw "C# build failed." }

$releaseDir = Join-Path $OutputDir "DantesInferno"
$distDir = Join-Path $releaseDir "dist"

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
New-Item -ItemType Directory -Path $distDir -Force | Out-Null
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

Write-Host "Copying game binaries from $GameBuildDir ..."
$gameFiles = @("dantes_inferno.exe", "rexruntime.dll", "rexgpu-xenos.dll")
foreach ($f in $gameFiles) {
    $src = Join-Path $GameBuildDir $f
    if (Test-Path $src) {
        Copy-Item $src $distDir -Force
        Write-Host "  -> $f"
    } else {
        Write-Warning "Missing expected file: $src"
    }
}

Write-Host "Copying launcher files..."
$launcherBin = Join-Path $root "DantesInfernoLauncher\bin\$Configuration"
Copy-Item (Join-Path $launcherBin "DantesInfernoLauncher.exe") $distDir -Force
Copy-Item (Join-Path $launcherBin "DantesInferno.Shared.dll") $distDir -Force
Copy-Item (Join-Path $launcherBin "version.txt") $distDir -Force

$installerBin = Join-Path $root "DantesInfernoInstaller\bin\$Configuration"

Write-Host "Copying installer files..."
Copy-Item (Join-Path $installerBin "DantesInfernoInstaller.exe") $releaseDir -Force
Copy-Item (Join-Path $installerBin "DantesInferno.Shared.dll") $releaseDir -Force
Copy-Item (Join-Path $installerBin "extract-xiso.exe") $releaseDir -Force

Copy-Item (Join-Path $root "icon.ico") $distDir -Force
Copy-Item (Join-Path $root "icon.png") $distDir -Force

$zipPath = Join-Path $OutputDir "DantesInferno-Release.zip"
Compress-Archive -Path "$releaseDir\*" -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Release package created at: $OutputDir"
Write-Host "  - Installer: $releaseDir\DantesInfernoInstaller.exe"
Write-Host "  - Zip:       $zipPath"
