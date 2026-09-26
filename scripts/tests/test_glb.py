import json
import struct
import unittest

import support  # noqa: F401  (puts scripts/ on sys.path)
import glb


def build_doc(indices=(0, 1, 2), index_type=5123, buffer_length=None,
              positions=(0, 0, 0, 1, 0, 0, 0, 0, -1), normals=(0, 1, 0, 0, 1, 0, 0, 1, 0),
              nodes=None, scene_nodes=None):
    """The document and BIN chunk behind `tiny_glb`, exposed so tests can mutate
    either before packing: a JSON-shape test corrupts the document, a scene-graph
    test replaces `nodes`/`scene_nodes`, a vertex-data test replaces the floats."""
    position_bytes = struct.pack("<9f", *positions)
    normal_bytes = struct.pack("<9f", *normals)
    fmt = "<%dH" if index_type == 5123 else "<%dI"
    index_bytes = struct.pack(fmt % len(indices), *indices)
    index_bytes += b"\0" * (-len(index_bytes) % 4)
    bin_chunk = position_bytes + normal_bytes + index_bytes
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
        "nodes": nodes if nodes is not None else [{"mesh": 0}],
        "scenes": [{"nodes": scene_nodes if scene_nodes is not None else [0]}],
        "scene": 0,
    }
    return doc, bin_chunk


