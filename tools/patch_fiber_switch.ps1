# patch_fiber_switch.ps1 - Patch sub_82701240 in generated code to bypass
# the fiber-switch callback check and always take the normal context-save path.
#
# sub_82701240 checks a function pointer at guest 0x82B101E4. If non-zero,
# it calls that function and returns without saving context. The game sets
# this to a no-op blr stub (0x821EA208) during initialization, which breaks
# the save system (the caller sees a non-zero r3 and aborts).
#
# This patch forces cr0.eq=true after the cmpwi, so the bnectr is never
# taken and the normal context-save path runs, which correctly sets r3=0.
#
# Run after codegen, before compilation.

param(
    [string]$GeneratedDir = "generated\default"
)

$files = Get-ChildItem -Path $GeneratedDir -Filter "dantes_inferno_recomp.*.cpp" -ErrorAction SilentlyContinue
$patched = $false

foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw
    if ($content -match "DEFINE_REX_FUNC\(sub_82701240\)\s*\{") {
        if ($content -match "PATCHED: Skip the fiber-switch") {
            Write-Output "patch_fiber_switch: $($file.Name) already patched"
            $patched = $true
            break
        }
        # Insert the patch: force cr0.eq=true after the cmpwi
        $patched_content = $content -replace "(// cmpwi r0,0\s*\r?\n\s*ctx\.cr0\.compare<int32_t>\(ctx\.r0\.s32, 0, ctx\.xer\);)", "`$1`n`t// PATCHED: Force eq so bnectr is not taken`n`tctx.cr0.eq = true;"
        Set-Content -Path $file.FullName -Value $patched_content -NoNewline
        Write-Output "patch_fiber_switch: Patched $($file.Name)"
        $patched = $true
        break
    }
}

if (-not $patched) {
    Write-Output "patch_fiber_switch: WARNING - sub_82701240 not found in any generated file"
}
