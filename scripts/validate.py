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

import celestial
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

    def check_kind(self, entries: list[Entry], root: Path) -> list[Problem]:
        """Rules that span every record of the kind, reported once."""
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


def _convention_repr(value):
    """2451545.0 reads as 2451545 in a message; strings keep their quotes."""
    if isinstance(value, float) and value.is_integer():
        return repr(int(value))
    return repr(value)


class BodiesKind(Kind):
    """Bodies are the one kind shipped app builds read today, and those builds
    reject the whole package when any body record fails to decode or to be
    admitted: one bad record removes every contributed body for every user.
    So every rule below mirrors a check in the app (Swift names cited beside
    each, all under ios/Overhead/ in the app repository), and a record that
    passes here is one the app admits."""

    key = "bodies"
    record_kind = "body"
    schema = "body.schema.json"

    # The app's admission checks reject an orbit or rotation that does not use
    # exactly these conventions (CelestialCatalogue.validateOrbit,
    # ~413-450, and validateRotation, ~467-517); a schema cannot express
    # "this field equals this value", so it is checked here.
    KEPLER_ORBIT_CONVENTIONS = {
        "epochJD": 2451545.0,
        "frame": "ecliptic-j2000",
        "distanceUnit": "au",
        "angleUnit": "deg",
        "timeConvention": "tt-as-utc",
    }
    LEGACY_LUNAR_ORBIT_CONVENTIONS = {
        "epochJD": 2451545.0,
        "frame": "earth-fixed",
        "timeConvention": "tt-as-utc",
    }
    IAU_LINEAR_ROTATION_CONVENTIONS = {
        "epochJD": 2451545.0,
        "frame": "equatorial-j2000",
        "angleUnit": "deg",
        "timeConvention": "tt-as-utc",
    }
    LEGACY_LUNAR_ROTATION_CONVENTIONS = {
        "epochJD": 2451545.0,
        "frame": "world-legacy",
        "timeConvention": "tt-as-utc",
    }
    # CelestialCatalogue.validateRecordIdentities: the app owns these two.
    PROTECTED_IDS = ("sun", "earth")
    # CelestialCapability.implemented, minus layers (those come from
    # CelestialLayerRegistry and are checked against the record's own lists).
    ORBIT_CAPABILITY = {"kepler-standish-table2a": "kepler-standish-table2a/1",
                        "legacy-lunar-schlyter": "legacy-lunar-schlyter/1"}
    ROTATION_CAPABILITY = {"iau-linear": "iau-linear/1", "legacy-lunar-libration": "legacy-lunar-libration/1"}
    PHOTOMETRY_CAPABILITY = {"lunar": "lunar/1", "lambert": "lambert/1", "emissive": "emissive/1"}
    # CelestialLayerRegistry.capabilities.
    LAYER_CAPABILITIES = {"rings/1"}
    # CelestialCapability.implemented: a record requiring anything else is
    # skipped by shipped builds.
    IMPLEMENTED = (set(ORBIT_CAPABILITY.values()) | set(ROTATION_CAPABILITY.values())
                   | set(PHOTOMETRY_CAPABILITY.values()) | LAYER_CAPABILITIES)

    # Temporary shipped-build limits, bodies only. Current app builds fail the
    # whole package past any of these; they are removed here when the app's
    # content-kinds plan ships and lifts them in the app.
    SHIPPED_MAX_MAJOR = 14                  # CatalogueLimits.maxMajorRecords (CelestialTree.maximumBodyCount 16 - Sun, Earth)
    SHIPPED_MAX_RECORDS = 64                # ContentPackageFetcher.maximumRecords
    SHIPPED_MAX_RECORD_BYTES = 256 * 1024   # CelestialContentLayout.maximumRecordBytes
    SHIPPED_MAX_INDEX_BYTES = 64 * 1024     # CelestialContentLayout.maximumIndexBytes (the index every kind shares)
    SHIPPED_MAX_ASSET_BYTES = 16 * 1024 * 1024    # DirectoryCelestialAssetProvider.maximumEncodedBytes
    SHIPPED_MAX_PACKAGE_BYTES = 64 * 1024 * 1024  # ContentPackageFetcher.maximumPackageBytes (sum of body asset byteLimits)

    def assets_of(self, record: dict) -> list[dict]:
        assets = list(record.get("assets") or [])
        for layer in record.get("layers") or []:
            if isinstance(layer, dict):
                assets.extend(layer.get("assets") or [])
        return [a for a in assets if isinstance(a, dict)]

    def check(self, entry: Entry, records: list[Entry], root: Path) -> list[Problem]:
        record, path, problems = entry.record, rel(root, entry.record_path), []

        def add(message: str) -> None:
            problems.append(Problem(path, message))

        if record.get("id") in self.PROTECTED_IDS:
            # CelestialCatalogue.validateRecordIdentities (protectedAnchorOverride)
            add(f"id {record.get('id')!r} is reserved: the app draws the Sun and Earth itself")
        top_assets = [a for a in (record.get("assets") or []) if isinstance(a, dict)]
        asset_ids = {a.get("id") for a in top_assets}
        texture = (record.get("appearance") or {}).get("textureID")
        if texture is not None and texture not in asset_ids:
            # CelestialCatalogue.resolveAssets (unknownTextureID); layer assets never count.
            add(f"appearance.textureID {texture!r} names no asset")
        # CelestialTier.validate: a major body needs a texture (radii are schema-positive).
        if record.get("tier") == "major" and not texture:
            add("a major body needs appearance.textureID")
        paths = [a.get("path") for a in top_assets]
        for duplicate in sorted({p for p in paths if isinstance(p, str) and paths.count(p) > 1}):
            # CelestialCatalogue.resolveAssets: "duplicate asset path"
            add(f"two assets share the path {duplicate!r}")

        # The numeric rules need a well-formed record; schema problems are
        # reported centrally by validate().
        if schema_validator(self.schema).is_valid(record):
            self.check_physics(record, add)
            self.check_capabilities(record, add)
        return problems

    def check_physics(self, record: dict, add) -> None:
        eq, polar = record["equatorialRadiusM"], record["polarRadiusM"]
        # CelestialCatalogue.validatePhysical: polar <= equatorial (bounds are in the schema).
        if polar > eq:
            add("polarRadiusM must not exceed equatorialRadiusM")
        appearance = record["appearance"]
        # CelestialCatalogue.validateAppearance: presentation against the radii.
        if appearance["presentation"] == "sphere" and eq != polar:
            add("presentation sphere needs equatorialRadiusM equal to polarRadiusM; use ellipsoid for a flattened body")
        if appearance["presentation"] == "ellipsoid" and not polar < eq:
            add("presentation ellipsoid needs polarRadiusM below equatorialRadiusM; use sphere for equal radii")
        # CelestialCatalogue.validateAppearance / requiredMagnitude: lunar and
        # lambert need a finite absoluteMagnitude; emissive may omit it.
        if appearance["photometry"]["model"] in ("lunar", "lambert") and "absoluteMagnitude" not in appearance:
            add(f"appearance.absoluteMagnitude is required for {appearance['photometry']['model']} photometry "
                "(the body's V(1,0), for example from the NSSDC fact sheet)")

        orbit = record["orbit"]
        model = orbit["model"]
        if model == "kepler-standish-table2a":
            for field, expected in self.KEPLER_ORBIT_CONVENTIONS.items():
                if orbit.get(field) != expected:
                    add(f"orbit.{field} must be {_convention_repr(expected)}")
        elif model == "legacy-lunar-schlyter":
            for field, expected in self.LEGACY_LUNAR_ORBIT_CONVENTIONS.items():
                if orbit.get(field) != expected:
                    add(f"orbit.{field} must be {_convention_repr(expected)}")
            # CelestialCatalogue.validateAdapterConstraints
            if record.get("parent") != "earth":
                add("legacy-lunar-schlyter only works for a body whose parent is earth")
        # CelestialCatalogue.validityRange, called by validateOrbit.
        validity = celestial.validity_problem(orbit["validityStartJD"], orbit["validityEndJD"])
        if validity:
            add(f"orbit: {validity}")
        elif model == "kepler-standish-table2a":
            # GenericKeplerOrbit.init, then heliocentricPosition at both endpoints (validateOrbit).
            elements = orbit["elements"]
            problem = celestial.kepler_elements_problem(elements)
            if problem is None:
                for jd in (orbit["validityStartJD"], orbit["validityEndJD"]):
                    problem = celestial.kepler_position_problem(elements, jd)
                    if problem:
                        break
            if problem:
                add(problem)

        rotation = record["rotation"]
        rotation_model = rotation["model"]
        if rotation_model == "iau-linear":
            for field, expected in self.IAU_LINEAR_ROTATION_CONVENTIONS.items():
                if rotation.get(field) != expected:
                    add(f"rotation.{field} must be {_convention_repr(expected)}")
        elif rotation_model == "legacy-lunar-libration":
            for field, expected in self.LEGACY_LUNAR_ROTATION_CONVENTIONS.items():
                if rotation.get(field) != expected:
                    add(f"rotation.{field} must be {_convention_repr(expected)}")
        # CelestialCatalogue.validityRange, called by validateRotation.
        validity = celestial.validity_problem(rotation["validityStartJD"], rotation["validityEndJD"])
        if validity:
            add(f"rotation: {validity}")
        elif rotation_model == "iau-linear":
            # IAURotation.init, then orientation and spin at both endpoints (validateRotation).
            coefficients = rotation["coefficients"]
            problem = celestial.iau_coefficients_problem(coefficients)
            if problem is None:
                for jd in (rotation["validityStartJD"], rotation["validityEndJD"]):
                    problem = celestial.iau_endpoint_problem(coefficients, jd)
                    if problem:
                        break
            if problem:
                add(problem)

    def check_capabilities(self, record: dict, add) -> None:
        """CelestialCapability.rejection: a record that uses a model it does not
        list in requires, or carries a layer listed in neither list, is skipped
        by the app. That is not package-wide, but the body silently never
        appears, so it is reported."""
        requires = set(record["capabilities"]["requires"])
        listed = requires | set(record["capabilities"].get("enhances") or [])
        used = [self.ORBIT_CAPABILITY[record["orbit"]["model"]]]
        if record["tier"] == "major":
            used.append(self.ROTATION_CAPABILITY[record["rotation"]["model"]])
            used.append(self.PHOTOMETRY_CAPABILITY[record["appearance"]["photometry"]["model"]])
        for capability in used:
            if capability not in requires:
                add(f"uses {capability!r} without listing it in capabilities.requires, so the app skips the record")
        for layer in record.get("layers") or []:
            capability = f"{layer['type']}/{layer['version']}"
            if capability not in listed:
                add(f"carries layer {capability!r} without listing it in capabilities.requires or enhances, "
                    "so the app skips the record")

    def unimplemented(self, record: dict) -> str | None:
        """The first capability a record requires that shipped builds lack."""
        capabilities = record.get("capabilities")
        requires = capabilities.get("requires") if isinstance(capabilities, dict) else None
        if not isinstance(requires, list):
            return None
        return next((c for c in sorted(r for r in requires if isinstance(r, str)) if c not in self.IMPLEMENTED), None)

    def check_kind(self, entries: list[Entry], root: Path) -> list[Problem]:
        """Rules that span records: each is package-wide on shipped builds."""
        problems: list[Problem] = []
        by_id = {e.id: e for e in entries}
        majors = [e for e in entries if e.record.get("tier") == "major"]
        # Shipped builds skip a major that requires an unimplemented capability,
        # so it is no parent: a child of it fails CelestialTree with missingParent.
        admitted = [e for e in majors if not self.unimplemented(e.record)]
        major_ids = {e.id for e in admitted}
        skipped = {e.id: self.unimplemented(e.record) for e in majors if self.unimplemented(e.record)}

        # CelestialCatalogue.resolveAssets: record asset ids are unique across the package.
        owners: dict[str, str] = {}
        for entry in entries:
            for asset in entry.record.get("assets") or []:
                if not isinstance(asset, dict) or not isinstance(asset.get("id"), str):
                    continue
                if asset["id"] in owners:
                    problems.append(Problem(rel(root, entry.record_path),
                                            f"asset id {asset['id']!r} is already used by {owners[asset['id']]}; "
                                            "asset ids must be unique across all bodies"))
                else:
                    owners[asset["id"]] = entry.id

        # CelestialTree.init: a major body's parent is the Sun, Earth, or another
        # admitted major body (missingParent), with no cycles. The app does not
        # place minor bodies in the tree yet; a minor's parent must at least be
        # a body this repository or the app knows.
        for entry in entries:
            parent = entry.record.get("parent")
            if not isinstance(parent, str):
                continue
            if entry.record.get("tier") == "major":
                if parent in skipped:
                    problems.append(Problem(rel(root, entry.record_path),
                                            f"parent {parent!r} requires {skipped[parent]!r}, which current app builds "
                                            "do not implement; they skip the parent and would drop every body"))
                elif parent not in self.PROTECTED_IDS and parent not in major_ids:
                    problems.append(Problem(rel(root, entry.record_path),
                                            f"parent {parent!r} must be sun, earth, or a major body listed under bodies"))
            elif parent not in self.PROTECTED_IDS and parent not in by_id:
                problems.append(Problem(rel(root, entry.record_path),
                                        f"parent {parent!r} must be sun, earth, or a body listed under bodies"))
        problems += self.tree_problems(admitted, root)

        # Temporary shipped-build limits (see the constants above).
        index_path = root / INDEX
        if index_path.is_file() and index_path.stat().st_size > self.SHIPPED_MAX_INDEX_BYTES:
            problems.append(Problem(rel(root, index_path),
                                    f"is {index_path.stat().st_size} bytes; current app builds read at most "
                                    f"{self.SHIPPED_MAX_INDEX_BYTES} and would drop every body"))
        if len(majors) > self.SHIPPED_MAX_MAJOR:
            problems.append(Problem(rel(root, index_path),
                                    f"bodies lists {len(majors)} major bodies; current app builds admit at most "
                                    f"{self.SHIPPED_MAX_MAJOR} and would drop every body"))
        if len(entries) > self.SHIPPED_MAX_RECORDS:
            problems.append(Problem(rel(root, index_path),
                                    f"bodies lists {len(entries)} records; current app builds fetch at most "
                                    f"{self.SHIPPED_MAX_RECORDS} and would drop every body"))
        total = 0
        for entry in entries:
            size = entry.record_path.stat().st_size
            if size > self.SHIPPED_MAX_RECORD_BYTES:
                problems.append(Problem(rel(root, entry.record_path),
                                        f"is {size} bytes; current app builds read at most "
                                        f"{self.SHIPPED_MAX_RECORD_BYTES} and would drop every body"))
            layer_assets = [id(a) for layer in entry.record.get("layers") or [] if isinstance(layer, dict)
                            for a in layer.get("assets") or []]
            for asset in self.assets_of(entry.record):
                limit = asset.get("byteLimit")
                if isinstance(limit, int) and not isinstance(limit, bool):
                    total += limit
                    # Record textures carry this cap in the schema (validateAssetDescriptor);
                    # the fetcher applies it to layer assets too (ContentPackageFetcher.fill).
                    if id(asset) in layer_assets and limit > self.SHIPPED_MAX_ASSET_BYTES:
                        problems.append(Problem(rel(root, entry.record_path),
                                                f"asset {asset.get('id')!r} is {limit} bytes; current app builds "
                                                f"accept at most {self.SHIPPED_MAX_ASSET_BYTES} (16 MiB) per asset"))
        if total > self.SHIPPED_MAX_PACKAGE_BYTES:
            problems.append(Problem(rel(root, index_path),
                                    f"body assets total {total} bytes; current app builds fetch at most "
                                    f"{self.SHIPPED_MAX_PACKAGE_BYTES} (64 MiB) and would drop every body"))
        return problems

    def tree_problems(self, majors: list[Entry], root: Path) -> list[Problem]:
        """CelestialTree.init: walk majors parent-first from the Sun and Earth
        anchors; report a cycle, and any orbit whose Hill radius, period or
        reach overflows."""
        problems: list[Problem] = []
        known = {"sun": (celestial.SUN_GM, 0.0)}
        _, earth_reach = celestial.tree_step(celestial.SUN_GM, 0.0, *celestial.LEGACY_EARTH_ORBIT, celestial.EARTH_GM)
        known["earth"] = (celestial.EARTH_GM, earth_reach)
        remaining = [e for e in majors if schema_validator(self.schema).is_valid(e.record)]
        while remaining:
            ready = [e for e in remaining if e.record["parent"] in known]
            if not ready:
                # What is left is either blocked by a missing parent (reported
                # above) or on a loop (CelestialTreeError.cycle).
                parents = {e.id: e.record["parent"] for e in remaining}
                for entry in remaining:
                    seen, current = set(), entry.id
                    while current in parents and current not in seen:
                        seen.add(current)
                        current = parents[current]
                    if current == entry.id:
                        problems.append(Problem(rel(root, entry.record_path),
                                                "parent chain loops back on itself; a body cannot orbit its own descendant"))
                break
            for entry in ready:
                remaining.remove(entry)
                record = entry.record
                parent_gm, parent_reach = known[record["parent"]]
                orbit = record["orbit"]
                if orbit["model"] == "legacy-lunar-schlyter":
                    a_m, e = celestial.LEGACY_MOON_ORBIT
                else:
                    elements = orbit["elements"]
                    a_m, e = elements["semiMajorAxisAU"] * celestial.AU, elements["eccentricity"]
                    if celestial.kepler_elements_problem(elements):
                        continue  # already reported per record
                problem, reach = celestial.tree_step(parent_gm, parent_reach, a_m, e,
                                                     record["gravitationalParameterM3S2"])
                if problem:
                    problems.append(Problem(rel(root, entry.record_path), problem))
                    continue
                known[entry.id] = (record["gravitationalParameterM3S2"], reach)
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


