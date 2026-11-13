#!/usr/bin/env python3
"""Build a bootable GPT + FAT32 ESP image for WCT-OS with VFAT long names."""

from __future__ import annotations

import math
import struct
import sys
import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "esp"
if len(sys.argv) >= 3:
    STAGE = Path(sys.argv[1]).resolve()
    OUT = Path(sys.argv[2]).resolve()
else:
    OUT = ROOT.parent / "dist" / "WCT-OS-LTS-1.0.img"

SECTOR = 512
IMAGE_SIZE = int(sys.argv[3]) * 1024 * 1024 if len(sys.argv) >= 4 else 256 * 1024 * 1024
TOTAL_SECTORS = IMAGE_SIZE // SECTOR
PART_START = 2048
PART_END = TOTAL_SECTORS - 34
PART_SECTORS = PART_END - PART_START + 1

RESERVED = 32
NUM_FATS = 2
SPC = 1 if IMAGE_SIZE <= 64 * 1024 * 1024 else 4
CLUSTER_SIZE = SECTOR * SPC
FIXED_DATE = ((2026 - 1980) << 9) | (11 << 5) | 7
FIXED_TIME = (9 << 11) | (0 << 5) | 0

ESP_TYPE_GUID = uuid.UUID("C12A7328-F81F-11D2-BA4B-00A0C93EC93B")
DISK_GUID = uuid.UUID("57544354-4F53-4C54-9B71-2D9F5E2C7A11")
PART_GUID = uuid.UUID("57544354-4F53-4C54-8E11-3EED0D4A9121")


class Node:
    def __init__(self, name: str, is_dir: bool, data: bytes = b""):
        self.name = name
        self.is_dir = is_dir
        self.data = data
        self.children: list[Node] = []
        self.short = b""
        self.clusters: list[int] = []
        self.parent: Node | None = None

    @property
    def size(self) -> int:
        return 0 if self.is_dir else len(self.data)


def load_tree(path: Path, name: str = "") -> Node:
    node = Node(name, path.is_dir())
    if path.is_dir():
        for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
            child_node = load_tree(child, child.name)
            child_node.parent = node
            node.children.append(child_node)
    else:
        node.data = path.read_bytes()
    return node


def valid_83_char(c: str) -> bool:
    return c.isalnum() or c in "$%'-_@~`!(){}^#&"


def make_short_names(node: Node) -> None:
    used: set[bytes] = set()
    for child in node.children:
        name = child.name
        upper = name.upper()
        base, dot, ext = upper.rpartition(".")
        if not dot:
            base, ext = upper, ""
        clean_base = "".join(c for c in base if valid_83_char(c))
        clean_ext = "".join(c for c in ext if valid_83_char(c))[:3]
        direct = (
            name == upper
            and 0 < len(clean_base) <= 8
            and len(clean_ext) <= 3
            and clean_base == base
            and clean_ext == ext
            and all(c not in " ." for c in name)
        )
        if direct:
            short = clean_base.ljust(8) + clean_ext.ljust(3)
            short = short.encode("ascii")
            if short not in used:
                child.short = short
                used.add(short)
                if child.is_dir:
                    make_short_names(child)
                continue
        prefix = "".join(c for c in clean_base if c.isalnum())[:6] or "WCTOS"
        n = 1
        while True:
            tail = f"~{n}"
            short_base = (prefix + tail)[:8]
            short = (short_base.ljust(8) + clean_ext.ljust(3)).encode("ascii")
            if short not in used:
                child.short = short
                used.add(short)
                break
            n += 1
        if child.is_dir:
            make_short_names(child)


def lfn_checksum(short: bytes) -> int:
    total = 0
    for c in short:
        total = (((total & 1) << 7) + (total >> 1) + c) & 0xFF
    return total


def lfn_entries(name: str, short: bytes) -> list[bytes]:
    if name.upper() == short.decode("ascii", "ignore").strip().replace(" ", ""):
        return []
    # Use a simple 8.3 equivalence test: the short entry is enough if the name
    # only differs by case and the short name has no numeric tail.
    short_clean = short.decode("ascii", "ignore").replace(" ", "")
    if "~" not in short_clean and short_clean.upper() == name.replace(".", "").upper():
        return []

    encoded = name.encode("utf-16le") + b"\x00\x00"
    while len(encoded) % 26:
        encoded += b"\xFF\xFF"
    chunks = [encoded[i : i + 26] for i in range(0, len(encoded), 26)]
    checksum = lfn_checksum(short)
    entries: list[bytes] = []
    for index in range(len(chunks) - 1, -1, -1):
        entry = bytearray(32)
        ordinal = index + 1
        if index == len(chunks) - 1:
            ordinal |= 0x40
        entry[0] = ordinal
        entry[1:11] = chunks[index][0:10]
        entry[11] = 0x0F
        entry[12] = 0
        entry[13] = checksum
        entry[14:26] = chunks[index][10:22]
        entry[26:28] = b"\x00\x00"
        entry[28:32] = chunks[index][22:26]
        entries.append(bytes(entry))
    return entries


