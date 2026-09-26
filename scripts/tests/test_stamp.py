import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  (puts scripts/ on sys.path)
from support import make_root, write_entry
from test_glb import tiny_glb
import stamp


def quietly(function, *args, **kwargs):
    """Run with stdout captured, so the test log shows only test results."""
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


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
        clean = quietly(stamp.stamp_record, path, check_only=False)
        self.assertFalse(clean)
        record = json.loads(path.read_text())
        self.assertEqual(record["model"]["sha256"], stamp.sha256_of(model))
        self.assertEqual(record["model"]["byteLimit"], len(model))
        self.assertNotIn("width", record["model"])
        self.assertNotIn("height", record["model"])

    def test_glb_asset_already_stamped_is_clean(self):
        model = tiny_glb()
        path = self.write_record(model, byte_limit=len(model), sha256=stamp.sha256_of(model))
        self.assertTrue(quietly(stamp.stamp_record, path, check_only=False))

    def test_glb_check_reports_without_rewriting(self):
        model = tiny_glb()
        path = self.write_record(model)
        clean = quietly(stamp.stamp_record, path, check_only=True)
        self.assertFalse(clean)
        record = json.loads(path.read_text())
        self.assertEqual(record["model"]["sha256"], "")

    def test_declared_glb_but_not_a_glb(self):
        path = self.write_record(b"not actually a glb")
        with self.assertRaises(stamp.StampError) as raised:
            quietly(stamp.stamp_record, path, check_only=False)
        self.assertIn("declared glb but the file is not a GLB", str(raised.exception))


class StampErrorReportingTests(unittest.TestCase):
    """A record stamp.py cannot handle is a `path: problem` line and exit 2,
    never a traceback, and the other records are still processed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))
        self.model = tiny_glb()

    def tearDown(self):
        self.tmp.cleanup()

    def craft(self, id: str, model: dict | None = None) -> Path:
        record = {"kind": "craft", "id": id,
                  "model": model if model is not None else
                  {"id": "model", "path": "model.glb", "format": "glb", "byteLimit": 0, "sha256": "",
                   "required": True}}
        return write_entry(self.root, "craft/aircraft", id, record, {"model.glb": self.model})

    def run_main(self, *args) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = stamp.main([*args, str(self.root)])
        return status, out.getvalue(), err.getvalue()

    def test_invalid_json_is_reported_with_its_path(self):
        directory = self.craft("broken")
        (directory / "record.json").write_text("{ not json")
        status, _, err = self.run_main("--check")
        self.assertEqual(status, 2)
        self.assertIn("content/craft/aircraft/broken/record.json: not valid JSON:", err)
        self.assertNotIn("Traceback", err)

    def test_asset_without_path_is_reported_with_its_path(self):
        self.craft("pathless", {"id": "model", "format": "glb", "byteLimit": 0, "sha256": "", "required": True})
        status, _, err = self.run_main()
        self.assertEqual(status, 2)
        self.assertIn("content/craft/aircraft/pathless/record.json: asset 'model' needs a path", err)

    def test_other_records_are_still_stamped(self):
        directory = self.craft("broken")
        (directory / "record.json").write_text("{ not json")
        good = self.craft("good")
        status, _, _ = self.run_main()
        self.assertEqual(status, 2)
        record = json.loads((good / "record.json").read_text())
        self.assertEqual(record["model"]["byteLimit"], len(self.model))

    def test_symlinked_asset_is_refused(self):
        directory = self.craft("linked")
        outside = Path(self.tmp.name) / "outside.glb"
        outside.write_bytes(self.model)
        (directory / "model.glb").unlink()
        os.symlink(outside, directory / "model.glb")
        status, _, err = self.run_main()
        self.assertEqual(status, 2)
        self.assertIn("content/craft/aircraft/linked/record.json: linked/model.glb: is a symlink", err)

    def test_missing_record_is_reported_against_the_index(self):
        directory = self.craft("gone")
        (directory / "record.json").unlink()
        status, _, err = self.run_main("--check")
        self.assertEqual(status, 2)
        self.assertIn("content/index.json: declares craft/aircraft/gone but "
                      "content/craft/aircraft/gone/record.json is missing", err)
