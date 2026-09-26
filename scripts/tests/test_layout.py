import json
import tempfile
import unittest
from pathlib import Path

from support import make_root, write_entry, write_json, messages
import validate


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_tree_is_valid(self):
        self.assertEqual(validate.validate(self.root), [])

    def test_unknown_kind_key_is_reported(self):
        write_json(self.root / "index.json", {"schemaVersion": 1, "kinds": {"widgets": ["a"]}})
        self.assertIn("index.json: unknown kind 'widgets'", messages(validate.validate(self.root)))

    def test_listed_entry_without_directory(self):
        write_json(self.root / "index.json",
                   {"schemaVersion": 1, "kinds": {"events/solar-eclipses": ["2024-04-08"]}})
        found = messages(validate.validate(self.root))
        self.assertIn("index.json: events/solar-eclipses lists '2024-04-08' but "
                      "events/solar-eclipses/2024-04-08/record.json is missing", found)

    def test_directory_not_listed(self):
        (self.root / "events/solar-eclipses/2024-04-08").mkdir(parents=True)
        (self.root / "events/solar-eclipses/2024-04-08/record.json").write_text("{}")
        found = messages(validate.validate(self.root))
        self.assertIn("index.json: events/solar-eclipses/2024-04-08 exists but is not listed", found)

    def test_duplicate_listing(self):
        write_json(self.root / "index.json",
                   {"schemaVersion": 1, "kinds": {"events/solar-eclipses": ["2024-04-08", "2024-04-08"]}})
        found = messages(validate.validate(self.root))
        self.assertIn("index.json: events/solar-eclipses lists '2024-04-08' twice", found)

    def test_id_must_match_directory(self):
        write_entry(self.root, "events/solar-eclipses", "2024-04-08",
                    {"kind": "solar-eclipse", "id": "2024-04-09"})
        found = messages(validate.validate(self.root))
        self.assertIn("events/solar-eclipses/2024-04-08/record.json: id is '2024-04-09' "
                      "but the directory is '2024-04-08'", found)

    def test_kind_must_match_key(self):
        write_entry(self.root, "events/solar-eclipses", "2024-04-08",
                    {"kind": "body", "id": "2024-04-08"})
        found = messages(validate.validate(self.root))
        self.assertIn("events/solar-eclipses/2024-04-08/record.json: kind is 'body' "
                      "but events/solar-eclipses records are 'solar-eclipse'", found)

    def test_stray_file_and_missing_readme(self):
        directory = write_entry(self.root, "events/solar-eclipses", "2024-04-08",
                                {"kind": "solar-eclipse", "id": "2024-04-08"})
        (directory / "README.md").unlink()
        (directory / "notes.txt").write_text("x")
        found = messages(validate.validate(self.root))
        self.assertIn("events/solar-eclipses/2024-04-08: README.md is missing", found)
        self.assertIn("events/solar-eclipses/2024-04-08/notes.txt: not declared by record.json", found)

    def test_unreadable_record(self):
        directory = write_entry(self.root, "events/solar-eclipses", "2024-04-08", {})
        (directory / "record.json").write_text("{not json")
        found = messages(validate.validate(self.root))
        self.assertTrue(any(m.startswith("events/solar-eclipses/2024-04-08/record.json: not valid JSON")
                            for m in found), found)
