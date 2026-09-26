import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import make_root, write_entry, messages
from test_glb import tiny_glb
import validate


def craft(id="peregrine", **overrides):
    model = tiny_glb()
    record = {
        "kind": "craft", "id": id, "name": id.capitalize(), "licence": "CC0-1.0",
        "model": {"id": "model", "path": "model.glb", "format": "glb", "byteLimit": len(model),
                  "sha256": hashlib.sha256(model).hexdigest(), "required": True},
        "dimensions": {"length": 23.05, "span": 25.3},
        "matches": {"classes": ["airplane"], "types": [], "default": True},
        "provenance": {"sources": ["https://example.com/model"], "attribution": "Example"},
    }
    record.update(overrides)
    return record, {"model.glb": model}


class CraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, domain, id, **overrides):
        record, files = craft(id, **overrides)
        write_entry(self.root, f"craft/{domain}", id, record, files)

    def test_valid_aircraft(self):
        self.add("aircraft", "peregrine")
        self.assertEqual(messages(validate.validate(self.root)), [])

    def test_licence_allowlist(self):
        self.add("aircraft", "peregrine", licence="All rights reserved")
        self.assertTrue(any("licence: 'All rights reserved' is not one of" in m for m in messages(validate.validate(self.root))))

    def test_unknown_class_for_domain(self):
        self.add("vessels", "boat", matches={"classes": ["airplane"], "types": [], "default": False})
        self.assertIn("content/craft/vessels/boat/record.json: class 'airplane' is not a vessels class "
                      "(fishing, tug, sailing, pleasure, high-speed, service, passenger, cargo, tanker, other)",
                      messages(validate.validate(self.root)))

    def test_type_pattern_per_domain(self):
        self.add("aircraft", "bus", matches={"classes": [], "types": ["a320"], "default": False})
        self.assertIn("content/craft/aircraft/bus/record.json: type 'a320' does not match the aircraft "
                      "pattern ^[A-Z0-9]{2,4}$", messages(validate.validate(self.root)))

    def test_must_match_something(self):
        self.add("aircraft", "orphan", matches={"classes": [], "types": [], "default": False})
        self.assertIn("content/craft/aircraft/orphan/record.json: matches must name a class, a type, or default",
                      messages(validate.validate(self.root)))

    def test_duplicate_type_and_default(self):
        self.add("aircraft", "first", matches={"classes": [], "types": ["A320"], "default": True})
        self.add("aircraft", "second", matches={"classes": [], "types": ["A320"], "default": True})
        found = messages(validate.validate(self.root))
        self.assertIn("content/craft/aircraft/second/record.json: type 'A320' is already claimed by first", found)
        self.assertIn("content/craft/aircraft/second/record.json: aircraft already has a default, first", found)

    def test_transit_has_no_types(self):
        self.add("transit", "bus", matches={"classes": ["bus"], "types": ["X"], "default": False})
        self.assertIn("content/craft/transit/bus/record.json: transit craft have no types yet",
                      messages(validate.validate(self.root)))

    def test_broken_glb_is_reported(self):
        record, files = craft("bad")
        files["model.glb"] = tiny_glb(indices=(0, 1, 9))
        record["model"]["sha256"] = hashlib.sha256(files["model.glb"]).hexdigest()
        write_entry(self.root, "craft/aircraft", "bad", record, files)
        self.assertIn("content/craft/aircraft/bad/model.glb: accessor 2: index 9 is past the 3 vertices of its primitive",
                      messages(validate.validate(self.root)))

    def test_glb_check_crash_is_reported_not_raised(self):
        # glb.check is written to report a problem rather than raise, but
        # validate.py must not depend on that: a bug in the checker should
        # surface as a problem, not take the whole run down with it.
        self.add("aircraft", "peregrine")
        with patch("validate.glb.check", side_effect=RuntimeError("boom")):
            found = messages(validate.validate(self.root))
        self.assertIn("content/craft/aircraft/peregrine/model.glb: could not be read as a GLB: boom", found)

    def test_stale_digest_is_reported(self):
        self.add("aircraft", "stale", model={"id": "model", "path": "model.glb", "format": "glb",
                                             "byteLimit": 1, "sha256": "0" * 64, "required": True})
        found = messages(validate.validate(self.root))
        self.assertIn("content/craft/aircraft/stale/record.json: model.glb sha256 or byteLimit is stale; "
                      "run python3 scripts/stamp.py content", found)
