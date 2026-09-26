"""Body rules that mirror the app's admission.

Shipped app builds drop every body when one body record fails admission, so
each test here is a record the app would reject and validate.py must too.
"""

import copy
import os
import tempfile
import unittest
from pathlib import Path

from support import make_root, write_entry, messages
from test_existing_kinds import MINIMAL_BODY
import validate

PATH = "content/bodies/ceres/record.json"
FAKE_JPEG = b"\xff\xd8\xff\xd9"


def body(id="ceres", **changes) -> dict:
    record = copy.deepcopy(MINIMAL_BODY)
    record["id"] = id
    record.update(changes)
    return record


def major(id: str, parent: str = "sun", asset_id: str | None = None) -> dict:
    record = body(id, tier="major", parent=parent,
                  capabilities={"requires": ["kepler-standish-table2a/1", "iau-linear/1", "lambert/1"]})
    asset_id = asset_id or f"{id}-2k"
    record["appearance"]["textureID"] = asset_id
    record["assets"] = [{"id": asset_id, "path": "texture.jpg", "format": "jpeg", "width": 2048, "height": 1024,
                         "byteLimit": len(FAKE_JPEG), "sha256": "0" * 64, "required": False}]
    return record


class BodyAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def found(self, record: dict, id: str = "ceres") -> list[str]:
        files = {"texture.jpg": FAKE_JPEG} if record.get("assets") else None
        write_entry(self.root, "bodies", id, record, files)
        return messages(validate.validate(self.root))

    def assertReported(self, found: list[str], fragment: str, path: str = PATH):
        self.assertTrue(any(m.startswith(path + ": ") and fragment in m for m in found), found)

    # C1: record textures

    def test_minimal_major_body_admits(self):
        self.assertEqual(self.found(major("ceres")), [])

    def test_png_record_texture_is_rejected(self):
        record = major("ceres")
        record["assets"][0].update(path="texture.png", format="png")
        write_entry(self.root, "bodies", "ceres", record, {"texture.png": b"\x89PNG"})
        found = messages(validate.validate(self.root))
        self.assertReported(found, "assets.0.format: 'jpeg' was expected")
        self.assertReported(found, "assets.0.path: 'texture.png' does not match")

    def test_4096_by_2048_record_texture_is_rejected(self):
        record = major("ceres")
        record["assets"][0].update(width=4096, height=2048)
        found = self.found(record)
        self.assertReported(found, "assets.0.width: 4096 is not one of")
        self.assertReported(found, "assets.0.height: 2048 is not one of")

    def test_non_power_of_two_record_texture_is_rejected(self):
        record = major("ceres")
        record["assets"][0].update(width=2000, height=1000)
        self.assertReported(self.found(record), "assets.0.width: 2000 is not one of")

    def test_record_texture_over_16_mib_is_rejected(self):
        record = major("ceres")
        record["assets"][0]["byteLimit"] = 16 * 1024 * 1024 + 1
        self.assertReported(self.found(record), "assets.0.byteLimit: 16777217 is greater than the maximum")

    # I1: per-record admission

    def test_lambert_without_absolute_magnitude_is_rejected(self):
        record = body()
        del record["appearance"]["absoluteMagnitude"]
        self.assertReported(self.found(record), "appearance.absoluteMagnitude is required for lambert photometry")

    def test_emissive_may_omit_absolute_magnitude(self):
        record = body()
        del record["appearance"]["absoluteMagnitude"]
        record["appearance"]["photometry"] = {"model": "emissive", "version": "1"}
        self.assertEqual(self.found(record), [])

    def test_sphere_needs_equal_radii(self):
        record = body()
        record["appearance"]["presentation"] = "sphere"
        self.assertReported(self.found(record), "presentation sphere needs equatorialRadiusM equal to polarRadiusM")

    def test_ellipsoid_needs_polar_below_equatorial(self):
        record = body(polarRadiusM=MINIMAL_BODY["equatorialRadiusM"])
        self.assertReported(self.found(record), "presentation ellipsoid needs polarRadiusM below equatorialRadiusM")

    def test_polar_above_equatorial_is_rejected(self):
        record = body(polarRadiusM=MINIMAL_BODY["equatorialRadiusM"] * 2)
        self.assertReported(self.found(record), "polarRadiusM must not exceed equatorialRadiusM")

    def test_radius_above_app_bound_is_rejected(self):
        record = body(equatorialRadiusM=2e10)
        self.assertReported(self.found(record), "equatorialRadiusM: 20000000000.0 is greater than the maximum")

    def test_gm_above_app_bound_is_rejected(self):
        record = body(gravitationalParameterM3S2=2e25)
        self.assertReported(self.found(record), "gravitationalParameterM3S2: 2e+25 is greater than the maximum")

    def test_albedo_scale_above_100_is_rejected(self):
        record = body()
        record["appearance"]["albedoScale"] = 101
        self.assertReported(self.found(record), "appearance.albedoScale: 101 is greater than the maximum of 100")

    def test_orbit_validity_must_be_ordered(self):
        record = body()
        record["orbit"]["validityStartJD"] = record["orbit"]["validityEndJD"]
        self.assertReported(self.found(record), "orbit: validity endpoints must be finite with validityStartJD before")

    def test_rotation_validity_must_be_ordered(self):
        record = body()
        record["rotation"]["validityStartJD"] = record["rotation"]["validityEndJD"] + 1
        self.assertReported(self.found(record), "rotation: validity endpoints must be finite with validityStartJD before")

    def test_validity_too_far_to_convert_is_rejected(self):
        record = body()
        record["orbit"]["validityEndJD"] = 1e305
        self.assertReported(self.found(record), "orbit: validity endpoints are too far from the present")

    def test_eccentricity_of_one_is_rejected(self):
        record = body()
        record["orbit"]["elements"]["eccentricity"] = 1.0
        self.assertReported(self.found(record), "orbit.elements.eccentricity must be at least 0 and below 1")

    def test_eccentricity_reaching_one_at_an_endpoint_is_rejected(self):
        record = body()
        # 0.0485 + 0.02 * (2816795 - 2451545) / 36525 = 0.25 at the end, but
        # 0.0485 + 0.02 * (625295 - 2451545) / 36525 < 0 at the start.
        record["orbit"]["elements"]["rateEccentricity"] = 0.02
        self.assertReported(self.found(record), "at a validity endpoint the elements advanced by their rates")

    def test_non_positive_semi_major_axis_is_rejected(self):
        record = body()
        record["orbit"]["elements"]["semiMajorAxisAU"] = 0
        self.assertReported(self.found(record), "orbit.elements.semiMajorAxisAU must be greater than 0")

    def test_pole_declination_out_of_range_is_rejected(self):
        record = body()
        record["rotation"]["coefficients"]["poleDeclination"] = 91
        self.assertReported(self.found(record), "rotation.coefficients.poleDeclination must be within -90 to 90")

    def test_rotation_overflowing_at_an_endpoint_is_rejected(self):
        record = body()
        record["rotation"]["coefficients"]["rotationRate"] = 1e305
        self.assertReported(self.found(record), "the rotation overflows at a validity endpoint")

    def test_nan_literal_is_rejected(self):
        write_entry(self.root, "bodies", "ceres", body())
        path = self.root / "bodies" / "ceres" / "record.json"
        path.write_text(path.read_text().replace('"albedoScale": 1', '"albedoScale": NaN'))
        self.assertReported(messages(validate.validate(self.root)), "not valid JSON: NaN is not JSON")

    def test_infinity_literal_is_rejected(self):
        write_entry(self.root, "bodies", "ceres", body())
        path = self.root / "bodies" / "ceres" / "record.json"
        path.write_text(path.read_text().replace('"albedoScale": 1', '"albedoScale": -Infinity'))
        self.assertReported(messages(validate.validate(self.root)), "not valid JSON: -Infinity is not JSON")

    def test_out_of_range_number_is_rejected(self):
        write_entry(self.root, "bodies", "ceres", body())
        path = self.root / "bodies" / "ceres" / "record.json"
        path.write_text(path.read_text().replace('"albedoScale": 1', '"albedoScale": 1e400'))
        self.assertReported(messages(validate.validate(self.root)), "not valid JSON: 1e400 is too large")

    def test_sun_id_is_protected(self):
        found = self.found(body("sun"), id="sun")
        self.assertReported(found, "id 'sun' is reserved", "content/bodies/sun/record.json")

    def test_earth_id_is_protected(self):
        found = self.found(body("earth", parent="sun"), id="earth")
        self.assertReported(found, "id 'earth' is reserved", "content/bodies/earth/record.json")

    def test_provenance_source_needs_a_host(self):
        record = body()
        record["provenance"]["sources"] = ["https://"]
        self.assertReported(self.found(record), "provenance.sources.0: 'https://' does not match")

    def test_undeclared_capability_is_reported(self):
        record = major("ceres")
        record["capabilities"]["requires"] = ["kepler-standish-table2a/1", "lambert/1"]
        self.assertReported(self.found(record), "uses 'iau-linear/1' without listing it in capabilities.requires")

    # I1: cross-record admission

    def test_major_parent_must_be_a_major_body(self):
        write_entry(self.root, "bodies", "vesta", body("vesta"))
        found = self.found(major("ceres", parent="vesta"))
        self.assertReported(found, "parent 'vesta' must be sun, earth, or a major body listed under bodies")

    def test_major_parent_must_exist(self):
        found = self.found(major("ceres", parent="pluto"))
        self.assertReported(found, "parent 'pluto' must be sun, earth, or a major body")

    def test_major_moon_of_a_major_body_admits(self):
        write_entry(self.root, "bodies", "vesta", major("vesta"), {"texture.jpg": FAKE_JPEG})
        self.assertEqual(self.found(major("ceres", parent="vesta")), [])

    def test_parent_cycle_is_rejected(self):
        write_entry(self.root, "bodies", "vesta", major("vesta", parent="ceres"), {"texture.jpg": FAKE_JPEG})
        found = self.found(major("ceres", parent="vesta"))
        self.assertReported(found, "parent chain loops back on itself")

    def test_asset_ids_are_unique_across_bodies(self):
        write_entry(self.root, "bodies", "vesta", major("vesta", asset_id="shared"), {"texture.jpg": FAKE_JPEG})
        found = self.found(major("ceres", asset_id="shared"))
        self.assertReported(found, "asset id 'shared' is already used by vesta")

    # I2: temporary shipped-build limits

    def test_fifteen_major_bodies_are_rejected(self):
        for n in range(15):
            write_entry(self.root, "bodies", f"body-{n}", major(f"body-{n}"), {"texture.jpg": FAKE_JPEG})
        found = messages(validate.validate(self.root))
        self.assertIn("content/index.json: bodies lists 15 major bodies; current app builds admit at most 14 "
                      "and would drop every body", found)

    def test_fourteen_major_bodies_admit(self):
        for n in range(14):
            write_entry(self.root, "bodies", f"body-{n}", major(f"body-{n}"), {"texture.jpg": FAKE_JPEG})
        self.assertEqual(messages(validate.validate(self.root)), [])

    def test_sixty_five_body_records_are_rejected(self):
        for n in range(65):
            write_entry(self.root, "bodies", f"body-{n}", body(f"body-{n}"))
        found = messages(validate.validate(self.root))
        self.assertIn("content/index.json: bodies lists 65 records; current app builds fetch at most 64 "
                      "and would drop every body", found)

    def test_record_over_256_kb_is_rejected(self):
        record = body()
        record["provenance"]["accuracy"] = "x" * (256 * 1024)
        self.assertReported(self.found(record), "current app builds read at most 262144")

    def test_layer_asset_over_16_mib_is_rejected(self):
        record = body()
        record["capabilities"]["enhances"] = ["rings/1"]
        record["layers"] = [{"type": "rings", "version": "1", "assets": [
            {"id": "rings", "role": "profile", "path": "rings.png", "format": "png", "width": 2048, "height": 1,
             "byteLimit": 16 * 1024 * 1024 + 1, "sha256": "0" * 64, "required": True}]}]
        write_entry(self.root, "bodies", "ceres", record, {"rings.png": b"\x89PNG"})
        self.assertReported(messages(validate.validate(self.root)), "asset 'rings' is 16777217 bytes")

    # I3: symlinks

    def test_symlinked_asset_is_rejected(self):
        outside = Path(self.tmp.name) / "outside.jpg"
        outside.write_bytes(FAKE_JPEG)
        record = major("ceres")
        write_entry(self.root, "bodies", "ceres", record)
        os.symlink(outside, self.root / "bodies" / "ceres" / "texture.jpg")
        found = messages(validate.validate(self.root))
        self.assertIn("content/bodies/ceres/texture.jpg: is a symlink; entries hold regular files only", found)

    def test_symlinked_entry_directory_is_rejected(self):
        real = write_entry(self.root, "bodies", "ceres", body())
        target = Path(self.tmp.name) / "elsewhere"
        real.rename(target)
        os.symlink(target, real)
        found = messages(validate.validate(self.root))
        self.assertIn("content/bodies/ceres: is a symlink; entries must be real directories", found)


if __name__ == "__main__":
    unittest.main()
