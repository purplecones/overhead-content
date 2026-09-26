#!/usr/bin/env python3
"""Stamp asset digests, byte sizes and pixel dimensions into records of every kind.

Every `content/<kind>/<id>/record.json` declares its assets with a `sha256`, a
`byteLimit` and, for images, a `width`/`height` pair, and admission rejects the
record if any of them disagrees with the file on disk. Computing those by hand
is the step a contributor gets wrong, so this walks the content tree, reads
each declared asset from the directory beside its record, and writes the
measured values back.

Usage:

    python3 scripts/stamp.py content
    python3 scripts/stamp.py --check content

`--check` stamps nothing and exits non-zero if any record is stale, which is what
continuous integration runs. Records are rewritten with sorted keys and a
two-space indent, which is the shape the shipped records already have, so a
stamp of an already-correct record is a no-op in the diff.

Only the four measured fields are ever touched. `format`, `path`, `id` and
`required` are the author's declaration and are read, not rewritten: a mismatch
between the declared format and the file is reported as an error rather than
quietly corrected, because a JPEG relabelled as PNG is an authoring mistake, not
a stale digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

RECORD_FILENAME = "record.json"
INDEX_FILENAME = "index.json"
IMAGE_FIELDS = ("sha256", "byteLimit", "width", "height")
BINARY_FIELDS = ("sha256", "byteLimit")


class StampError(Exception):
    """An authoring mistake this script reports rather than repairs."""


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Width and height from a baseline or progressive JPEG's frame header.

    Only the SOFn markers carry the dimensions, so this walks the segment chain
    rather than trusting any single offset. Reading the file itself is the point:
    a resized texture must not keep the old record's dimensions.
    """
    if data[:2] != b"\xff\xd8":
        raise StampError("not a JPEG: missing the SOI marker")
    offset = 2
    size = len(data)
    while offset < size:
        if data[offset] != 0xFF:
            raise StampError(f"malformed JPEG segment at byte {offset}")
        marker = data[offset + 1]
        offset += 2
        # Standalone markers carry no length field.
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        (length,) = struct.unpack(">H", data[offset:offset + 2])
        # SOF0 to SOF15, excluding the DHT, JPG and DAC markers in that range.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
            return width, height
        offset += length
    raise StampError("no JPEG frame header found")


def png_dimensions(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise StampError("not a PNG: missing the signature")
    if data[12:16] != b"IHDR":
        raise StampError("malformed PNG: first chunk is not IHDR")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def dimensions(data: bytes, declared_format: str, label: str) -> tuple[int, int]:
    readers = {"jpeg": jpeg_dimensions, "jpg": jpeg_dimensions, "png": png_dimensions}
    reader = readers.get(declared_format.lower())
    if reader is None:
        raise StampError(f"{label}: unsupported declared format '{declared_format}'")
    try:
        return reader(data)
    except StampError as error:
        raise StampError(f"{label}: {error}") from error


def stamp_record(path: Path, check_only: bool) -> bool:
    """Returns True when the record on disk was already correct."""
    record = json.loads(path.read_text())
    assets = list(record.get("assets") or [])
    for layer in record.get("layers") or []:
        assets.extend(layer.get("assets") or [])
    if isinstance(record.get("model"), dict):
        assets.append(record["model"])
    stale: list[str] = []
    for asset in assets:
        asset_path = path.parent / asset["path"]
        label = f"{path.parent.name}/{asset['path']}"
        if not asset_path.is_file():
            raise StampError(f"{label}: declared by record.json but missing on disk")
        data = asset_path.read_bytes()
        declared_format = asset.get("format", "").lower()
        if declared_format == "glb":
            if data[:4] != b"glTF":
                raise StampError(f"{label}: declared glb but the file is not a GLB")
            fields = BINARY_FIELDS
            measured = {"sha256": sha256_of(data), "byteLimit": len(data)}
        else:
            width, height = dimensions(data, declared_format, label)
            fields = IMAGE_FIELDS
            measured = {"sha256": sha256_of(data), "byteLimit": len(data), "width": width, "height": height}
        for field in fields:
            if asset.get(field) != measured[field]:
                stale.append(f"{label}: {field} {asset.get(field)!r} -> {measured[field]!r}")
                asset[field] = measured[field]
    if not stale:
        return True
    for line in stale:
        print(("stale " if check_only else "stamped ") + line)
    if not check_only:
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return False


def records_of(root: Path) -> list[Path]:
    """Every entry the index declares, in index order.

    The index is the authority on what ships, so a stray directory left behind
    by a deleted entry is neither stamped nor reported as missing.
    """
    index_path = root / INDEX_FILENAME
    if not index_path.is_file():
        raise StampError(f"{index_path} is missing")
    index = json.loads(index_path.read_text())
    paths: list[Path] = []
    for kind, ids in sorted(index.get("kinds", {}).items()):
        for entry in ids:
            record = root / kind / entry / RECORD_FILENAME
            if not record.is_file():
                raise StampError(f"index declares {kind}/{entry} but {record} is missing")
            paths.append(record)
    return paths


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path,
                        help="the content root holding index.json, e.g. ios/Overhead/Resources/content")
    parser.add_argument("--check", action="store_true",
                        help="report stale records without rewriting them")
    arguments = parser.parse_args(argv)
    try:
        records = records_of(arguments.root)
        clean = [stamp_record(record, arguments.check) for record in records]
    except StampError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if all(clean):
        print(f"{len(records)} records already carry their measured asset values")
        return 0
    return 1 if arguments.check else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
