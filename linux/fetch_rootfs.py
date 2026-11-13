#!/usr/bin/env python3
"""Fetch a minimal Debian root filesystem for WCT-OS from deb.debian.org over HTTP."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG_DIR = ROOT / "packages"
ROOTFS = ROOT / "rootfs"
KERNEL = ROOT / "kernel"
INDEX = PKG_DIR / "Packages"
BASE_URL = "http://deb.debian.org/debian/"

PACKAGES = [
    "busybox-static", "bash", "base-files", "debianutils", "coreutils",
    "libacl1", "libattr1", "libselinux1", "libpcre2-8-0",
    "libc6", "libc-bin", "libgcc-s1", "gcc-12-base", "libtinfo6", "libncursesw6", "ncurses-base",
    "nano",
    "python3", "python3.11", "python3.11-minimal", "libpython3.11-minimal",
    "libpython3.11-stdlib", "libpython3.11",
    "libexpat1", "zlib1g", "libssl3", "libbz2-1.0", "libcrypt1", "libdb5.3",
    "libffi8", "liblzma5", "libnsl2", "libtirpc3", "libgssapi-krb5-2",
    "libkrb5-3", "libk5crypto3", "libkrb5support0", "libcom-err2",
    "libkeyutils1", "libuuid1", "libreadline8", "readline-common",
    "libsqlite3-0", "media-types",
    "zhcon", "zhcon-data", "libgpm2", "libstdc++6",
    "systemd-boot-efi", "kbd", "console-setup-linux", "fonts-terminus",
    "kmod", "libkmod2", "libzstd1",
]

KERNEL_PACKAGE = "linux-image-6.1.0-50-amd64"


def parse_index() -> dict[str, dict[str, str]]:
    text = INDEX.read_text(encoding="utf-8", errors="replace")
    out: dict[str, dict[str, str]] = {}
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        fields: dict[str, str] = {}
        key = None
        for line in block.splitlines():
            if line.startswith(" ") and key:
                fields[key] += "\n" + line
            elif ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.strip()
        name = fields.get("Package")
        if name:
            out[name] = fields
    return out


def dep_names(value: str) -> list[str]:
    names: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        first = item.split("|")[0].strip()
        first = first.split("(")[0].strip()
        first = first.split("[")[0].strip()
        if first and not first.startswith("${"):
            names.append(first)
    return names


def resolve(index: dict[str, dict[str, str]]) -> list[str]:
    needed = set(PACKAGES)
    queue = list(PACKAGES)
    while queue:
        name = queue.pop()
        fields = index.get(name)
        if not fields:
            print(f"  (skip virtual/missing dependency: {name})")
            continue
        for dep in dep_names(fields.get("Pre-Depends", "") + ", " + fields.get("Depends", "")):
            if dep in index and dep not in needed:
                needed.add(dep)
                queue.append(dep)
    needed.add(KERNEL_PACKAGE)
    return sorted(needed)


def download(fields: dict[str, str]) -> Path:
    filename = fields["Filename"]
    target = PKG_DIR / Path(filename).name
    if target.exists() and target.stat().st_size == int(fields.get("Size", "0")):
        return target
    url = BASE_URL + filename
    print(f"  GET {url}")
    subprocess.run(["curl.exe", "-L", "--fail", "--max-time", "180", "-o", str(target), url], check=True)
    return target


def ar_members(blob: bytes):
    if not blob.startswith(b"!<arch>\n"):
        raise ValueError("not an ar archive")
    pos = 8
    while pos + 60 <= len(blob):
        header = blob[pos : pos + 60]
        name = header[0:16].decode("ascii", "replace").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        pos += 60
        data = blob[pos : pos + size]
        yield name, data
        pos += size + (size & 1)


def deb_data(deb: Path) -> tarfile.TarFile:
    blob = deb.read_bytes()
    for name, data in ar_members(blob):
        if name.startswith("data.tar"):
            return tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    raise ValueError(f"no data.tar in {deb}")


SYMLINKS: dict[str, str] = {}
MODES: dict[str, int] = {}


def safe_extract(tar: tarfile.TarFile, dest: Path, skip_prefixes=()) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for member in tar.getmembers():
        name = member.name.lstrip("./")
        if not name or name.startswith(skip_prefixes):
            continue
        if name.startswith("/") or ".." in Path(name).parts:
            continue
        if name.startswith(("usr/share/man/", "usr/share/doc/", "usr/share/info/")):
            continue
        target = dest / name
        MODES[name] = member.mode & 0o777
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif member.issym():
            # Windows cannot create symlinks without extra privileges.
            # Record it and materialize it later in the cpio archive.
            SYMLINKS[name] = member.linkname
            target.parent.mkdir(parents=True, exist_ok=True)
        elif member.islnk():
            src = dest / member.linkname.lstrip("./")
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                shutil.copyfile(src, target)
        elif member.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            if src:
                with open(target, "wb") as fh:
                    shutil.copyfileobj(src, fh)


def main() -> None:
    if not INDEX.exists():
        print("Packages index missing")
        sys.exit(1)
    index = parse_index()
    names = resolve(index)
    print(f"{len(names)} packages, downloading...")
    if ROOTFS.exists():
        shutil.rmtree(ROOTFS)
    ROOTFS.mkdir(parents=True)
    KERNEL.mkdir(parents=True, exist_ok=True)
    for name in names:
        fields = index.get(name)
        if not fields:
            continue
        print(f"[{name} {fields.get('Version')}]")
        deb = download(fields)
        tar = deb_data(deb)
        if name == KERNEL_PACKAGE:
            skip = ("lib/modules/",)
            # Extract the kernel image only; modules are handled separately below.
            safe_extract(tar, KERNEL, skip_prefixes=skip)
        else:
            safe_extract(tar, ROOTFS)
        tar.close()

    # The kernel package is also the source of the modules used by our initramfs.
    kernel_deb = next(PKG_DIR.glob("linux-image-6.1.0-50-amd64_*.deb"))
    tar = deb_data(kernel_deb)
    safe_extract(tar, ROOTFS, skip_prefixes=("boot/",))
    tar.close()

    boot = ROOTFS / "boot"
    if boot.exists():
        shutil.rmtree(boot)

    kernel_image = next(KERNEL.glob("boot/vmlinuz-*"), None)
    if kernel_image:
        shutil.copyfile(kernel_image, KERNEL / "vmlinuz")
        print("kernel:", kernel_image.name, kernel_image.stat().st_size)

    import json
    (ROOT / "symlinks.json").write_text(json.dumps(SYMLINKS, indent=1), encoding="utf-8")
    (ROOT / "modes.json").write_text(json.dumps(MODES, indent=1), encoding="utf-8")

    # Make the firmware loader entry look like a normal system bootloader.
    print("rootfs ready:", ROOTFS)


if __name__ == "__main__":
    main()
