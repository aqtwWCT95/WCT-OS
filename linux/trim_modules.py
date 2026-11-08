#!/usr/bin/env python3
"""Trim the kernel module tree to the drivers WCT-OS actually needs."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KVER = "6.1.0-50-amd64"
MODDIR = ROOT / "rootfs" / "lib" / "modules" / KVER
STAGE = ROOT / "modules_trim"

WANTED = {
    "vfat", "fat", "nls_cp437", "nls_iso8859_1", "nls_utf8", "nls_ascii",
    "ata_piix", "ahci", "libata", "scsi_mod", "scsi_common", "sd_mod",
    "virtio", "virtio_ring", "virtio_pci", "virtio_pci_legacy_dev",
    "virtio_pci_modern_dev", "virtio_blk",
    "nvme", "nvme_core",
    "usbcore", "usb_common", "xhci_hcd", "xhci_pci", "ehci_hcd", "ehci_pci",
    "usb_storage", "uas", "usbhid", "hid",
}

modules: dict[str, Path] = {}
deps: dict[str, list[str]] = {}
for path in MODDIR.rglob("*.ko"):
    blob = path.read_bytes()
    match = re.search(rb"depends=([^\x00]*)", blob)
    dep_list = []
    if match:
        raw = match.group(1).decode("ascii", "ignore")
        dep_list = [d for d in raw.split(",") if d]
    name = path.stem
    modules[name] = path
    deps[name] = dep_list

needed: set[str] = set()
queue = list(WANTED)
while queue:
    name = queue.pop()
    if name in needed or name not in modules:
        continue
    needed.add(name)
    for dep in deps.get(name, []):
        if dep not in needed:
            queue.append(dep)

selected = {name: modules[name] for name in sorted(needed)}
total = sum(p.stat().st_size for p in selected.values())
print(f"selected {len(selected)} modules, {total / 1024 / 1024:.1f} MiB")
for name in sorted(selected):
    print(f"  {name:28s} {selected[name].relative_to(MODDIR)}")

meta = {}
for name in ("modules.builtin", "modules.order", "modules.builtin.modinfo"):
    p = MODDIR / name
    if p.exists():
        meta[name] = p.read_bytes()

if STAGE.exists():
    shutil.rmtree(STAGE)
STAGE.mkdir(parents=True)
for name, path in selected.items():
    rel = path.relative_to(MODDIR)
    dest = STAGE / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, dest)
for name, data in meta.items():
    (STAGE / name).write_bytes(data)

shutil.rmtree(MODDIR)
shutil.copytree(STAGE, MODDIR)
shutil.rmtree(STAGE)
print("trim complete")
