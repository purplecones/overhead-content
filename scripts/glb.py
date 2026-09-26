"""Structural check of a GLB the way the app's loader reads it, minus the
app's former size limits. A model that passes here parses on the phone; one
that fails here is rejected there with the same complaint.

The app supports: glTF 2.0, one buffer equal to the BIN chunk, triangle
primitives with float VEC3 POSITION and NORMAL and uint16 or uint32 SCALAR
indices, optional pbrMetallicRoughness.baseColorFactor, node TRS or matrix
transforms, no sparse accessors, no external buffers, no textures.
"""

from __future__ import annotations

import json
import struct

MAGIC, JSON_CHUNK, BIN_CHUNK = 0x46546C67, 0x4E4F534A, 0x004E4942
COMPONENT_SIZE = {5126: 4, 5123: 2, 5125: 4}
COMPONENT_COUNT = {"VEC3": 3, "SCALAR": 1}


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


def _int(value, label: str, problems: list[str], default=None) -> int | None:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        problems.append(f"{label} must be a non-negative integer")
        return None
    return value


def check(data: bytes) -> list[str]:
    try:
        document, bin_chunk = split(data)
    except ValueError as error:
        return [str(error)]
    problems: list[str] = []
    if not isinstance(document, dict) or (document.get("asset") or {}).get("version") != "2.0":
        return ["asset.version must be \"2.0\""]
    buffers = document.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or buffers[0].get("byteLength") != len(bin_chunk):
        problems.append("buffers[0].byteLength does not match the BIN chunk")
    views = []
    for i, view in enumerate(document.get("bufferViews") or []):
        if view.get("buffer", 0) != 0:
            problems.append(f"bufferViews[{i}]: external buffers are not supported")
        offset = _int(view.get("byteOffset"), f"bufferViews[{i}].byteOffset", problems, 0)
        length = _int(view.get("byteLength"), f"bufferViews[{i}].byteLength", problems)
        stride = view.get("byteStride")
        if stride is not None and (not isinstance(stride, int) or stride < 4 or stride > 256 or stride % 4):
            problems.append(f"bufferViews[{i}].byteStride must be a multiple of 4 between 4 and 256")
            stride = None
        if offset is None or length is None or length == 0 or offset + length > len(bin_chunk):
            problems.append(f"bufferViews[{i}] exceeds the BIN chunk")
            views.append(None)
        else:
            views.append((offset, length, stride))
    accessors = []
    for i, acc in enumerate(document.get("accessors") or []):
        if "sparse" in acc:
            problems.append(f"accessors[{i}]: sparse accessors are not supported")
        view = acc.get("bufferView")
        ctype, atype, count = acc.get("componentType"), acc.get("type"), acc.get("count")
        offset = _int(acc.get("byteOffset"), f"accessors[{i}].byteOffset", problems, 0)
        if ctype not in COMPONENT_SIZE or atype not in COMPONENT_COUNT:
            problems.append(f"accessors[{i}]: only float VEC3 and uint16/uint32 SCALAR are supported")
            accessors.append(None); continue
        if not isinstance(view, int) or view < 0 or view >= len(views) or views[view] is None or not isinstance(count, int) or count <= 0 or offset is None:
            problems.append(f"accessors[{i}] is invalid")
            accessors.append(None); continue
        v_offset, v_length, v_stride = views[view]
        packed = COMPONENT_SIZE[ctype] * COMPONENT_COUNT[atype]
        stride = v_stride or packed
        last = offset + (count - 1) * stride + packed
        if offset % COMPONENT_SIZE[ctype] or stride < packed or last > v_length:
            problems.append(f"accessors[{i}] exceeds its bufferView")
            accessors.append(None); continue
        accessors.append((v_offset + offset, stride, ctype, atype, count))
    materials = document.get("materials") or []
    for i, material in enumerate(materials):
        factor = (material.get("pbrMetallicRoughness") or {}).get("baseColorFactor")
        if factor is not None and (len(factor) != 4 or not all(isinstance(x, (int, float)) for x in factor)):
            problems.append(f"materials[{i}].baseColorFactor must be four numbers")
    meshes = document.get("meshes") or []
    triangles = 0
    for m, mesh in enumerate(meshes):
        prims = mesh.get("primitives") or []
        if not prims:
            problems.append(f"meshes[{m}] has no primitives")
        for p, prim in enumerate(prims):
            label = f"meshes[{m}].primitives[{p}]"
            if prim.get("mode", 4) != 4:
                problems.append(f"{label}: only triangle lists (mode 4) are supported"); continue
            attrs = prim.get("attributes") or {}
            ids = [attrs.get("POSITION"), attrs.get("NORMAL"), prim.get("indices")]
            if any(not isinstance(x, int) or x < 0 or x >= len(accessors) or accessors[x] is None for x in ids):
                problems.append(f"{label} needs POSITION, NORMAL and indices accessors"); continue
            pos, nor, idx = (accessors[x] for x in ids)
            if pos[2:4] != (5126, "VEC3") or nor[2:4] != (5126, "VEC3") or idx[3] != "SCALAR" or idx[2] not in (5123, 5125):
                problems.append(f"{label}: POSITION and NORMAL must be float VEC3 and indices uint16 or uint32 SCALAR"); continue
            if idx[4] % 3:
                problems.append(f"accessor {ids[2]}: index count {idx[4]} is not a multiple of 3"); continue
            if pos[4] != nor[4]:
                problems.append(f"{label}: POSITION and NORMAL counts differ")
            material = prim.get("material")
            if material is not None and (not isinstance(material, int) or material < 0 or material >= len(materials)):
                problems.append(f"{label}: material is out of range")
            fmt = "<H" if idx[2] == 5123 else "<I"
            for n in range(idx[4]):
                value = struct.unpack_from(fmt, bin_chunk, idx[0] + n * idx[1])[0]
                if value >= pos[4]:
                    problems.append(f"accessor {ids[2]}: index {value} is past the {pos[4]} vertices of its primitive"); break
            triangles += idx[4] // 3
    nodes = document.get("nodes") or []
    for n, node in enumerate(nodes):
        mesh = node.get("mesh")
        if mesh is not None and (not isinstance(mesh, int) or mesh < 0 or mesh >= len(meshes)):
            problems.append(f"nodes[{n}].mesh is out of range")
        for child in node.get("children") or []:
            if not isinstance(child, int) or child < 0 or child >= len(nodes):
                problems.append(f"nodes[{n}] has a child out of range")
        if "matrix" in node and any(k in node for k in ("translation", "rotation", "scale")):
            problems.append(f"nodes[{n}] has both matrix and TRS transforms")
    scenes = document.get("scenes") or []
    scene = document.get("scene")
    if not isinstance(scene, int) or scene < 0 or scene >= len(scenes) or not (scenes[scene].get("nodes") or []):
        problems.append("scene is missing or empty")
    elif any(not isinstance(x, int) or x < 0 or x >= len(nodes) for x in scenes[scene]["nodes"]):
        problems.append("scene node is out of range")
    if not problems and triangles == 0:
        problems.append("model has no triangles")
    return problems


def summary(data: bytes) -> dict:
    """Triangle count and the axis-aligned extent of every POSITION accessor,
    in authored units, ignoring node transforms. Enough to sanity-check
    dimensions; the app applies transforms when it draws."""
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
