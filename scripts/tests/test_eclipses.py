import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from support import make_root, write_entry, messages
import validate

ECLIPSE = {
    "kind": "solar-eclipse", "id": "2024-04-08", "greatest": "2024-04-08T18:17:15Z", "type": "total",
    "title": "Great North American Eclipse",
    "summary": "The Moon's shadow crossed Mexico, the United States and Canada.",
    "provenance": {
        "source": "NASA Five Millennium Canon of Solar Eclipses, table SE2001-2100",
        "url": "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html",
        "attribution": "Eclipse predictions by Fred Espenak, NASA/GSFC",
    },
}


class EclipseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_record(self):
        write_entry(self.root, "events/solar-eclipses", "2024-04-08", ECLIPSE)
        self.assertEqual(messages(validate.validate(self.root)), [])

    def test_id_must_be_the_utc_date_of_greatest(self):
        write_entry(self.root, "events/solar-eclipses", "2024-04-09", dict(ECLIPSE, id="2024-04-09"))
        found = messages(validate.validate(self.root))
        self.assertIn("content/events/solar-eclipses/2024-04-09/record.json: id must be the UTC date of "
                      "greatest, 2024-04-08", found)

    def test_greatest_must_fall_on_a_new_moon(self):
        # 2024-04-22 is two weeks after the eclipse: a full moon, not a new one.
        wrong = dict(ECLIPSE, id="2024-04-22", greatest="2024-04-22T18:17:15Z")
        write_entry(self.root, "events/solar-eclipses", "2024-04-22", wrong)
        found = messages(validate.validate(self.root))
        self.assertTrue(any(m.startswith("content/events/solar-eclipses/2024-04-22/record.json: greatest is ")
                            and "from the nearest new moon" in m for m in found), found)

    def test_type_enum(self):
        write_entry(self.root, "events/solar-eclipses", "2024-04-08", dict(ECLIPSE, type="partial"))
        found = messages(validate.validate(self.root))
        self.assertTrue(any("type: 'partial' is not one of" in m for m in found), found)

    def test_mean_new_moon_offset(self):
        greatest = datetime(2024, 4, 8, 18, 17, 15, tzinfo=timezone.utc)
        self.assertLess(abs(validate.mean_new_moon_offset_days(greatest)), 1.0)
        off = datetime(2024, 4, 22, 0, 0, tzinfo=timezone.utc)
        self.assertGreater(abs(validate.mean_new_moon_offset_days(off)), 10.0)

    def test_record_over_256_kb_is_rejected(self):
        # The app reads a record.json for events/solar-eclipses too
        # (CelestialContentLayout.maximumRecordBytes), so this is not a
        # bodies-only rule.
        huge = dict(ECLIPSE, provenance=dict(ECLIPSE["provenance"], attribution="x" * (256 * 1024)))
        write_entry(self.root, "events/solar-eclipses", "2024-04-08", huge)
        found = messages(validate.validate(self.root))
        self.assertTrue(any("the app reads at most 262144 bytes of a record.json" in m for m in found), found)
