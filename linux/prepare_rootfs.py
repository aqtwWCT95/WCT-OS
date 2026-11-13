#!/usr/bin/env python3
"""Configure the WCT-OS root filesystem and terminal environment."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FS = ROOT / "rootfs"
SYMLINKS = ROOT / "symlinks.json"
MODES = ROOT / "modes.json"

symlinks = json.loads(SYMLINKS.read_text(encoding="utf-8"))
modes = json.loads(MODES.read_text(encoding="utf-8"))

# os-release is a symlink in Debian; we provide our own regular file.
symlinks.pop("etc/os-release", None)
symlinks.pop("usr/lib/python3.11/sitecustomize.py", None)
symlinks["usr/bin/python"] = "python3.11"

for path in ("usr/local/bin", "etc", "var/log", "home"):
    (FS / path).mkdir(parents=True, exist_ok=True)

FILES = {
    "etc/os-release": """PRETTY_NAME="WCT-OS LTS 1.0"
NAME="WCT-OS"
VERSION_ID="1.0"
VERSION="1.0"
VERSION_CODENAME=stable
ID=wctos
ID_LIKE=debian
HOME_URL="https://wct.local/"
SUPPORT_URL="https://wct.local/support"
BUG_REPORT_URL="https://wct.local/bugs"
""",
    "etc/issue": """WCT-OS LTS 1.0 \\n \\l
""",
    "etc/passwd": """root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
wct:x:1000:1000:WCT User:/home/wct:/bin/bash
""",
    "etc/group": """root:x:0:
daemon:x:1:
wct:x:1000:
""",
    "etc/shells": """/bin/sh
/bin/bash
""",
    "etc/hostname": "wct-os\n",
    "etc/hosts": """127.0.0.1 localhost
127.0.1.1 wct-os
""",
    "etc/motd": """
  WCT-OS LTS 1.0  /  x86_64  /  UEFI
  ---------------------------------------------
  CPython 3.11.2       type: python
  GNU nano 7.2         type: nano FILE
  FAT32 workspace      /fat/home/wct
  UTF-8                LANG=C.UTF-8
  Chinese input        type: cn   (zhcon / pinyin)
  Native boot entry    type: native (reboot into C shell)

  Try: python --version, nano notes.txt, ls /fat
  The full disk is a real GPT + FAT32 filesystem.
""",
    "etc/profile": r"""# WCT-OS LTS 1.0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TERM=linux
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/lib/x86_64-linux-gnu
export HOSTNAME=wct-os
export SHELL=/bin/bash
export PS1='\[\033[01;32m\]wct@wct-os\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]$ '
if [ -d /home/wct ]; then cd /home/wct; fi
if [ -f /etc/bash.bashrc ]; then . /etc/bash.bashrc; fi
""",
    "etc/bash.bashrc": r"""alias ll='ls -lah'
alias py='python'
alias edit='nano'
export EDITOR=nano
""",
    "usr/local/bin/cn": """#!/bin/sh
# zhcon provides a UTF-8 Linux console with pinyin input.
if [ -x /usr/bin/zhcon ]; then
    exec /usr/bin/zhcon --utf8 "$@"
fi
echo "zhcon is not installed" >&2
exit 1
""",
    "usr/local/bin/native": """#!/bin/sh
# Reboot into the native C system (the firmware default).
echo "Rebooting into WCT-OS Native..."
sync
reboot -f
""",
    "init": r"""#!/bin/busybox sh
# WCT-OS LTS 1.0 initramfs init

/bin/busybox --install -s /bin
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mkdir -p /dev /proc /sys /run /tmp /fat /dev/pts /dev/shm
mount -t devtmpfs devtmpfs /dev 2>/dev/null
mkdir -p /dev/pts /dev/shm
mount -t devpts devpts /dev/pts 2>/dev/null
mount -t tmpfs tmpfs /run 2>/dev/null
mount -t tmpfs tmpfs /tmp 2>/dev/null

hostname wct-os 2>/dev/null
ldconfig 2>/dev/null

# Build the module index inside the initramfs, then load storage and FAT modules.
depmod -a 6.1.0-50-amd64 >/dev/null 2>&1
for mod in ata_piix libata scsi_mod sd_mod ahci virtio_blk virtio_pci nvme xhci_pci usb_storage vfat fat nls_cp437 nls_iso8859-1 nls_utf8 nls_ascii bochs; do
    modprobe -q "$mod" 2>/dev/null
done

FatMounted=0
for dev in /dev/sda1 /dev/vda1 /dev/nvme0n1p1 /dev/mmcblk0p1 /dev/sdb1; do
    if [ -b "$dev" ]; then
        if mount -t vfat -o rw,iocharset=utf8,umask=000 "$dev" /fat 2>/dev/null; then
            if [ -d /fat/wct ]; then FatMounted=1; break; fi
            umount /fat
        fi
        if mount -t vfat -o rw,iocharset=ascii,umask=000 "$dev" /fat 2>/dev/null; then
            if [ -d /fat/wct ]; then FatMounted=1; break; fi
            umount /fat
        fi
    fi
done

if [ "$FatMounted" = "1" ]; then
    mkdir -p /fat/home/wct /fat/data /fat/tmp
    ln -sfn /fat/home/wct /home/wct
else
    echo "WCT-OS: FAT32 partition was not found; using a RAM-only home."
    mkdir -p /home/wct
fi

export HOME=/home/wct
export USER=wct
export LOGNAME=wct
export SHELL=/bin/bash
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TERM=linux
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/lib/x86_64-linux-gnu

# A larger console font makes the 1280x800 UEFI framebuffer readable.
if [ -x /usr/bin/setfont ] || [ -x /bin/setfont ]; then
    for f in /usr/share/consolefonts/Uni2-Terminus32x16.psf.gz /usr/share/consolefonts/Lat15-Terminus32x16.psf.gz /usr/share/consolefonts/Uni2-Terminus28x14.psf.gz; do
        if [ -f "$f" ]; then
            setfont -C /dev/tty1 "$f" 2>/dev/null && break
        fi
    done
fi

cd /home/wct
clear 2>/dev/null
cat /etc/motd

if [ -c /dev/tty1 ]; then
    exec setsid cttyhack /bin/bash --login < /dev/tty1 > /dev/tty1 2>&1
elif [ -x /bin/bash ]; then
    exec /bin/bash --login
else
    exec /bin/sh -l
fi
""",
}

for rel, content in FILES.items():
    path = FS / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write LF endings explicitly; CRLF breaks init and shell scripts on Linux.
    path.write_bytes(content.encode("utf-8"))
    modes[rel] = 0o755 if rel in ("init", "usr/local/bin/cn", "usr/local/bin/native") else 0o644

# Empty, user-visible mount point (FAT32 is mounted over this at boot).
(FS / "fat").mkdir(parents=True, exist_ok=True)

# Remove Debian's obsolete boot directory and package metadata.
for rel in ("boot", "var/lib/dpkg", "var/lib/apt", "var/cache/apt"):
    p = FS / rel
    if p.exists():
        import shutil
        shutil.rmtree(p)

SYMLINKS.write_text(json.dumps(symlinks, indent=1), encoding="utf-8")
MODES.write_text(json.dumps(modes, indent=1), encoding="utf-8")
print(f"configured {FS} with {len(symlinks)} symlinks")