def pack(doc, bin_chunk: bytes) -> bytes:
    json_bytes = json.dumps(doc).encode()
    json_bytes += b" " * (-len(json_bytes) % 4)
    body = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes + struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def tiny_glb(indices=(0, 1, 2), index_type=5123, buffer_length=None,
             positions=(0, 0, 0, 1, 0, 0, 0, 0, -1), normals=(0, 1, 0, 0, 1, 0, 0, 1, 0),
             nodes=None, scene_nodes=None) -> bytes:
    doc, bin_chunk = build_doc(indices=indices, index_type=index_type, buffer_length=buffer_length,
                               positions=positions, normals=normals, nodes=nodes, scene_nodes=scene_nodes)
    return pack(doc, bin_chunk)


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

    # -- reachability: only nodes walked from the scene's roots count -----

    def test_cycle_is_reported_not_infinite_looped(self):
        nodes = [{"mesh": 0, "children": [1]}, {"children": [0]}]
        problems = glb.check(tiny_glb(nodes=nodes, scene_nodes=[0]))
        self.assertTrue(any("cycle" in message for message in problems))

    def test_unreachable_mesh_is_not_checked(self):
        # Two meshes share POSITION/NORMAL. Mesh 0 (good indices) hangs off
        # node 0, the scene root. Mesh 1 (an out-of-range index) hangs off
        # node 1, which is neither a root nor any other node's child, so the
        # app never reads it and the checker must not reject it either.
        positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 0, -1)
        normals = struct.pack("<9f", 0, 1, 0, 0, 1, 0, 0, 1, 0)
        good_indices = struct.pack("<3H", 0, 1, 2)
        bad_indices = struct.pack("<3H", 0, 1, 9) + b"\0\0"
        bin_chunk = positions + normals + good_indices + bad_indices
        doc = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(bin_chunk)}],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                {"buffer": 0, "byteOffset": 36, "byteLength": 36},
                {"buffer": 0, "byteOffset": 72, "byteLength": 6},
                {"buffer": 0, "byteOffset": 78, "byteLength": 6},
            ],
            "accessors": [
                {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
                {"bufferView": 2, "componentType": 5123, "count": 3, "type": "SCALAR"},
                {"bufferView": 3, "componentType": 5123, "count": 3, "type": "SCALAR"},
            ],
            "meshes": [
                {"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2}]},
                {"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 3}]},
            ],
            "nodes": [{"mesh": 0}, {"mesh": 1}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        }
        self.assertEqual(glb.check(pack(doc, bin_chunk)), [])

    def test_no_triangles_when_nothing_is_reached(self):
        nodes = [{"children": []}]
        self.assertIn("model has no triangles", glb.check(tiny_glb(nodes=nodes, scene_nodes=[0])))

    # -- vertex data of a reached primitive ---------------------------------

    def test_non_finite_position_is_reported(self):
        positions = (float("nan"), 0, 0, 1, 0, 0, 0, 0, -1)
        problems = glb.check(tiny_glb(positions=positions))
        self.assertTrue(any("position" in message and "finite" in message for message in problems))

    def test_zero_length_normal_is_reported(self):
        normals = (0, 0, 0, 0, 1, 0, 0, 1, 0)
        problems = glb.check(tiny_glb(normals=normals))
        self.assertTrue(any("normal" in message for message in problems))

    def test_infinite_normal_is_reported(self):
        normals = (float("inf"), 0, 0, 0, 1, 0, 0, 1, 0)
        problems = glb.check(tiny_glb(normals=normals))
        self.assertTrue(any("normal" in message for message in problems))

    # -- node transforms, structural (every node, reached or not) ----------

    def test_non_affine_matrix_is_rejected(self):
        matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 2]  # bottom-right should be 1
        problems = glb.check(tiny_glb(nodes=[{"mesh": 0, "matrix": matrix}]))
        self.assertTrue(any("affine" in message for message in problems))

    def test_matrix_and_trs_together_is_rejected(self):
        matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        node = {"mesh": 0, "matrix": matrix, "translation": [1, 0, 0]}
        problems = glb.check(tiny_glb(nodes=[node]))
        self.assertTrue(any("matrix and TRS" in message for message in problems))

    def test_zero_length_rotation_is_rejected(self):
        node = {"mesh": 0, "rotation": [0, 0, 0, 0]}
        problems = glb.check(tiny_glb(nodes=[node]))
        self.assertTrue(any("rotation" in message for message in problems))

    def test_singular_transform_is_reported(self):
        node = {"mesh": 0, "scale": [0, 0, 0]}
        problems = glb.check(tiny_glb(nodes=[node]))
        self.assertTrue(any("singular" in message for message in problems))

    def test_identity_trs_defaults_are_acceptable(self):
        # A node with none of matrix/translation/rotation/scale set falls back
        # to the identity transform, same as the app.
        self.assertEqual(glb.check(tiny_glb(nodes=[{"mesh": 0}])), [])

    # -- malformed JSON shapes must be reported, never raise ----------------

    def test_buffer_view_not_an_object(self):
        doc, bin_chunk = build_doc()
        doc["bufferViews"][0] = "not an object"
        problems = glb.check(pack(doc, bin_chunk))
        self.assertTrue(problems)

    def test_attributes_is_a_list(self):
        doc, bin_chunk = build_doc()
        doc["meshes"][0]["primitives"][0]["attributes"] = ["POSITION", "NORMAL"]
        problems = glb.check(pack(doc, bin_chunk))
        self.assertTrue(problems)

    def test_accessor_type_is_a_list(self):
        doc, bin_chunk = build_doc()
        doc["accessors"][0]["type"] = ["VEC3"]
        problems = glb.check(pack(doc, bin_chunk))
        self.assertTrue(problems)

    def test_base_color_factor_is_a_number(self):
        doc, bin_chunk = build_doc()
        doc["materials"] = [{"pbrMetallicRoughness": {"baseColorFactor": 1}}]
        problems = glb.check(pack(doc, bin_chunk))
        self.assertTrue(problems)

    def test_scene_nodes_is_an_int(self):
        doc, bin_chunk = build_doc()
        doc["scenes"][0]["nodes"] = 0
        problems = glb.check(pack(doc, bin_chunk))
        self.assertTrue(problems)

    def test_accessor_not_an_object_does_not_raise(self):
        doc, bin_chunk = build_doc()
        doc["accessors"][1] = 42
        problems = glb.check(pack(doc, bin_chunk))
        self.assertTrue(problems)

    def test_node_children_not_a_list_does_not_raise(self):
        doc, bin_chunk = build_doc()
        doc["nodes"][0]["children"] = "nope"
        problems = glb.check(pack(doc, bin_chunk))
        # Not necessarily a problem on its own (children is optional and empty
        # is the fallback), but it must not raise.
        self.assertIsInstance(problems, list)

    # -- exactInt: integral floats accepted, JSON booleans always rejected --

    def test_integral_float_count_is_accepted(self):
        doc, bin_chunk = build_doc()
        doc["accessors"][2]["count"] = 3.0
        self.assertEqual(glb.check(pack(doc, bin_chunk)), [])

    def test_boolean_scene_index_is_rejected(self):
        doc, bin_chunk = build_doc()
        doc["scene"] = True
        problems = glb.check(pack(doc, bin_chunk))
        self.assertTrue(problems)

    def test_boolean_mode_is_rejected(self):
        doc, bin_chunk = build_doc()
        doc["meshes"][0]["primitives"][0]["mode"] = True
        problems = glb.check(pack(doc, bin_chunk))
        self.assertTrue(problems)
