#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$qemu = (Get-Command qemu-system-x86_64 -ErrorAction SilentlyContinue).Source
if (-not $qemu -and (Test-Path "C:\QEMU\QEMU\qemu-system-x86_64.exe")) {
    $qemu = "C:\QEMU\QEMU\qemu-system-x86_64.exe"
}
if (-not $qemu) { throw "qemu-system-x86_64 not found." }

$image = Join-Path $Root "dist\WCT-OS-LTS-1.0.img"
if (-not (Test-Path $image)) { throw "WCT-OS image not found." }

$share = Join-Path (Split-Path $qemu) "share"
$code = Join-Path $share "edk2-x86_64-code.fd"
$vars = Join-Path $share "edk2-i386-vars.fd"
if (-not (Test-Path $code) -or -not (Test-Path $vars)) {
    throw "OVMF firmware not found next to QEMU."
}

New-Item -ItemType Directory -Force -Path build | Out-Null
Copy-Item $vars build\OVMF_VARS.fd -Force

Write-Host "WCT-OS LTS 1.0  //  UEFI boot via OVMF"
Write-Host "Image: $image"
Write-Host "At the console: python / nano / cn / ls /fat"
Write-Host "Close the QEMU window to power off."
Write-Host ""

& $qemu `
    -name "WCT-OS LTS 1.0" `
    -machine q35 `
    -m 1536 `
    -smp 2 `
    -drive "if=pflash,format=raw,readonly=on,file=$code" `
    -drive "if=pflash,format=raw,file=$Root\build\OVMF_VARS.fd" `
    -drive "file=$image,format=raw,if=ide" `
    -device VGA `
    -device qemu-xhci,id=xhci ^
    -device usb-tablet,bus=xhci.0 ^
    -display gtk `
    -serial none
