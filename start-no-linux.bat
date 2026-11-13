@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "IMAGE=%ROOT%no-linux\WCT-OS-Native-Only-1.0.img"
set "QEMU=C:\QEMU\QEMU\qemu-system-x86_64.exe"

if not exist "%QEMU%" (
    for /f "delims=" %%I in ('where qemu-system-x86_64.exe 2^>nul') do set "QEMU=%%I"
)

if not exist "%QEMU%" (
    echo.
    echo qemu-system-x86_64.exe not found.
    echo Install QEMU or put it at C:\QEMU\QEMU\.
    echo.
    pause
    exit /b 1
)

if not exist "%IMAGE%" (
    echo.
    echo Image not found:
    echo   %IMAGE%
    echo.
    pause
    exit /b 1
)

for %%I in ("%QEMU%") do set "SHARE=%%~dpIshare"
if not exist "%SHARE%\edk2-x86_64-code.fd" set "SHARE=C:\QEMU\QEMU\share"

set "CODE=%SHARE%\edk2-x86_64-code.fd"
set "VARS=%SHARE%\edk2-i386-vars.fd"
if not exist "%CODE%" (
    echo OVMF code not found: %CODE%
    pause
    exit /b 1
)
if not exist "%VARS%" (
    echo OVMF vars not found: %VARS%
    pause
    exit /b 1
)

if not exist "%ROOT%build" mkdir "%ROOT%build"
copy /y "%VARS%" "%ROOT%build\OVMF_VARS_NO_LINUX.fd" >nul

echo.
echo WCT-OS Native Only 1.0  //  UEFI boot via OVMF
echo Image: %IMAGE%
echo This build has no Linux subsystem.
echo Close the QEMU window to power off.
echo.

"%QEMU%" ^
    -name "WCT-OS Native Only 1.0" ^
    -machine q35 ^
    -m 1024 ^
    -smp 2 ^
    -drive "if=pflash,format=raw,readonly=on,file=%CODE%" ^
    -drive "if=pflash,format=raw,file=%ROOT%build\OVMF_VARS_NO_LINUX.fd" ^
    -drive "file=%IMAGE%,format=raw,if=ide" ^
    -device VGA ^
    -display gtk ^
    -serial none

if errorlevel 1 pause
endlocal