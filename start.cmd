@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
pushd "%ROOT%"

REM ---------- locate qemu-system-x86_64 ----------
set "QEMU="
for /f "delims=" %%i in ('where qemu-system-x86_64 2^>nul') do (
    set "QEMU=%%i"
    goto :got_qemu
)
if exist "C:\QEMU\QEMU\qemu-system-x86_64.exe" set "QEMU=C:\QEMU\QEMU\qemu-system-x86_64.exe"

:got_qemu
if not defined QEMU (
    echo qemu-system-x86_64 not found.
    popd
    exit /b 1
)

REM ---------- disk image ----------
set "IMAGE=%ROOT%dist\WCT-OS-LTS-1.0.img"
if not exist "%IMAGE%" (
    echo WCT-OS image not found.
    popd
    exit /b 1
)

REM ---------- OVMF firmware (in <qemu-dir>\share\) ----------
for %%i in ("%QEMU%") do set "QEMUDIR=%%~dpi"
if "%QEMUDIR:~-1%"=="\" set "QEMUDIR=%QEMUDIR:~0,-1%"
set "SHARE=%QEMUDIR%\share"
set "CODE=%SHARE%\edk2-x86_64-code.fd"
set "VARS=%SHARE%\edk2-i386-vars.fd"
if not exist "%CODE%" (
    echo OVMF firmware not found next to QEMU.
    popd
    exit /b 1
)
if not exist "%VARS%" (
    echo OVMF firmware not found next to QEMU.
    popd
    exit /b 1
)

REM ---------- prepare vars copy ----------
if not exist "%ROOT%build" mkdir "%ROOT%build"
copy /Y "%VARS%" "%ROOT%build\OVMF_VARS.fd" >nul

echo WCT-OS LTS 1.0  //  UEFI boot via OVMF
echo Image: %IMAGE%
echo At the console: python / nano / cn / ls /fat
echo Close the QEMU window to power off.
echo.

REM ---------- run ----------
"%QEMU%" ^
    -name "WCT-OS LTS 1.0" ^
    -machine q35 ^
    -m 1536 ^
    -smp 2 ^
    -drive "if=pflash,format=raw,readonly=on,file=%CODE%" ^
    -drive "if=pflash,format=raw,file=%ROOT%build\OVMF_VARS.fd" ^
    -drive "file=%IMAGE%,format=raw,if=ide" ^
    -device VGA ^
    -device qemu-xhci,id=xhci ^
    -device usb-tablet,bus=xhci.0 ^
    -display gtk ^
    -serial none

popd
endlocal