def dir_entry(short: bytes, attr: int, cluster: int, size: int) -> bytes:
    entry = bytearray(32)
    entry[0:11] = short
    entry[11] = attr
    entry[12] = 0
    entry[13] = 0
    entry[14:16] = struct.pack("<H", FIXED_TIME)
    entry[16:18] = struct.pack("<H", FIXED_DATE)
    entry[18:20] = struct.pack("<H", FIXED_DATE)
    entry[20:22] = struct.pack("<H", (cluster >> 16) & 0xFFFF)
    entry[22:24] = struct.pack("<H", FIXED_TIME)
    entry[24:26] = struct.pack("<H", FIXED_DATE)
    entry[26:28] = struct.pack("<H", cluster & 0xFFFF)
    entry[28:32] = struct.pack("<I", size)
    return bytes(entry)


def dot_entry(name: str, cluster: int) -> bytes:
    short = (name.encode("ascii") + b" " * 11)[:11]
    return dir_entry(short, 0x10, cluster, 0)


def directory_entry_count(node: Node) -> int:
    count = 0
    if node.parent is not None:
        count += 2
    for child in node.children:
        count += len(lfn_entries(child.name, child.short)) + 1
    return count + 1


def fat_geometry() -> tuple[int, int]:
    for fat_sectors in range(1, 16384):
        clusters = (PART_SECTORS - RESERVED - NUM_FATS * fat_sectors) // SPC
        needed = math.ceil((clusters + 2) * 4 / SECTOR)
        if needed <= fat_sectors:
            if clusters < 65525:
                raise SystemExit("image too small for FAT32")
            return fat_sectors, clusters
    raise SystemExit("fat geometry failed")


def collect_nodes(root: Node) -> list[Node]:
    out = [root]
    for child in root.children:
        out.append(child)
        if child.is_dir:
            out.extend(collect_nodes(child))
    return out


