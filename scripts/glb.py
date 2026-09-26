"""Structural check of a GLB, mirroring the app's loader (GlobeGLB.swift and
GlobeAircraftAsset.swift) minus its former count and byte maximums. A model
that fails here is rejected by the app for a related reason; the messages
below are this checker's own wording, not the app's.

The app supports: glTF 2.0, one buffer equal to the BIN chunk, triangle
primitives with float VEC3 POSITION and NORMAL and uint16 or uint32 SCALAR
indices, optional pbrMetallicRoughness.baseColorFactor, node TRS or matrix
transforms, no sparse accessors, no external buffers, no textures.

Two things the app does that a naive reader would miss:

- Every field the app treats as an integer index goes through its `exactInt`,
  which accepts a JSON number only when it is finite and has no fractional
  part (so `3.0` is fine, `3.5` is not) and always rejects a JSON boolean,
  even though `true`/`false` decode to numbers in some JSON libraries. `_int`
  and `_exact_int` below mirror that.
- Only nodes reached by walking the active scene's `nodes` from its roots,
  through `children`, are ever read for vertex data; an unreachable node's
  mesh is validated for shape (right accessor types, triangle-sized index
  count) but never for its actual vertex values, because the app never gets
  there either. The walk also matches the app's cycle guard: revisiting a
  node already on the current path is reported, not followed forever.
"""

from __future__ import annotations

import json
import math
import struct

MAGIC, JSON_CHUNK, BIN_CHUNK = 0x46546C67, 0x4E4F534A, 0x004E4942
COMPONENT_SIZE = {5126: 4, 5123: 2, 5125: 4}
COMPONENT_COUNT = {"VEC3": 3, "SCALAR": 1}
SINGULAR_DETERMINANT = 1e-12


def split(data: bytes) -> tuple[dict, bytes]:
    if len(data) < 20 or struct.unpack_from("<III", data, 0)[:2] != (MAGIC, 2) or struct.unpack_from("<I", data, 8)[0] != len(data):
        raise ValueError("not a GLB: bad header")
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != JSON_CHUNK or 20 + json_length > len(data):
        raise ValueError("JSON chunk must come first and fit the file")
    cursor = 20 + json_length
    if cursor + 8 > len(data):
        raise ValueError("missing BIN chunk")
    bin_length, bin_type = struct.unpack_from("<II", data, cursor)
    if bin_type != BIN_CHUNK or cursor + 8 + bin_length != len(data):
        raise ValueError("BIN chunk must follow JSON and end the file")
    try:
        document = json.loads(data[20:20 + json_length].rstrip(b"\0 "))
    except ValueError as error:
        raise ValueError(f"JSON chunk is not valid JSON: {error}") from error
    return document, data[cursor + 8:cursor + 8 + bin_length]


# -- defensive JSON access: every one of these reports a problem and returns
# a safe fallback instead of raising, so a malformed document is a finding,
# never a traceback. ---------------------------------------------------------

def _dict_or_none(value, label: str, problems: list[str]):
    if not isinstance(value, dict):
        problems.append(f"{label} must be an object")
        return None
    return value


def _list_or_empty(value, label: str, problems: list[str], required: bool = True):
    """A required array reports a problem when the value is missing or the
    wrong type, mirroring the app's `guard let ... as? [Any] else { throw }`.
    An optional array (`required=False`) mirrors `as? [Any] ?? []`: anything
    that is not already an array, present or absent, silently becomes empty,
    because that is what the app itself does with it."""
    if isinstance(value, list):
        return value
    if required:
        problems.append(f"{label} must be an array")
    return []


