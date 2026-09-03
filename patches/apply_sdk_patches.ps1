# apply_sdk_patches.ps1
#
# Applies local patches to the ReXGlue SDK after it has been cloned by setup.ps1.
#
# Patches included:
#   - VMX builder fixes (vmsum3fp128 mask, pack aliasing) - physics/FMV fix
#   - manifest.cpp midasm_hook fix - top-level [[midasm_hook]] now works
#   - gpu_3d_to_2d_texture default disabled - prevents crash at >1x resolution
#   - XUserFindUsers handler - prevents save load null-pointer crash
#   - XMA decoder thread fix - prevents audio init hang
#   - Content/save API logging
#   - D3D12 graphics patches (ROV, presenter, texture cache, etc.)
#   - Function dispatcher unresolved-call behavior

param(
    [string]$SdkDir = "thirdparty\rexglue-sdk"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$sdkPath = Join-Path $projectRoot $SdkDir
$patchFile = Join-Path $PSScriptRoot "sdk\rexglue-sdk-v0.10.0.patch"

if (-not (Test-Path $sdkPath)) {
    Write-Error "SDK directory not found: $sdkPath"
    Write-Error "Run setup.ps1 first to clone the SDK."
    exit 1
}

if (-not (Test-Path $patchFile)) {
    Write-Error "Patch file not found: $patchFile"
    exit 1
}

# Apply the patch using git apply within the SDK repo
Write-Host "Applying SDK patches to $sdkPath ..."
Push-Location $sdkPath
try {
    # Check if patches are already applied by testing reverse application
    $reverseCheck = & git apply --reverse --check $patchFile 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "SDK patches already applied."
        Pop-Location
        exit 0
    }

    # Try forward application
    $forwardCheck = & git apply --check $patchFile 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Attempting to apply with --3way..."
        $applyResult = & git apply --3way $patchFile 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to apply SDK patches: $applyResult"
            Pop-Location
            exit 1
        }
    } else {
        $applyResult = & git apply $patchFile 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to apply SDK patches: $applyResult"
            Pop-Location
            exit 1
        }
    }
    Write-Host "SDK patches applied successfully."
}
finally {
    Pop-Location
}
