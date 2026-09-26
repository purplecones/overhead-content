import tempfile
import unittest
from pathlib import Path

from support import make_root, write_entry, messages
import validate

REPO_CONTENT = Path(__file__).resolve().parents[2] / "content"

MINIMAL_BODY = {
    "kind": "body", "id": "ceres", "tier": "minor", "displayName": "Ceres", "parent": "sun",
    "capabilities": {"requires": ["kepler-standish-table2a/1"]},
    # The app decodes these for every tier, so the schema now requires them too.
    "equatorialRadiusM": 71492000.0,
    "polarRadiusM": 66854000.0,
    "gravitationalParameterM3S2": 1.26687e+17,
    # A real, admissible kepler orbit, copied from the shipped Jupiter record,
    # so the app's orbit conventions are satisfied and not just the schema.
    "orbit": {
        "model": "kepler-standish-table2a", "version": "1",
        "epochJD": 2451545.0, "frame": "ecliptic-j2000", "distanceUnit": "au", "angleUnit": "deg",
        "timeConvention": "tt-as-utc", "validityStartJD": 625295.0, "validityEndJD": 2816795.0,
        "elements": {
            "eccentricity": 0.0485359, "inclinationDeg": 1.29861416,
            "longitudeOfAscendingNodeDeg": 100.29282654, "longitudeOfPerihelionDeg": 14.27495244,
            "meanLongitudeDeg": 34.33479152, "rateEccentricity": 0.00018026,
            "rateInclination": -0.00322699, "rateMeanLongitude": 3034.90371757,
            "rateNode": 0.13024619, "ratePerihelion": 0.18199196,
            "rateSemiMajorAxis": -2.864e-05, "semiMajorAxisAU": 5.20248019,
        },
    },
    "rotation": {
        "model": "iau-linear", "version": "1",
        "epochJD": 2451545.0, "frame": "equatorial-j2000", "timeConvention": "tt-as-utc", "angleUnit": "deg",
        "validityStartJD": 625295.0, "validityEndJD": 2816795.0,
        "coefficients": {
            "poleDeclination": 64.495303, "poleRateDec": 0.002413, "poleRateRA": -0.006499,
            "poleRightAscension": 268.056595, "primeMeridian": 284.95, "rotationRate": 870.536,
        },
    },
    "appearance": {},
    "assets": [],
    "provenance": {"sources": ["https://ssd.jpl.nasa.gov/"], "attribution": "JPL", "licence": "Public domain",
                   "modelVersion": "x", "accuracy": "x", "coverage": "x"},
}

MINIMAL_FEED = {
    "kind": "transit-feed", "id": "demo", "agency": "Demo Transit",
    "coverage": {"minLat": 40.0, "minLon": -74.5, "maxLat": 41.0, "maxLon": -73.5},
    "modes": ["bus"], "positioning": "gps",
    "realtime": {"vehiclePositions": ["https://example.com/vp.pb"], "refreshSeconds": 15, "key": None},
    "static": {"gtfs": ["https://example.com/gtfs.zip"], "key": None},
    "licence": {"name": "Open", "url": "https://example.com/licence", "credit": "Demo"},
    "provenance": {"verifiedAt": "2026-09-25", "notes": "test"},
}


class ExistingKindTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_shipped_content_is_valid(self):
        self.assertEqual(messages(validate.validate(REPO_CONTENT)), [])

    def test_minimal_minor_body_admits(self):
        write_entry(self.root, "bodies", "ceres", MINIMAL_BODY)
        self.assertEqual(messages(validate.validate(self.root)), [])

    def test_major_body_needs_texture_and_radii(self):
        record = dict(MINIMAL_BODY, tier="major")
        write_entry(self.root, "bodies", "ceres", record)
        found = messages(validate.validate(self.root))
        self.assertIn("content/bodies/ceres/record.json: a major body needs equatorialRadiusM, "
                      "polarRadiusM, rotation, and appearance.textureID", found)

    def test_texture_id_must_name_an_asset(self):
        record = dict(MINIMAL_BODY, appearance={"presentation": "sphere", "textureID": "nope"})
        write_entry(self.root, "bodies", "ceres", record)
        found = messages(validate.validate(self.root))
        self.assertIn("content/bodies/ceres/record.json: appearance.textureID 'nope' names no asset", found)

    def test_schema_violation_is_reported_with_its_path(self):
        record = dict(MINIMAL_BODY, tier="huge")
        write_entry(self.root, "bodies", "ceres", record)
        found = messages(validate.validate(self.root))
        self.assertTrue(any(m.startswith("content/bodies/ceres/record.json: tier: 'huge' is not one of")
                            for m in found), found)

    def test_missing_rotation_is_rejected(self):
        record = dict(MINIMAL_BODY)
        del record["rotation"]
        write_entry(self.root, "bodies", "ceres", record)
        found = messages(validate.validate(self.root))
        self.assertTrue(any("'rotation' is a required property" in m for m in found), found)

    def test_kepler_orbit_angle_unit_must_be_deg(self):
        record = dict(MINIMAL_BODY, orbit=dict(MINIMAL_BODY["orbit"], angleUnit="degrees"))
        write_entry(self.root, "bodies", "ceres", record)
        found = messages(validate.validate(self.root))
        self.assertIn("content/bodies/ceres/record.json: orbit.angleUnit must be 'deg'", found)

    def test_legacy_lunar_orbit_requires_earth_parent(self):
        record = dict(MINIMAL_BODY, parent="jupiter", orbit={
            "model": "legacy-lunar-schlyter", "version": "1",
            "epochJD": 2451545.0, "frame": "earth-fixed", "timeConvention": "tt-as-utc",
            "validityStartJD": 2415020.5, "validityEndJD": 2488069.5,
        })
        write_entry(self.root, "bodies", "ceres", record)
        found = messages(validate.validate(self.root))
        self.assertIn("content/bodies/ceres/record.json: legacy-lunar-schlyter only works for a body "
                      "whose parent is earth", found)

    def test_transit_feed_coverage_order(self):
        record = dict(MINIMAL_FEED, coverage={"minLat": 41.0, "minLon": -74.5, "maxLat": 40.0, "maxLon": -73.5})
        write_entry(self.root, "transit-feeds", "demo", record)
        found = messages(validate.validate(self.root))
        self.assertIn("content/transit-feeds/demo/record.json: coverage.minLat must be less than maxLat", found)

    def test_transit_feed_gps_needs_vehicle_positions(self):
        record = dict(MINIMAL_FEED, realtime={"refreshSeconds": 15, "key": None})
        write_entry(self.root, "transit-feeds", "demo", record)
        found = messages(validate.validate(self.root))
        self.assertIn("content/transit-feeds/demo/record.json: a gps feed needs at least one "
                      "realtime.vehiclePositions URL", found)

    def test_transit_feed_secret_shape(self):
        record = dict(MINIMAL_FEED)
        record["realtime"] = dict(MINIMAL_FEED["realtime"], key={"secret": "TRANSIT_KEY_DEMO"})
        write_entry(self.root, "transit-feeds", "demo", record)
        found = messages(validate.validate(self.root))
        self.assertIn("content/transit-feeds/demo/record.json: realtime.key names exactly one of "
                      "'query' or 'header'", found)
