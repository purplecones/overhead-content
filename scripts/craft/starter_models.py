#!/usr/bin/env python3
"""Builds the repository's starter craft models from boxes and prisms.

The models are original work by the Overhead project, released under CC0, and
exist so every domain has something better than the app's built-in floor
until someone contributes a real model. They also show the conventions a GLB
must follow: Y up, the direction of travel along -Z, flat colours in each
material's baseColorFactor, positions and normals only.

    python3 scripts/craft/starter_models.py content

writes model.glb into each starter's entry directory; run stamp.py after.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path


class Mesh:
    """Flat-shaded triangles grouped by material colour."""

    def __init__(self) -> None:
        self.groups: dict[tuple[float, float, float, float], list[tuple]] = {}

    def triangle(self, colour, a, b, c) -> None:
        ux, uy, uz = (b[i] - a[i] for i in range(3))
        vx, vy, vz = (c[i] - a[i] for i in range(3))
        n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        length = sum(x * x for x in n) ** 0.5
        if length == 0:
            return
        n = tuple(x / length for x in n)
        self.groups.setdefault(colour, []).append((a, b, c, n))

    def quad(self, colour, a, b, c, d) -> None:
        """Counter-clockwise seen from the side the face looks at."""
        self.triangle(colour, a, b, c)
        self.triangle(colour, a, c, d)

    def box(self, colour, x0, x1, y0, y1, z0, z1) -> None:
        p = lambda x, y, z: (x, y, z)
        self.quad(colour, p(x0, y1, z0), p(x0, y1, z1), p(x1, y1, z1), p(x1, y1, z0))  # top
        self.quad(colour, p(x0, y0, z0), p(x1, y0, z0), p(x1, y0, z1), p(x0, y0, z1))  # bottom
        self.quad(colour, p(x1, y0, z0), p(x1, y1, z0), p(x1, y1, z1), p(x1, y0, z1))  # right
        self.quad(colour, p(x0, y0, z0), p(x0, y0, z1), p(x0, y1, z1), p(x0, y1, z0))  # left
        self.quad(colour, p(x0, y0, z1), p(x1, y0, z1), p(x1, y1, z1), p(x0, y1, z1))  # back
        self.quad(colour, p(x0, y0, z0), p(x0, y1, z0), p(x1, y1, z0), p(x1, y0, z0))  # front

    def prism(self, colour, outline, y0, y1) -> None:
        """Extrudes a convex outline of (x, z) points, listed clockwise seen from above."""
        top = [(x, y1, z) for x, z in outline]
        bottom = [(x, y0, z) for x, z in outline]
        for i in range(1, len(outline) - 1):
            self.triangle(colour, top[0], top[i + 1], top[i])
            self.triangle(colour, bottom[0], bottom[i], bottom[i + 1])
        for i in range(len(outline)):
            j = (i + 1) % len(outline)
            self.quad(colour, bottom[i], top[i], top[j], bottom[j])

    def glb(self) -> bytes:
        binary = bytearray()
        views, accessors, materials, primitives = [], [], [], []

        def view(data: bytes, target: int) -> int:
            views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data), "target": target})
            binary.extend(data)
            while len(binary) % 4:
                binary.append(0)
            return len(views) - 1

        for colour, triangles in self.groups.items():
            positions, normals = [], []
            for a, b, c, n in triangles:
                for vertex in (a, b, c):
                    positions.append(vertex)
                    normals.append(n)
            count = len(positions)
            lo = [min(p[i] for p in positions) for i in range(3)]
            hi = [max(p[i] for p in positions) for i in range(3)]
            position_view = view(b"".join(struct.pack("<3f", *p) for p in positions), 34962)
            normal_view = view(b"".join(struct.pack("<3f", *n) for n in normals), 34962)
            index_view = view(struct.pack(f"<{count}I", *range(count)), 34963)
            accessors += [
                {"bufferView": position_view, "componentType": 5126, "count": count, "type": "VEC3",
                 "min": lo, "max": hi},
                {"bufferView": normal_view, "componentType": 5126, "count": count, "type": "VEC3"},
                {"bufferView": index_view, "componentType": 5125, "count": count, "type": "SCALAR"},
            ]
            materials.append({"pbrMetallicRoughness": {"baseColorFactor": list(colour), "metallicFactor": 0,
                                                       "roughnessFactor": 0.8}})
            base = len(accessors) - 3
            primitives.append({"attributes": {"POSITION": base, "NORMAL": base + 1}, "indices": base + 2,
                               "material": len(materials) - 1, "mode": 4})

        document = {
            "asset": {"version": "2.0", "generator": "overhead-content starter_models.py"},
            "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": primitives}], "materials": materials,
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(binary)}],
        }
        text = json.dumps(document, separators=(",", ":")).encode()
        text += b" " * (-len(text) % 4)
        length = 12 + 8 + len(text) + 8 + len(binary)
        return (struct.pack("<III", 0x46546C67, 2, length) + struct.pack("<II", len(text), 0x4E4F534A) + text
                + struct.pack("<II", len(binary), 0x004E4942) + bytes(binary))


def linear(r: int, g: int, b: int) -> tuple[float, float, float, float]:
    """glTF colours are linear; these are picked in sRGB."""
    f = lambda c: round(((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92, 4)
    return (f(r), f(g), f(b), 1.0)


GLASS = linear(38, 48, 60)
TYRE = linear(30, 30, 32)


def bus() -> Mesh:
    """A 12 m city bus, 2.55 m wide and 3.2 m tall."""
    m, w, body, roof = Mesh(), 1.275, linear(40, 96, 170), linear(225, 228, 232)
    m.box(body, -w, w, 0.35, 1.3, -6, 6)
    m.box(GLASS, -w, w, 1.3, 2.4, -5.7, 5.8)
    m.box(body, -w, w, 1.3, 2.4, 5.8, 6)
    m.box(GLASS, -w + 0.05, w - 0.05, 1.0, 2.5, -6.02, -5.7)  # windscreen
    m.box(roof, -w, w, 2.4, 2.9, -6, 6)
    m.box(roof, -0.9, 0.9, 2.9, 3.2, -1, 3.5)  # roof equipment
    for z in (-3.9, 3.2):
        for x in (-w + 0.02, w - 0.4):
            m.box(TYRE, x, x + 0.38, 0, 0.9, z - 0.5, z + 0.5)
    return m


def subway_car() -> Mesh:
    """An 18 m subway car, 3.05 m wide and 3.7 m tall."""
    m, w, steel, stripe = Mesh(), 1.525, linear(176, 182, 188), linear(0, 57, 166)
    m.box(steel, -w, w, 0.8, 1.9, -9, 9)
    m.box(stripe, -w - 0.01, w + 0.01, 1.75, 1.95, -9, 9)
    m.box(GLASS, -w, w, 1.95, 2.8, -8.6, 8.6)
    m.box(steel, -w, w, 1.95, 2.8, 8.6, 9)
    m.box(GLASS, -w + 0.1, w - 0.1, 1.95, 2.9, -9.02, -8.6)
    m.box(steel, -w, w, 2.8, 3.7, -9, 9)
    for z in (-6.5, 6.5):
        m.box(TYRE, -1.2, 1.2, 0, 0.8, z - 1.2, z + 1.2)  # bogies
    return m


def cargo_ship() -> Mesh:
    """A 180 m container ship above the waterline, 30 m in the beam."""
    m, hull, deck = Mesh(), linear(150, 40, 36), linear(90, 96, 100)
    b = 15.0
    outline = [(0, -90), (b, -62), (b, 84), (b - 3, 90), (-b + 3, 90), (-b, 84), (-b, -62)]
    m.prism(hull, outline, 0, 12)
    m.prism(deck, [(x * 0.97, z * 0.99) for x, z in outline], 12, 12.4)
    white = linear(236, 238, 240)
    m.box(white, -12, 12, 12.4, 36, 58, 74)  # accommodation block
    m.box(GLASS, -12.1, 12.1, 32, 34, 57.9, 74.1)
    m.box(linear(40, 40, 44), -2, 2, 36, 44, 66, 70)  # funnel
    colours = [linear(196, 62, 44), linear(40, 92, 160), linear(230, 170, 40), linear(70, 130, 80),
               linear(120, 120, 130)]
    for row, z in enumerate(range(-50, 52, 14)):
        for column, x in enumerate(range(-12, 12, 3)):
            height = 2.6 * (2 + (row + column) % 3)
            m.box(colours[(row * 3 + column) % len(colours)], x + 0.1, x + 2.9, 12.4, 12.4 + height, z, z + 12.2)
    return m


STARTERS = {
    "transit/starter-bus": bus,
    "transit/starter-subway-car": subway_car,
    "vessels/starter-cargo-ship": cargo_ship,
}


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "content")
    for path, build in STARTERS.items():
        directory = root / "craft" / path
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "model.glb").write_bytes(build().glb())
        print(directory / "model.glb")


if __name__ == "__main__":
    main()
