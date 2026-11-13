#!/usr/bin/env python3
"""Create a gzip-compressed newc cpio initramfs for WCT-OS."""

from __future__ import annotations

import gzip
import json
import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FS = ROOT / "rootfs"
OUT = ROOT / "initrd.img"
SYMLINKS = json.loads((ROOT / "symlinks.json").read_text(encoding="utf-8"))
MODES = json.loads((ROOT / "modes.json").read_text(encoding="utf-8"))

SKIP_PREFIXES = (
    "usr/share/doc",
    "usr/share/man",
    "usr/share/info",
    "usr/share/locale",
    "usr/share/icons",
    "usr/share/pixmaps",
    "usr/share/fonts",
    "usr/share/perl",
    "usr/share/lintian",
)

TYPE_DIR = stat.S_IFDIR
TYPE_REG = stat.S_IFREG
TYPE_LNK = stat.S_IFLNK


def included(rel: str) -> bool:
    return not any(rel == p or rel.startswith(p + "/") for p in SKIP_PREFIXES)


def mode_of(rel: str, default: int) -> int:
    return MODES.get(rel, default) & 0o777


def pad4(n: int) -> int:
    return (-n) & 3


def write_entry(fh, name: str, mode: int, data: bytes = b"", nlink: int = 1) -> None:
    name_b = name.encode("utf-8") + b"\0"
    fields = [
        0,                 # ino
        mode,
        0,                 # uid
        0,                 # gid
        nlink,
        0,                 # mtime
        len(data),
        0, 0, 0, 0,        # dev/rdev
        len(name_b),
        0,                 # check
    ]
    fh.write(b"070701")
    for value in fields:
        fh.write(f"{value:08x}".encode("ascii"))
    fh.write(name_b)
    fh.write(b"\0" * pad4(110 + len(name_b)))
    if data:
        fh.write(data)
        fh.write(b"\0" * pad4(len(data)))


def collect() -> list[tuple[str, int, bytes, int]]:
    entries: list[tuple[str, int, bytes, int]] = []
    entries.append((".", TYPE_DIR | 0o755, b"", 2))

    file_paths: set[str] = set()
    for base, dirs, files in os.walk(FS):
        dirs.sort()
        files.sort()
        relbase = os.path.relpath(base, FS).replace("\\", "/")
        if relbase == ".":
            relbase = ""
        if relbase and included(relbase):
            entries.append((relbase, TYPE_DIR | mode_of(relbase, 0o755), b"", 2))
        for name in files:
            rel = (relbase + "/" + name).lstrip("/")
            if not included(rel):
                continue
            path = Path(base) / name
            file_paths.add(rel)
            try:
                data = path.read_bytes()
            except OSError:
                continue
            entries.append((rel, TYPE_REG | mode_of(rel, 0o644), data, 1))

    for rel, target in SYMLINKS.items():
        if not included(rel):
            continue
        if rel in file_paths:
            continue
        entries.append((rel, TYPE_LNK | 0o777, target.encode("utf-8"), 1))

    entries.sort(key=lambda item: item[0])
    return entries


def main() -> None:
    entries = collect()
    total = sum(len(e[2]) for e in entries)
    print(f"{len(entries)} entries, {total / 1024 / 1024:.1f} MiB payload")

    with open(OUT, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0) as gz:
            for name, mode, data, nlink in entries:
                write_entry(gz, name, mode, data, nlink)
            write_entry(gz, "TRAILER!!!", 0, b"", 1)

    print(f"wrote {OUT} ({OUT.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    main()
