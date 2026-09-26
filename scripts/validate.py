#!/usr/bin/env python3
"""Check everything under content/ the way the app and the reviewer will.

Usage:

    python3 scripts/validate.py content

Prints one line per problem, `path: what is wrong and what to do`, relative to
the repository root, and exits 1 if there is any. Exit 0 with no output means
the tree is ready for a pull request.

The rules live in one place on purpose: this script is what continuous
integration runs, what a contributor runs, and what a contributor's coding
agent runs, so all three see the same verdict.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    print("validate.py needs jsonschema: python3 -m pip install -r requirements-dev.txt", file=sys.stderr)
    raise SystemExit(2)

RECORD = "record.json"
README = "README.md"
INDEX = "index.json"
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"
_validators: dict[str, Draft202012Validator] = {}


def schema_validator(name: str) -> Draft202012Validator:
    if name not in _validators:
        _validators[name] = Draft202012Validator(json.loads((SCHEMA_DIR / name).read_text()))
    return _validators[name]


def schema_problems(value, schema_name: str, path: str) -> list[Problem]:
    problems = []
    for error in sorted(schema_validator(schema_name).iter_errors(value), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(p) for p in error.absolute_path)
        problems.append(Problem(path, f"{where + ': ' if where else ''}{error.message}"))
    return problems


@dataclass(frozen=True)
class Problem:
    path: str
    message: str


@dataclass
class Entry:
    kind: str
    id: str
    directory: Path
    record: dict

    @property
    def record_path(self) -> Path:
        return self.directory / RECORD


class Kind:
    """One content kind: its index key, its record `kind` value, its schema
    file under schema/, and the checks a schema cannot express."""

    key: str
    record_kind: str
    schema: str | None = None

    def assets_of(self, record: dict) -> list[dict]:
        return []

    def check(self, entry: Entry, records: list[Entry], root: Path) -> list[Problem]:
        return []


KINDS: dict[str, Kind] = {}


def register(kind: Kind) -> Kind:
    KINDS[kind.key] = kind
    return kind


class SolarEclipseKind(Kind):
    key = "events/solar-eclipses"
    record_kind = "solar-eclipse"


register(SolarEclipseKind())


class BodiesKind(Kind):
    key = "bodies"
    record_kind = "body"
    schema = "body.schema.json"

    def assets_of(self, record: dict) -> list[dict]:
        assets = list(record.get("assets") or [])
        for layer in record.get("layers") or []:
            assets.extend(layer.get("assets") or [])
        return [a for a in assets if isinstance(a, dict)]

    def check(self, entry: Entry, records: list[Entry], root: Path) -> list[Problem]:
        record, path, problems = entry.record, rel(root, entry.record_path), []
        asset_ids = {a.get("id") for a in self.assets_of(record)}
        texture = (record.get("appearance") or {}).get("textureID")
        if texture is not None and texture not in asset_ids:
            problems.append(Problem(path, f"appearance.textureID {texture!r} names no asset"))
        if record.get("tier") == "major" and not all([
            record.get("equatorialRadiusM"), record.get("polarRadiusM"), record.get("rotation"), texture,
        ]):
            problems.append(Problem(path, "a major body needs equatorialRadiusM, polarRadiusM, rotation, "
                                          "and appearance.textureID"))
        return problems


class TransitFeedsKind(Kind):
    key = "transit-feeds"
    record_kind = "transit-feed"
    schema = "transit-feed.schema.json"

    def check(self, entry: Entry, records: list[Entry], root: Path) -> list[Problem]:
        record, path, problems = entry.record, rel(root, entry.record_path), []
        coverage = record.get("coverage") or {}
        if all(isinstance(coverage.get(k), (int, float)) for k in ("minLat", "maxLat", "minLon", "maxLon")):
            if not coverage["minLat"] < coverage["maxLat"]:
                problems.append(Problem(path, "coverage.minLat must be less than maxLat"))
            if not coverage["minLon"] < coverage["maxLon"]:
                problems.append(Problem(path, "coverage.minLon must be less than maxLon"))
            if coverage["maxLat"] - coverage["minLat"] > 10 or coverage["maxLon"] - coverage["minLon"] > 10:
                problems.append(Problem(path, "coverage may span at most 10 degrees each way"))
        realtime = record.get("realtime") or {}
        if record.get("positioning") == "gps" and not realtime.get("vehiclePositions"):
            problems.append(Problem(path, "a gps feed needs at least one realtime.vehiclePositions URL"))
        if record.get("positioning") == "predicted" and not realtime.get("tripUpdates"):
            problems.append(Problem(path, "a predicted feed needs at least one realtime.tripUpdates URL"))
        for section in ("realtime", "static"):
            key = (record.get(section) or {}).get("key")
            if isinstance(key, dict) and (("query" in key) == ("header" in key)):
                problems.append(Problem(path, f"{section}.key names exactly one of 'query' or 'header'"))
        return problems


register(BodiesKind())
register(TransitFeedsKind())


def rel(root: Path, path: Path) -> str:
    """Paths are printed relative to the repository root, where people run git."""
    return str(path.relative_to(root.parent))


def load_json(path: Path, root: Path, problems: list[Problem]):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        problems.append(Problem(rel(root, path), f"not valid JSON: {error}"))
        return None


def entries_of(root: Path, problems: list[Problem]) -> list[Entry]:
    index_path = root / INDEX
    index = load_json(index_path, root, problems)
    if not isinstance(index, dict) or not isinstance(index.get("kinds"), dict):
        problems.append(Problem(rel(root, index_path), "must be an object with a 'kinds' object"))
        return []
    problems += schema_problems(index, "index.schema.json", rel(root, index_path))
    entries: list[Entry] = []
    for key in index["kinds"]:
        if key not in KINDS:
            problems.append(Problem(rel(root, index_path), f"unknown kind '{key}'"))
    # Every registered kind is walked, listed or not, so a folder the index
    # forgot is reported even when its kind has no key yet.
    for key in KINDS:
        ids = index["kinds"].get(key, [])
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            problems.append(Problem(rel(root, index_path), f"{key} must be an array of ids"))
            continue
        seen: set[str] = set()
        for id in ids:
            if id in seen:
                problems.append(Problem(rel(root, index_path), f"{key} lists '{id}' twice"))
                continue
            seen.add(id)
            directory = root / key / id
            record_path = directory / RECORD
            if not record_path.is_file():
                problems.append(Problem(rel(root, index_path),
                                        f"{key} lists '{id}' but {rel(root, record_path)} is missing"))
                continue
            record = load_json(record_path, root, problems)
            if record is None:
                continue
            if not isinstance(record, dict):
                problems.append(Problem(rel(root, record_path), "must be a JSON object"))
                continue
            entries.append(Entry(key, id, directory, record))
        # Folders the index forgot: the app would never see them.
        kind_dir = root / key
        if kind_dir.is_dir():
            for child in sorted(kind_dir.iterdir()):
                if child.is_dir() and child.name not in seen:
                    problems.append(Problem(rel(root, index_path), f"{key}/{child.name} exists but is not listed"))
    return entries


def check_identity(entry: Entry, root: Path) -> list[Problem]:
    kind = KINDS[entry.kind]
    path = rel(root, entry.record_path)
    problems = []
    if entry.record.get("id") != entry.id:
        problems.append(Problem(path, f"id is {entry.record.get('id')!r} but the directory is {entry.id!r}"))
    if entry.record.get("kind") != kind.record_kind:
        problems.append(Problem(path, f"kind is {entry.record.get('kind')!r} but {entry.kind} records are "
                                      f"{kind.record_kind!r}"))
    return problems


def check_files(entry: Entry, root: Path) -> list[Problem]:
    kind = KINDS[entry.kind]
    problems = []
    if not (entry.directory / README).is_file():
        problems.append(Problem(rel(root, entry.directory), f"{README} is missing"))
    declared = {RECORD, README}
    for asset in kind.assets_of(entry.record):
        path = asset.get("path")
        if not isinstance(path, str) or not path or "/" in path or path.startswith("."):
            problems.append(Problem(rel(root, entry.record_path),
                                    f"asset path {path!r} must be a plain filename in the entry directory"))
            continue
        declared.add(path)
        if not (entry.directory / path).is_file():
            problems.append(Problem(rel(root, entry.record_path), f"declares {path} but the file is missing"))
    for child in sorted(entry.directory.iterdir()):
        if child.name == ".DS_Store":
            continue
        if child.is_dir():
            problems.append(Problem(rel(root, child), "entries hold files only, no subdirectories"))
        elif child.name not in declared:
            problems.append(Problem(rel(root, child), f"not declared by {RECORD}"))
    return problems


def validate(root: Path) -> list[Problem]:
    problems: list[Problem] = []
    entries = entries_of(root, problems)
    by_kind: dict[str, list[Entry]] = {}
    for entry in entries:
        by_kind.setdefault(entry.kind, []).append(entry)
    for entry in entries:
        problems += check_identity(entry, root)
        kind = KINDS[entry.kind]
        if kind.schema:
            problems += schema_problems(entry.record, kind.schema, rel(root, entry.record_path))
        problems += check_files(entry, root)
        problems += kind.check(entry, by_kind[entry.kind], root)
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: validate.py <content root>", file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    problems = validate(root)
    for problem in problems:
        print(f"{problem.path}: {problem.message}")
    if problems:
        print(f"{len(problems)} problem(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