def _exact_int(value, label: str, problems: list[str]):
    """Mirrors the app's exactInt: an int, or a finite float with no
    fractional part; a JSON boolean is never accepted even though it is
    numeric in Python."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(f"{label} must be an integer")
        return None
    if isinstance(value, float) and (not math.isfinite(value) or value != int(value)):
        problems.append(f"{label} must be an integer")
        return None
    return int(value)


def _int(value, label: str, problems: list[str], default: int | None = None):
    if value is None and default is not None:
        return default
    result = _exact_int(value, label, problems)
    if result is None:
        return None
    if result < 0:
        problems.append(f"{label} must be a non-negative integer")
        return None
    return result


def _finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _numbers(value, count: int, label: str, problems: list[str]):
    if not isinstance(value, list) or len(value) != count or not all(_finite_number(x) for x in value):
        problems.append(f"{label} must be {count} finite numbers")
        return None
    return [float(x) for x in value]


# -- 4x4 / 3x3 matrix helpers, glTF's column-major layout: a flat 16-tuple
# where element c*4+r is row r, column c. Positions and normals stay in
# authored units; only the composed node transform is applied, as the app
# does, to catch a transform that turns finite authored data into non-finite
# or degenerate on-screen data. --------------------------------------------

def _identity() -> tuple[float, ...]:
    return (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def _mat_mul(a, b):
    def get(m, r, c):
        return m[c * 4 + r]
    result = [0.0] * 16
    for c in range(4):
        for r in range(4):
            result[c * 4 + r] = sum(get(a, r, k) * get(b, k, c) for k in range(4))
    return tuple(result)


def _mat_point(m, point):
    x, y, z = point
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def _linear3(m):
    """The rotation/scale part of an affine 4x4, as three rows."""
    return ((m[0], m[4], m[8]), (m[1], m[5], m[9]), (m[2], m[6], m[10]))


def _det3(rows):
    (a, b, c), (d, e, f), (g, h, i) = rows
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _normal_matrix(rows, det):
    """transpose(inverse(rows)), the standard transform for normals under a
    non-uniform scale or shear; undefined when `rows` is singular."""
    (a, b, c), (d, e, f), (g, h, i) = rows
    inverse = (
        ((e * i - f * h) / det, -(d * i - f * g) / det, (d * h - e * g) / det),
        (-(b * i - c * h) / det, (a * i - c * g) / det, -(a * h - b * g) / det),
        ((b * f - c * e) / det, -(a * f - c * d) / det, (a * e - b * d) / det),
    )
    return tuple(tuple(inverse[c][r] for c in range(3)) for r in range(3))


def _apply3(rows, vector):
    return tuple(sum(rows[r][c] * vector[c] for c in range(3)) for r in range(3))


def _node_transform(node: dict, label: str, problems: list[str]):
    """Mirrors nodeTransform: a matrix (validated affine) or TRS (validated
    finite, with a non-zero rotation quaternion), defaulting to identity."""
    has_matrix = "matrix" in node
    trs_keys = [key for key in ("translation", "rotation", "scale") if key in node]
    if has_matrix:
        if trs_keys:
            problems.append(f"{label} has both matrix and TRS transforms")
            return None
        values = _numbers(node.get("matrix"), 16, f"{label}.matrix", problems)
        if values is None:
            return None
        if values[3] != 0 or values[7] != 0 or values[11] != 0 or values[15] != 1:
            problems.append(f"{label}.matrix is not affine (its bottom row must be 0, 0, 0, 1)")
            return None
        return tuple(values)
    translation = _numbers(node.get("translation", [0, 0, 0]), 3, f"{label}.translation", problems)
    rotation = _numbers(node.get("rotation", [0, 0, 0, 1]), 4, f"{label}.rotation", problems)
    scale = _numbers(node.get("scale", [1, 1, 1]), 3, f"{label}.scale", problems)
    if translation is None or rotation is None or scale is None:
        return None
    length = math.sqrt(sum(v * v for v in rotation))
    if not math.isfinite(length) or length <= 0:
        problems.append(f"{label}.rotation must have a non-zero length")
        return None
    x, y, z, w = (v / length for v in rotation)
    sx, sy, sz = scale
    return (
        (1 - 2 * (y * y + z * z)) * sx, (2 * (x * y + z * w)) * sx, (2 * (x * z - y * w)) * sx, 0.0,
        (2 * (x * y - z * w)) * sy, (1 - 2 * (x * x + z * z)) * sy, (2 * (y * z + x * w)) * sy, 0.0,
        (2 * (x * z + y * w)) * sz, (2 * (y * z - x * w)) * sz, (1 - 2 * (x * x + y * y)) * sz, 0.0,
        translation[0], translation[1], translation[2], 1.0,
    )


def check(data: bytes) -> list[str]:
    try:
        document, bin_chunk = split(data)
    except ValueError as error:
        return [str(error)]
    if not isinstance(document, dict):
        return ["the GLB's JSON chunk must decode to an object"]
    asset = document.get("asset")
    version = asset.get("version") if isinstance(asset, dict) else None
    if version != "2.0":
        return ["asset.version must be \"2.0\""]

    problems: list[str] = []

    # -- buffers: exactly one, matching the BIN chunk -----------------------
    buffers = document.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1:
        problems.append("buffers must be an array with exactly one buffer")
    else:
        buffer0 = _dict_or_none(buffers[0], "buffers[0]", problems)
        length = _int(buffer0.get("byteLength"), "buffers[0].byteLength", problems) if buffer0 is not None else None
        if length is None or length != len(bin_chunk):
            problems.append("buffers[0].byteLength does not match the BIN chunk")

    # -- bufferViews ----------------------------------------------------------
    views = []
    for i, raw in enumerate(_list_or_empty(document.get("bufferViews"), "bufferViews", problems)):
        view = _dict_or_none(raw, f"bufferViews[{i}]", problems)
        if view is None:
            views.append(None)
            continue
        buffer_index = _exact_int(view.get("buffer", 0), f"bufferViews[{i}].buffer", problems)
        if buffer_index is not None and buffer_index != 0:
            problems.append(f"bufferViews[{i}]: external buffers are not supported")
        offset = _int(view.get("byteOffset"), f"bufferViews[{i}].byteOffset", problems, 0)
        length = _int(view.get("byteLength"), f"bufferViews[{i}].byteLength", problems)
        stride = None
        if view.get("byteStride") is not None:
            stride = _exact_int(view.get("byteStride"), f"bufferViews[{i}].byteStride", problems)
            if stride is None or stride < 4 or stride > 256 or stride % 4:
                problems.append(f"bufferViews[{i}].byteStride must be a multiple of 4 between 4 and 256")
                stride = None
        if offset is None or length is None or length == 0 or offset + length > len(bin_chunk):
            problems.append(f"bufferViews[{i}] exceeds the BIN chunk")
            views.append(None)
        else:
            views.append((offset, length, stride))

    # -- accessors --------------------------------------------------------------
    accessors = []
    for i, raw in enumerate(_list_or_empty(document.get("accessors"), "accessors", problems)):
        acc = _dict_or_none(raw, f"accessors[{i}]", problems)
        if acc is None:
            accessors.append(None)
            continue
        if "sparse" in acc:
            problems.append(f"accessors[{i}]: sparse accessors are not supported")
        ctype = _exact_int(acc.get("componentType"), f"accessors[{i}].componentType", problems)
        atype = acc.get("type")
        count = _exact_int(acc.get("count"), f"accessors[{i}].count", problems)
        view_index = _exact_int(acc.get("bufferView"), f"accessors[{i}].bufferView", problems)
        offset = _int(acc.get("byteOffset"), f"accessors[{i}].byteOffset", problems, 0)
        valid_component = ctype in COMPONENT_SIZE if ctype is not None else False
        valid_type = isinstance(atype, str) and atype in COMPONENT_COUNT
        if not valid_component or not valid_type:
            problems.append(f"accessors[{i}]: only float VEC3 and uint16/uint32 SCALAR are supported")
            accessors.append(None)
            continue
        if (view_index is None or view_index < 0 or view_index >= len(views) or views[view_index] is None
                or count is None or count <= 0 or offset is None):
            problems.append(f"accessors[{i}] is invalid")
            accessors.append(None)
            continue
        v_offset, v_length, v_stride = views[view_index]
        packed = COMPONENT_SIZE[ctype] * COMPONENT_COUNT[atype]
        stride = v_stride or packed
        last = offset + (count - 1) * stride + packed
        if offset % COMPONENT_SIZE[ctype] or stride < packed or last > v_length:
            problems.append(f"accessors[{i}] exceeds its bufferView")
            accessors.append(None)
            continue
        accessors.append((v_offset + offset, stride, ctype, atype, count))

    # -- materials ----------------------------------------------------------------
    materials = []
    for i, raw in enumerate(_list_or_empty(document.get("materials"), "materials", problems, required=False)):
        material = _dict_or_none(raw, f"materials[{i}]", problems)
        materials.append(material)
        if material is None:
            continue
        # pbrMetallicRoughness is read with an `if let`, not a `guard`: a
        # wrongly-typed value is silently ignored, not an error, so this only
        # checks baseColorFactor when pbrMetallicRoughness is actually a dict.
        pbr = material.get("pbrMetallicRoughness")
        if isinstance(pbr, dict) and pbr.get("baseColorFactor") is not None:
            _numbers(pbr["baseColorFactor"], 4, f"materials[{i}].baseColorFactor", problems)

    # -- meshes: structural checks apply to every mesh, reached or not, the way
    # the app's parseMeshes validates the whole array before any scene walk. ---
    meshes = []
    for m, raw in enumerate(_list_or_empty(document.get("meshes"), "meshes", problems)):
        mesh = _dict_or_none(raw, f"meshes[{m}]", problems)
        if mesh is None:
            meshes.append([])
            continue
        raw_primitives = _list_or_empty(mesh.get("primitives"), f"meshes[{m}].primitives", problems)
        if not raw_primitives:
            problems.append(f"meshes[{m}] has no primitives")
        primitives = []
        for p, raw_primitive in enumerate(raw_primitives):
            label = f"meshes[{m}].primitives[{p}]"
            primitive = _dict_or_none(raw_primitive, label, problems)
            if primitive is None:
                primitives.append(None)
                continue
            mode = _exact_int(primitive["mode"], f"{label}.mode", problems) if "mode" in primitive else 4
            if mode != 4:
                problems.append(f"{label}: only triangle lists (mode 4) are supported")
                primitives.append(None)
                continue
            attributes = _dict_or_none(primitive.get("attributes"), f"{label}.attributes", problems)
            if attributes is None:
                primitives.append(None)
                continue
            position = _exact_int(attributes.get("POSITION"), f"{label}.attributes.POSITION", problems)
            normal = _exact_int(attributes.get("NORMAL"), f"{label}.attributes.NORMAL", problems)
            indices = _exact_int(primitive.get("indices"), f"{label}.indices", problems)
            ids = (position, normal, indices)
            if any(x is None or x < 0 or x >= len(accessors) or accessors[x] is None for x in ids):
                problems.append(f"{label} needs POSITION, NORMAL and indices accessors")
                primitives.append(None)
                continue
            pos, nor, idx = (accessors[x] for x in ids)
            if pos[2:4] != (5126, "VEC3") or nor[2:4] != (5126, "VEC3") or idx[3] != "SCALAR" or idx[2] not in (5123, 5125):
                problems.append(f"{label}: POSITION and NORMAL must be float VEC3 and indices uint16 or uint32 SCALAR")
                primitives.append(None)
                continue
            if idx[4] % 3:
                problems.append(f"accessor {indices}: index count {idx[4]} is not a multiple of 3")
                primitives.append(None)
                continue
            material_index = None
            if "material" in primitive:
                material_index = _exact_int(primitive.get("material"), f"{label}.material", problems)
                if material_index is None or material_index < 0 or material_index >= len(materials):
                    problems.append(f"{label}: material is out of range")
                    material_index = None
            primitives.append({"position": position, "normal": normal, "indices": indices, "material": material_index})
        meshes.append(primitives)

    # -- nodes: structural checks (mesh index, children, transform) apply to
    # every node, reached or not, the way parseNodes validates the whole array. -
    nodes = []
    raw_nodes = _list_or_empty(document.get("nodes"), "nodes", problems)
    for n, raw in enumerate(raw_nodes):
        node = _dict_or_none(raw, f"nodes[{n}]", problems)
        if node is None:
            nodes.append(None)
            continue
        mesh_index = None
        if "mesh" in node:
            mesh_index = _exact_int(node.get("mesh"), f"nodes[{n}].mesh", problems)
            if mesh_index is None or mesh_index < 0 or mesh_index >= len(meshes):
                problems.append(f"nodes[{n}].mesh is out of range")
                mesh_index = None
        children = []
        for raw_child in _list_or_empty(node.get("children"), f"nodes[{n}].children", problems, required=False):
            child = _exact_int(raw_child, f"nodes[{n}] child", problems)
            if child is None:
                continue
            if child < 0 or child >= len(raw_nodes):
                problems.append(f"nodes[{n}] has a child out of range")
                continue
            children.append(child)
        transform = _node_transform(node, f"nodes[{n}]", problems)
        nodes.append({"mesh": mesh_index, "children": children, "transform": transform})

    # -- scene: the active scene's roots, each a valid node index ------------
    scenes = _list_or_empty(document.get("scenes"), "scenes", problems)
    scene_index = _exact_int(document.get("scene"), "scene", problems)
    scene_roots: list[int] = []
    scene = None
    if scene_index is not None and 0 <= scene_index < len(scenes):
        scene = _dict_or_none(scenes[scene_index], f"scenes[{scene_index}]", problems)
    if scene is None:
        problems.append("scene is missing or empty")
    else:
        raw_scene_nodes = _list_or_empty(scene.get("nodes"), f"scenes[{scene_index}].nodes", problems)
        if not raw_scene_nodes:
            problems.append("scene is missing or empty")
        for raw_root in raw_scene_nodes:
            root = _exact_int(raw_root, "scene node", problems)
            if root is None or root < 0 or root >= len(nodes):
                problems.append("scene node is out of range")
                continue
            scene_roots.append(root)

    # -- walk the scene graph from its roots, cycle-checked; only a reached
    # mesh's vertex data is read, the way the app's own `visit` does. --------
    triangles = 0
    active: set[int] = set()

    def check_mesh(mesh_index: int, node_index: int, world: tuple[float, ...]) -> None:
        nonlocal triangles
        linear = _linear3(world)
        determinant = _det3(linear)
        singular = not math.isfinite(determinant) or abs(determinant) <= SINGULAR_DETERMINANT
        if singular:
            problems.append(f"nodes[{node_index}]: the composed transform is singular")
        normal_matrix = None if singular else _normal_matrix(linear, determinant)
        for p, primitive in enumerate(meshes[mesh_index]):
            if primitive is None:
                continue
            label = f"meshes[{mesh_index}].primitives[{p}]"
            pos = accessors[primitive["position"]]
            nor = accessors[primitive["normal"]]
            idx = accessors[primitive["indices"]]
            if pos[4] != nor[4]:
                problems.append(f"{label}: POSITION and NORMAL counts differ")
                continue
            element_count = pos[4]
            broken_vertex = False
            for element in range(element_count):
                position = struct.unpack_from("<3f", bin_chunk, pos[0] + element * pos[1])
                world_position = _mat_point(world, position)
                if not all(math.isfinite(v) for v in world_position):
                    problems.append(f"{label}: vertex {element} position is not finite")
                    broken_vertex = True
                    break
                if normal_matrix is not None:
                    normal = struct.unpack_from("<3f", bin_chunk, nor[0] + element * nor[1])
                    world_normal = _apply3(normal_matrix, normal)
                    normal_length = math.sqrt(sum(v * v for v in world_normal))
                    if not math.isfinite(normal_length) or normal_length == 0:
                        problems.append(f"{label}: vertex {element} normal is not finite or has zero length")
                        broken_vertex = True
                        break
            if broken_vertex:
                continue
            fmt = "<H" if idx[2] == 5123 else "<I"
            broken_index = False
            for element in range(idx[4]):
                value = struct.unpack_from(fmt, bin_chunk, idx[0] + element * idx[1])[0]
                if value >= element_count:
                    problems.append(f"accessor {primitive['indices']}: index {value} is past the "
                                     f"{element_count} vertices of its primitive")
                    broken_index = True
                    break
            if broken_index:
                continue
            triangles += idx[4] // 3

    def visit(node_index: int, parent: tuple[float, ...]) -> None:
        if node_index in active:
            problems.append(f"nodes[{node_index}]: the node graph contains a cycle")
            return
        node = nodes[node_index]
        if node is None:
            return
        active.add(node_index)
        try:
            world = _mat_mul(parent, node["transform"]) if node["transform"] is not None else parent
            if node["mesh"] is not None:
                check_mesh(node["mesh"], node_index, world)
            for child in node["children"]:
                visit(child, world)
        finally:
            active.discard(node_index)

    for root in scene_roots:
        visit(root, _identity())

    if not problems and triangles == 0:
        problems.append("model has no triangles")
    return problems


def summary(data: bytes) -> dict:
    """Triangle count and the axis-aligned extent of every POSITION accessor,
    in authored units, ignoring node transforms. Enough to sanity-check
    dimensions; the app applies transforms when it draws. Unlike `check`,
    this reads every mesh regardless of reachability, since it is a summary
    of the file's content, not a verdict on what the app would load."""
    document, bin_chunk = split(data)
    lo, hi, triangles = [float("inf")] * 3, [float("-inf")] * 3, 0
    views = document.get("bufferViews") or []
    accessors = document.get("accessors") or []
    for mesh in document.get("meshes") or []:
        for prim in mesh.get("primitives") or []:
            pos = accessors[prim["attributes"]["POSITION"]]
            view = views[pos["bufferView"]]
            stride = view.get("byteStride") or 12
            base = view.get("byteOffset", 0) + pos.get("byteOffset", 0)
            for n in range(pos["count"]):
                x, y, z = struct.unpack_from("<3f", bin_chunk, base + n * stride)
                for axis, value in enumerate((x, y, z)):
                    lo[axis], hi[axis] = min(lo[axis], value), max(hi[axis], value)
            triangles += accessors[prim["indices"]]["count"] // 3
    return {"triangles": triangles, "extent": tuple(h - l for l, h in zip(lo, hi))}
