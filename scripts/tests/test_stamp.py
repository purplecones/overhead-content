import json
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  (puts scripts/ on sys.path)
from test_glb import tiny_glb
import stamp


class StampGLBTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name) / "peregrine"
        self.directory.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_record(self, model_bytes: bytes, byte_limit=0, sha256=""):
        (self.directory / "model.glb").write_bytes(model_bytes)
        record = {
            "kind": "craft", "id": "peregrine",
            "model": {"id": "model", "path": "model.glb", "format": "glb",
                      "byteLimit": byte_limit, "sha256": sha256, "required": True},
        }
        path = self.directory / "record.json"
        path.write_text(json.dumps(record))
        return path

    def test_glb_asset_is_stamped(self):
        model = tiny_glb()
        path = self.write_record(model)
        clean = stamp.stamp_record(path, check_only=False)
        self.assertFalse(clean)
        record = json.loads(path.read_text())
        self.assertEqual(record["model"]["sha256"], stamp.sha256_of(model))
        self.assertEqual(record["model"]["byteLimit"], len(model))
        self.assertNotIn("width", record["model"])
        self.assertNotIn("height", record["model"])

    def test_glb_asset_already_stamped_is_clean(self):
        model = tiny_glb()
        path = self.write_record(model, byte_limit=len(model), sha256=stamp.sha256_of(model))
        self.assertTrue(stamp.stamp_record(path, check_only=False))

    def test_glb_check_reports_without_rewriting(self):
        model = tiny_glb()
        path = self.write_record(model)
        clean = stamp.stamp_record(path, check_only=True)
        self.assertFalse(clean)
        record = json.loads(path.read_text())
        self.assertEqual(record["model"]["sha256"], "")

    def test_declared_glb_but_not_a_glb(self):
        path = self.write_record(b"not actually a glb")
        with self.assertRaises(stamp.StampError) as raised:
            stamp.stamp_record(path, check_only=False)
        self.assertIn("declared glb but the file is not a GLB", str(raised.exception))
