import tempfile
import unittest
from pathlib import Path

from support import make_root, write_entry, messages
import validate

REPO_CONTENT = Path(__file__).resolve().parents[2] / "content"

MINIMAL_BODY = {
    "kind": "body", "id": "ceres", "tier": "minor", "displayName": "Ceres", "parent": "sun",
    "capabilities": {"requires": ["kepler-standish-table2a/1"]},
    "orbit": {"model": "kepler-standish-table2a", "version": "1"},
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
