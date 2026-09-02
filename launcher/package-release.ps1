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

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$GameBuildDir = (Join-Path $root $GameBuildDir | Resolve-Path -ErrorAction Stop).Path
$OutputDir = [System.IO.Path]::GetFullPath((Join-Path $root $OutputDir))

Write-Host "Building C# solution..."
& $msbuild (Join-Path $root "DantesInferno.sln") /p:Configuration=$Configuration /p:Platform=AnyCPU /v:minimal
if ($LASTEXITCODE -ne 0) { throw "C# build failed." }

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$payloadDir = Join-Path $OutputDir "payload"
$distDir = Join-Path $payloadDir "dist"
New-Item -ItemType Directory -Path $distDir -Force | Out-Null

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
Copy-Item (Join-Path $root "icon.ico") $distDir -Force
Copy-Item (Join-Path $root "banner.jpg") $distDir -Force
Copy-Item (Join-Path $root "icon.ico") (Join-Path $OutputDir "icon.ico") -Force

Write-Host "Copying uninstaller..."
$uninstallerBin = Join-Path $root "DantesInfernoUninstaller\bin\$Configuration"
Copy-Item (Join-Path $uninstallerBin "uninstall.exe") $distDir -Force

$installerBin = Join-Path $root "DantesInfernoInstaller\bin\$Configuration"
$installerExe = Join-Path $OutputDir "DantesInfernoInstaller.exe"
Copy-Item (Join-Path $installerBin "DantesInfernoInstaller.exe") $installerExe -Force

Write-Host "Copying ISO extraction tool..."
Copy-Item (Join-Path $root "..\tools\extract-xiso\extract-xiso.exe") $payloadDir -Force

$payloadFile = Join-Path $OutputDir "payload.bin"

function New-PayloadArchive($sourceDir, $outFile) {
    $stream = [System.IO.FileStream]::new($outFile, [System.IO.FileMode]::Create)
    $writer = [System.IO.BinaryWriter]::new($stream, [System.Text.Encoding]::UTF8)
    $files = Get-ChildItem -Path $sourceDir -Recurse -File
    $writer.Write([int]$files.Count)
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($sourceDir.Length + 1)
        $pathBytes = [System.Text.Encoding]::UTF8.GetBytes($relative)
        $writer.Write([int]$pathBytes.Length)
        $writer.Write($pathBytes)
        $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
        $writer.Write([long]$bytes.Length)
        $writer.Write($bytes)
    }
    $writer.Flush()
    $writer.Dispose()
}

function Append-Payload($exe, $archive) {
    $exeBytes = [System.IO.File]::ReadAllBytes($exe)
    $archiveBytes = [System.IO.File]::ReadAllBytes($archive)
    $marker = [System.Text.Encoding]::ASCII.GetBytes("DANTES_PAYLOAD")
    $lengthBytes = [System.BitConverter]::GetBytes([long]$archiveBytes.Length)
    $ms = [System.IO.MemoryStream]::new()
    $ms.Write($exeBytes, 0, $exeBytes.Length)
    $ms.Write($archiveBytes, 0, $archiveBytes.Length)
    $ms.Write($lengthBytes, 0, $lengthBytes.Length)
    $ms.Write($marker, 0, $marker.Length)
    [System.IO.File]::WriteAllBytes($exe, $ms.ToArray())
    $ms.Dispose()
}

Write-Host "Creating payload archive..."
New-PayloadArchive $payloadDir $payloadFile

Write-Host "Appending payload to installer..."
Append-Payload $installerExe $payloadFile

Remove-Item $payloadDir -Recurse -Force
Remove-Item $payloadFile -Force

Write-Host ""
Write-Host "Standalone installer created at: $installerExe"
