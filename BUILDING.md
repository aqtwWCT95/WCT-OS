# WCT-OS LTS 1.0 — 源码构建指南 (Source Only)

This folder contains source and build configuration only.
No compiled EFI, kernel, initramfs, rootfs or disk image is included.

## 📂 目录结构 (Layout)
- `native/` : 自研的纯 C UEFI 原生终端 (efi.h, main.c)
- `linux/` : Linux 子系统构建脚本 (fetch_rootfs.py 等)
- `build.ps1` / `build.cmd` : 完整构建脚本 (原生 + Linux + 镜像)
- `run.ps1` / `start.cmd` : QEMU 启动脚本

## 🛠️ 编译环境 (Build requirements)
- Windows PowerShell 5.1+
- MinGW-w64 GCC (确保在环境变量 PATH 中，或放在 `C:\mingw64\bin\gcc.exe`)
- Python 3
- curl.exe
- 能够访问 Debian 软件源 (`http://deb.debian.org/debian/`)

## 📦 构建 (Build)
执行 `build.cmd` 或运行 `build.ps1`。

该脚本会自动下载 Debian 软件包、裁剪并生成 rootfs 和 initramfs、编译原生的 `native.efi`，最终打包生成：
`dist\WCT-OS-LTS-1.0.img`

*(注：`linux/esp/EFI/BOOT` 和 `linux/esp/wct` 目录默认为空，构建脚本会在编译后自动将 EFI 和 Linux 加载器填入其中。)*



WCT-OS LTS 1.0 — Source Only

This folder contains source and build configuration only.
No compiled EFI, kernel, initramfs, rootfs or disk image is included.

Layout:
  native/                 self-developed C UEFI shell
    efi.h
    main.c
  linux/                  Linux compatibility build scripts
    fetch_rootfs.py
    trim_modules.py
    prepare_rootfs.py
    make_initramfs.py
    make_wct_image.py
    esp/                  ESP configuration and WCT scripts
  build.ps1               full build (native + Linux rootfs + image)
  build.cmd               Windows launcher for build.ps1
  run.ps1                 QEMU launcher
  start.cmd               Windows launcher for run.ps1

Build requirements:
  - Windows PowerShell 5.1+
  - MinGW-w64 GCC (C:\mingw64\bin\gcc.exe or gcc on PATH)
  - Python 3
  - curl.exe
  - Internet access to http://deb.debian.org/debian/

Build:
  build.cmd

The build downloads Debian packages, creates the root filesystem and
initramfs, compiles native/build/native.efi, and writes:
  dist\WCT-OS-LTS-1.0.img

The linux/esp/EFI/BOOT and linux/esp/wct directories are empty on
purpose. build.ps1 places the compiled native EFI and Linux loader there.
