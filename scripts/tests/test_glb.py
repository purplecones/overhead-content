import json
import struct
import unittest

import support  # noqa: F401  (puts scripts/ on sys.path)
import glb


def tiny_glb(indices=(0, 1, 2), index_type=5123, buffer_length=None) -> bytes:
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 0, -1)
    normals = struct.pack("<9f", 0, 1, 0, 0, 1, 0, 0, 1, 0)
    fmt = "<%dH" if index_type == 5123 else "<%dI"
    index_bytes = struct.pack(fmt % len(indices), *indices)
    index_bytes += b"\0" * (-len(index_bytes) % 4)
    bin_chunk = positions + normals + index_bytes
    doc = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": buffer_length if buffer_length is not None else len(bin_chunk)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 36},
            {"buffer": 0, "byteOffset": 72, "byteLength": len(index_bytes)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [0, 0, -1], "max": [1, 0, 0]},
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": index_type, "count": len(indices), "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    json_bytes = json.dumps(doc).encode()
    json_bytes += b" " * (-len(json_bytes) % 4)
    body = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes + struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


class GLBTests(unittest.TestCase):
    def test_tiny_model_is_acceptable(self):
        self.assertEqual(glb.check(tiny_glb()), [])
        self.assertEqual(glb.summary(tiny_glb())["triangles"], 1)

    def test_bad_magic(self):
        data = bytearray(tiny_glb()); data[0] = 0
        self.assertIn("not a GLB: bad header", glb.check(bytes(data)))

    def test_index_out_of_range(self):
        self.assertIn("accessor 2: index 7 is past the 3 vertices of its primitive", glb.check(tiny_glb(indices=(0, 1, 7))))

    def test_index_count_not_triangles(self):
        self.assertIn("accessor 2: index count 4 is not a multiple of 3", glb.check(tiny_glb(indices=(0, 1, 2, 0))))

    def test_buffer_length_mismatch(self):
        self.assertIn("buffers[0].byteLength does not match the BIN chunk", glb.check(tiny_glb(buffer_length=1)))

    def test_uint32_indices(self):
        self.assertEqual(glb.check(tiny_glb(index_type=5125)), [])

    def test_peregrine_from_the_app_is_acceptable(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "content/craft/aircraft/peregrine/model.glb"
        if not path.is_file():
            self.skipTest("Peregrine not yet imported")
        data = path.read_bytes()
        self.assertEqual(glb.check(data), [])
        extent = glb.summary(data)["extent"]
        self.assertAlmostEqual(extent[0], 25.3, places=1)
        self.assertAlmostEqual(extent[2], 23.05, places=1)
