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

import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    print("validate.py needs jsonschema: python3 -m pip install -r requirements-dev.txt", file=sys.stderr)
    raise SystemExit(2)

import glb

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


def julian_day(moment: datetime) -> float:
    return moment.timestamp() / 86400.0 + 2440587.5


def mean_new_moon_offset_days(greatest: datetime) -> float:
    """Days from `greatest` to the nearest mean new moon (Meeus, Astronomical
    Algorithms, chapter 49, mean phase only).

    The true new moon differs from the mean by up to about 14 hours, so this is
    a coarse check: it catches a wrong month or day, not a wrong hour. The app
    performs the exact check at admission."""
    jd = julian_day(greatest)
    years = (jd - 2451545.0) / 365.25 + 2000.0
    k = round((years - 2000.0) * 12.3685)
    best = math.inf
    for candidate in (k - 1, k, k + 1):
        t = candidate / 1236.85
        jde = 2451550.09766 + 29.530588861 * candidate + 0.00015437 * t * t
        best = min(best, jd - jde, key=abs)
    return best


class SolarEclipseKind(Kind):
    key = "events/solar-eclipses"
    record_kind = "solar-eclipse"
    schema = "solar-eclipse.schema.json"

    def check(self, entry: Entry, records: list[Entry], root: Path) -> list[Problem]:
        record, path, problems = entry.record, rel(root, entry.record_path), []
        raw = record.get("greatest")
        if not isinstance(raw, str):
            return problems
        try:
            greatest = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            problems.append(Problem(path, f"greatest {raw!r} is not a real UTC instant"))
            return problems
        date = greatest.strftime("%Y-%m-%d")
        if record.get("id") != date:
            problems.append(Problem(path, f"id must be the UTC date of greatest, {date}"))
        offset = mean_new_moon_offset_days(greatest)
        if abs(offset) > 1.0:
            problems.append(Problem(path, f"greatest is {abs(offset):.1f} days from the nearest new moon; "
                                          "a solar eclipse happens at new moon, so check the date"))
        return problems


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


CRAFT_CLASSES = {
    "aircraft": ["airplane", "propeller", "helicopter", "glider", "balloon", "parachutist", "ultralight",
                 "drone", "space-vehicle", "ground-vehicle", "obstacle"],
    "vessels": ["fishing", "tug", "sailing", "pleasure", "high-speed", "service", "passenger", "cargo",
                "tanker", "other"],
    "satellites": ["payload", "rocket-body", "debris"],
    "transit": ["bus", "subway", "light-rail", "rail", "ferry", "cable"],
}
CRAFT_TYPE_PATTERNS = {
    "aircraft": r"^[A-Z0-9]{2,4}$",
    "vessels": r"^[0-9]{9}$",
    "satellites": r"^[0-9]{1,9}$",
}


class CraftKind(Kind):
    record_kind = "craft"
    schema = "craft.schema.json"

    def __init__(self, domain: str):
        self.domain = domain
        self.key = f"craft/{domain}"

    def assets_of(self, record: dict) -> list[dict]:
        model = record.get("model")
        return [model] if isinstance(model, dict) else []

    def check(self, entry: Entry, records: list[Entry], root: Path) -> list[Problem]:
        record, path, problems = entry.record, rel(root, entry.record_path), []
        matches = record.get("matches") or {}
        classes, types = matches.get("classes") or [], matches.get("types") or []
        allowed = CRAFT_CLASSES[self.domain]
        for name in classes:
            if name not in allowed:
                problems.append(Problem(path, f"class {name!r} is not a {self.domain} class ({', '.join(allowed)})"))
        pattern = CRAFT_TYPE_PATTERNS.get(self.domain)
        for name in types:
            if pattern is None:
                problems.append(Problem(path, f"{self.domain} craft have no types yet"))
                break
            if not re.fullmatch(pattern, str(name)):
                problems.append(Problem(path, f"type {name!r} does not match the {self.domain} pattern {pattern}"))
        if not classes and not types and not matches.get("default"):
            problems.append(Problem(path, "matches must name a class, a type, or default"))
        # Earlier records in index order keep their claims.
        for other in records:
            if other is entry:
                break
            other_matches = other.record.get("matches") or {}
            for name in types:
                if name in (other_matches.get("types") or []):
                    problems.append(Problem(path, f"type {name!r} is already claimed by {other.id}"))
            if matches.get("default") and other_matches.get("default"):
                problems.append(Problem(path, f"{self.domain} already has a default, {other.id}"))
        model = record.get("model")
        model_path = entry.directory / "model.glb"
        if isinstance(model, dict) and model_path.is_file():
            data = model_path.read_bytes()
            if model.get("sha256") != hashlib.sha256(data).hexdigest() or model.get("byteLimit") != len(data):
                problems.append(Problem(path, "model.glb sha256 or byteLimit is stale; run python3 scripts/stamp.py content"))
            try:
                messages = glb.check(data)
            except Exception as error:  # glb.check should report, never raise; this is a last resort.
                problems.append(Problem(rel(root, model_path), f"could not be read as a GLB: {error}"))
            else:
                for message in messages:
                    problems.append(Problem(rel(root, model_path), message))
        return problems


register(BodiesKind())
register(TransitFeedsKind())
for _domain in CRAFT_CLASSES:
    register(CraftKind(_domain))


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
