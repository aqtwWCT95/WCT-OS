#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$python = $null
$pyArgs = @()
$bundled = "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (Test-Path $bundled) {
    $python = $bundled
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        $py = (Get-Command py -ErrorAction SilentlyContinue).Source
        if ($py) { $python = $py; $pyArgs = @("-3") }
    }
}
if (-not $python) { throw "Python 3 not found." }

$gcc = (Get-Command gcc -ErrorAction SilentlyContinue).Source
if (-not $gcc -and (Test-Path "C:\mingw64\bin\gcc.exe")) { $gcc = "C:\mingw64\bin\gcc.exe" }
if (-not $gcc) { throw "MinGW-w64 gcc not found." }

$stage = Join-Path $Root "build\native-only-esp"
$outDir = Join-Path $Root "no-linux"
$out = Join-Path $outDir "WCT-OS-Native-Only-1.0.img"

if (-not (Test-Path "linux\esp")) { throw "linux\esp not found." }
New-Item -ItemType Directory -Force -Path build, native\build, $outDir | Out-Null
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
Copy-Item linux\esp $stage -Recurse -Force
Remove-Item (Join-Path $stage "wct") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $stage "loader") -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $stage "EFI\BOOT") | Out-Null

Write-Host "Building native UEFI shell..."
& $gcc -ffreestanding -fno-stack-protector -fno-builtin -mno-red-zone -O2 `
    -Inative -c native\main.c -o native\build\main.o
if ($LASTEXITCODE -ne 0) { throw "native compile failed" }
$nativeLink = @(
    "-nostdlib", "-Wl,--subsystem,10", "-Wl,-e,efi_main",
    "-Wl,--image-base,0x10000000", "-Wl,--enable-reloc-section",
    "-Wl,--gc-sections", "-o", "native/build/native.efi",
    "native/build/main.o", "-lgcc"
)
& $gcc @nativeLink
if ($LASTEXITCODE -ne 0) { throw "native link failed" }

Copy-Item native\build\native.efi (Join-Path $stage "EFI\BOOT\BOOTX64.EFI") -Force

Write-Host "Building 64 MiB Native Only image..."
& $python @pyArgs linux\make_wct_image.py $stage $out 64
if ($LASTEXITCODE -ne 0) { throw "native-only image build failed" }

Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Built: no-linux\WCT-OS-Native-Only-1.0.img"
Get-Item $out | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
