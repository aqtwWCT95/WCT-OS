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

New-Item -ItemType Directory -Force -Path linux\packages, linux\kernel, linux\esp\EFI\BOOT, linux\esp\loader\entries, linux\esp\wct, dist | Out-Null

$packages = "linux\packages\Packages"
$packagesGz = "linux\packages\Packages.gz"
if (-not (Test-Path $packages)) {
    if (-not (Test-Path $packagesGz)) {
        Write-Host "Downloading Debian package index..."
        & curl.exe -L --fail --max-time 120 -o $packagesGz "http://deb.debian.org/debian/dists/bookworm/main/binary-amd64/Packages.gz"
        if ($LASTEXITCODE -ne 0) { throw "package index download failed" }
    }
    & $python @pyArgs -c "import gzip; open(r'linux/packages/Packages','w',encoding='utf-8').write(gzip.open(r'linux/packages/Packages.gz','rt',encoding='utf-8',errors='replace').read())"
    if ($LASTEXITCODE -ne 0) { throw "package index extraction failed" }
}

Write-Host "Fetching Debian root filesystem..."
& $python @pyArgs linux\fetch_rootfs.py
if ($LASTEXITCODE -ne 0) { throw "rootfs fetch failed" }

Write-Host "Trimming kernel modules..."
& $python @pyArgs linux\trim_modules.py
if ($LASTEXITCODE -ne 0) { throw "module trim failed" }

Write-Host "Configuring WCT-OS..."
& $python @pyArgs linux\prepare_rootfs.py
if ($LASTEXITCODE -ne 0) { throw "rootfs configuration failed" }

Write-Host "Building initramfs..."
& $python @pyArgs linux\make_initramfs.py
if ($LASTEXITCODE -ne 0) { throw "initramfs build failed" }

$gcc = (Get-Command gcc -ErrorAction SilentlyContinue).Source
if (-not $gcc -and (Test-Path "C:\mingw64\bin\gcc.exe")) { $gcc = "C:\mingw64\bin\gcc.exe" }
if (-not $gcc) { throw "MinGW-w64 gcc not found (needed for native.efi)." }

Write-Host "Building native C shell..."
New-Item -ItemType Directory -Force -Path native\build | Out-Null
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

Copy-Item linux\kernel\vmlinuz linux\esp\wct\vmlinuz -Force
Copy-Item linux\initrd.img linux\esp\wct\initrd.img -Force
Copy-Item linux\rootfs\usr\lib\systemd\boot\efi\systemd-bootx64.efi linux\esp\wct\bootx64.efi -Force
Copy-Item native\build\native.efi linux\esp\EFI\BOOT\BOOTX64.EFI -Force
Remove-Item linux\esp\loader\entries\native.conf -Force -ErrorAction SilentlyContinue

$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText((Join-Path $Root "linux\esp\loader\loader.conf"), "default wct`ntimeout 0`neditor 0`n", $utf8)
[IO.File]::WriteAllText((Join-Path $Root "linux\esp\loader\entries\wct.conf"),
    "title WCT-OS Linux (CPython / nano)`nlinux /wct/vmlinuz`ninitrd /wct/initrd.img`noptions console=tty0 rdinit=/init loglevel=3`n", $utf8)

Write-Host "Building GPT + FAT32 image..."
& $python @pyArgs linux\make_wct_image.py
if ($LASTEXITCODE -ne 0) { throw "image build failed" }

Write-Host ""
Write-Host "Built: dist\WCT-OS-LTS-1.0.img"
Get-Item dist\WCT-OS-LTS-1.0.img | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