def _reject_constant(name: str):
    raise ValueError(f"{name} is not JSON; the app's decoder rejects it")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text} is too large for a 64-bit float; the app's decoder rejects it")
    return value


def _representable_int(text: str) -> int:
    value = int(text)
    float(value)  # raises OverflowError past the float range, as the app's decoder fails
    return value


def strict_json(text: str):
    """json.loads, but refusing what Swift's JSONDecoder refuses: the NaN,
    Infinity and -Infinity literals Python accepts by default, and numbers
    outside the 64-bit float range, which Python would turn into inf."""
    return json.loads(text, parse_constant=_reject_constant, parse_float=_finite_float,
                      parse_int=_representable_int)


def load_json(path: Path, root: Path, problems: list[Problem]):
    try:
        return strict_json(path.read_text())
    except (OSError, ValueError, OverflowError) as error:
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
    # The app's asset provider rejects any symlink in a package path
    # (DirectoryCelestialAssetProvider.data), and a link can point outside
    # the repository, so entries hold regular files only.
    if entry.directory.is_symlink():
        return [Problem(rel(root, entry.directory), "is a symlink; entries must be real directories")]
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
        if (entry.directory / path).is_symlink():
            continue  # reported below with the directory listing
        if not (entry.directory / path).is_file():
            problems.append(Problem(rel(root, entry.record_path), f"declares {path} but the file is missing"))
    for child in sorted(entry.directory.iterdir()):
        if child.name == ".DS_Store":
            continue
        if child.is_symlink():
            problems.append(Problem(rel(root, child), "is a symlink; entries hold regular files only"))
        elif child.is_dir():
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
    for key, kind in KINDS.items():
        problems += kind.check_kind(by_kind.get(key, []), root)
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