def main() -> None:
    if not STAGE.exists():
        raise SystemExit(f"missing staging directory {STAGE}")
    root = load_tree(STAGE)
    make_short_names(root)

    fat_sectors, clusters = fat_geometry()
    fat = [0] * (clusters + 2)
    fat[0] = 0x0FFFFFF8
    fat[1] = 0x0FFFFFFF
    next_cluster = 2

    def alloc(count: int) -> list[int]:
        nonlocal next_cluster
        result = []
        for _ in range(count):
            if next_cluster >= len(fat):
                raise SystemExit("FAT cluster space exhausted")
            result.append(next_cluster)
            next_cluster += 1
        return result

    root.clusters = alloc(1)
    for node in collect_nodes(root):
        if node is root:
            continue
        if node.is_dir:
            entries = directory_entry_count(node)
            count = max(1, math.ceil(entries * 32 / CLUSTER_SIZE))
            node.clusters = alloc(count)
        else:
            count = max(1, math.ceil(len(node.data) / CLUSTER_SIZE))
            node.clusters = alloc(count)

    for node in collect_nodes(root):
        for i, cluster in enumerate(node.clusters):
            fat[cluster] = node.clusters[i + 1] if i + 1 < len(node.clusters) else 0x0FFFFFFF

    data_start = RESERVED + NUM_FATS * fat_sectors
    volume = bytearray(PART_SECTORS * SECTOR)

    # Boot sector.
    bs = bytearray(SECTOR)
    bs[0:3] = b"\xEB\x58\x90"
    bs[3:11] = b"WCTOS   "
    struct.pack_into("<H", bs, 11, SECTOR)
    bs[13] = SPC
    struct.pack_into("<H", bs, 14, RESERVED)
    bs[16] = NUM_FATS
    struct.pack_into("<H", bs, 17, 0)
    struct.pack_into("<H", bs, 19, 0)
    bs[21] = 0xF8
    struct.pack_into("<H", bs, 22, 0)
    struct.pack_into("<H", bs, 24, 63)
    struct.pack_into("<H", bs, 26, 255)
    struct.pack_into("<I", bs, 28, PART_START)
    struct.pack_into("<I", bs, 32, PART_SECTORS)
    struct.pack_into("<I", bs, 36, fat_sectors)
    struct.pack_into("<H", bs, 40, 0)
    struct.pack_into("<H", bs, 42, 0)
    struct.pack_into("<I", bs, 44, root.clusters[0])
    struct.pack_into("<H", bs, 48, 1)
    struct.pack_into("<H", bs, 50, 6)
    bs[64] = 0x80
    bs[66] = 0x29
    struct.pack_into("<I", bs, 67, 0x57544354)
    bs[71:82] = b"WCT-OS     "
    bs[82:90] = b"FAT32   "
    bs[510:512] = b"\x55\xAA"
    volume[0:SECTOR] = bs

    used = next_cluster - 2
    free = clusters - used
    fs = bytearray(SECTOR)
    struct.pack_into("<I", fs, 0, 0x41615252)
    struct.pack_into("<I", fs, 484, 0x61417272)
    struct.pack_into("<I", fs, 488, free)
    struct.pack_into("<I", fs, 492, next_cluster)
    struct.pack_into("<I", fs, 508, 0xAA550000)
    volume[SECTOR : 2 * SECTOR] = fs
    volume[6 * SECTOR : 7 * SECTOR] = bs
    volume[7 * SECTOR : 8 * SECTOR] = fs

    fat_bytes = bytearray((clusters + 2) * 4)
    for i, value in enumerate(fat):
        struct.pack_into("<I", fat_bytes, i * 4, value)
    fat_bytes.extend(b"\x00" * (fat_sectors * SECTOR - len(fat_bytes)))
    for i in range(NUM_FATS):
        start = (RESERVED + i * fat_sectors) * SECTOR
        volume[start : start + len(fat_bytes)] = fat_bytes

    def cluster_offset(cluster: int) -> int:
        return (data_start + (cluster - 2) * SPC) * SECTOR

    # Write file data.
    for node in collect_nodes(root):
        if node.is_dir:
            continue
        pos = 0
        for cluster in node.clusters:
            offset = cluster_offset(cluster)
            chunk = node.data[pos : pos + CLUSTER_SIZE]
            volume[offset : offset + len(chunk)] = chunk
            pos += len(chunk)

    # Write directory contents.
    def write_directory(node: Node) -> None:
        entries: list[bytes] = []
        if node.parent is not None:
            entries.append(dot_entry(".", node.clusters[0]))
            parent_cluster = node.parent.clusters[0] if node.parent.parent is not None else 0
            entries.append(dot_entry("..", parent_cluster))
        for child in node.children:
            entries.extend(lfn_entries(child.name, child.short))
            attr = 0x10 if child.is_dir else 0x20
            entries.append(dir_entry(child.short, attr, child.clusters[0], child.size))
        if not entries:
            entries.append(b"\x00" * 32)
        data = b"".join(entries) + b"\x00" * 32
        pos = 0
        for cluster in node.clusters:
            offset = cluster_offset(cluster)
            chunk = data[pos : pos + CLUSTER_SIZE]
            volume[offset : offset + len(chunk)] = chunk
            pos += len(chunk)

    for node in collect_nodes(root):
        if node.is_dir:
            write_directory(node)

    # GPT.
    disk = bytearray(IMAGE_SIZE)
    mbr = bytearray(SECTOR)
    mbr[446] = 0
    mbr[447:450] = b"\x00\x02\x00"
    mbr[450] = 0xEE
    mbr[451:454] = b"\xFF\xFF\xFF"
    struct.pack_into("<I", mbr, 454, 1)
    struct.pack_into("<I", mbr, 458, min(TOTAL_SECTORS - 1, 0xFFFFFFFF))
    mbr[510:512] = b"\x55\xAA"
    disk[0:SECTOR] = mbr

    entries = bytearray(128 * 128)
    entries[0:16] = ESP_TYPE_GUID.bytes_le
    entries[16:32] = PART_GUID.bytes_le
    struct.pack_into("<Q", entries, 32, PART_START)
    struct.pack_into("<Q", entries, 40, PART_END)
    struct.pack_into("<Q", entries, 48, 0)
    name = "WCT-OS LTS".encode("utf-16le")
    entries[56 : 56 + len(name)] = name
    entries_crc = zlib.crc32(entries) & 0xFFFFFFFF

    def gpt_header(current: int, backup: int, entries_lba: int) -> bytes:
        header = bytearray(struct.pack(
            "<8sIIIIQQQQ16sQIII",
            b"EFI PART", 0x00010000, 92, 0, 0, current, backup,
            34, TOTAL_SECTORS - 34, DISK_GUID.bytes_le, entries_lba,
            128, 128, entries_crc,
        ))
        struct.pack_into("<I", header, 16, zlib.crc32(header) & 0xFFFFFFFF)
        header.extend(b"\x00" * (SECTOR - len(header)))
        return bytes(header)

    disk[SECTOR : 2 * SECTOR] = gpt_header(1, TOTAL_SECTORS - 1, 2)
    disk[2 * SECTOR : 2 * SECTOR + len(entries)] = entries
    backup_entries_lba = TOTAL_SECTORS - 33
    disk[backup_entries_lba * SECTOR : backup_entries_lba * SECTOR + len(entries)] = entries
    disk[(TOTAL_SECTORS - 1) * SECTOR : TOTAL_SECTORS * SECTOR] = gpt_header(
        TOTAL_SECTORS - 1, 1, backup_entries_lba
    )

    part_offset = PART_START * SECTOR
    disk[part_offset : part_offset + len(volume)] = volume
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(disk)
    print(f"built {OUT} ({len(disk) / 1024 / 1024:.0f} MiB, GPT+FAT32, {used} clusters used)")


if __name__ == "__main__":
    main()
