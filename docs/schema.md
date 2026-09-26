# Record schema

Schema version 1.

A record is a single JSON object in `content/<kind>/<id>/record.json`.

Current app builds read every body record and fail the whole package - every contributed body, for every user - when one record does not decode or breaks one of the rules below.
`scripts/validate.py` mirrors those rules, so a body it accepts is one the app admits.
JSON must be plain JSON: `NaN`, `Infinity` and numbers beyond the 64-bit float range are rejected.

## Limits on current app builds

Current app builds limit bodies, and `validate.py` enforces these limits until a later app release lifts them:

| Limit | Value |
| --- | --- |
| Major bodies | at most 14 (16 slots less the Sun and Earth) |
| Body records, major and minor | at most 64 |
| One `record.json` | at most 256 KB |
| `content/index.json`, all kinds together | at most 64 KB |
| One asset | at most 16 MiB |
| All body assets together | at most 64 MiB |

## Identity

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | string | `"body"`. Singular, while the index key is plural (`"bodies"`). |
| `id` | string | Must equal the directory name. Lowercase, hyphen-separated, permanent. |
| `tier` | string | `"major"` or `"minor"`. |
| `displayName` | string | What people read on screen. |
| `parent` | string | The id this body orbits, for example `"sun"` or `"earth"`. A major body's parent is `sun`, `earth`, or another major body in the index, with no loops. That parent must not require a capability current app builds lack, since they skip it. |

The app cross-checks `kind` and `id` against the path and rejects a record that disagrees with where it lives.
The ids `sun` and `earth` are reserved: the app draws those two itself.

## Capabilities

```json
"capabilities": {
  "requires": ["kepler-standish-table2a/1", "iau-linear/1", "lambert/1"],
  "enhances": []
}
```

`requires` is hard: a build missing any entry skips the record entirely.
Every model the record uses must be listed in `requires` - the orbit, rotation and photometry models for a major body, the orbit model alone for a minor one - or the app skips the record.
`enhances` is optional and may be omitted.
Every capability is `name/version`.

Implemented capabilities are the model ids listed under Orbit, Rotation and Photometry below.

## Physical

| Field | Unit | Notes |
| --- | --- | --- |
| `equatorialRadiusM` | metres | Positive, at most 1e10. |
| `polarRadiusM` | metres | Positive, at most equatorial; equal for a sphere, less for an ellipsoid. |
| `gravitationalParameterM3S2` | m^3/s^2 | GM, not mass. Positive, at most 1e25. |

Take all axes of an ellipsoid from one source so the flattening stays self-consistent.
`pck00011.tpc` `BODY<n>99_RADII` gives all three together; mixing a JPL equatorial radius with an NSSDC polar radius does not.

## Orbit

`kepler-standish-table2a/1` - linear Kepler elements from the JPL approximate-positions tables.

```json
"orbit": {
  "model": "kepler-standish-table2a",
  "version": "1",
  "epochJD": 2451545.0,
  "frame": "ecliptic-j2000",
  "distanceUnit": "au",
  "angleUnit": "deg",
  "timeConvention": "tt-as-utc",
  "validityStartJD": 625295.0,
  "validityEndJD": 2816795.0,
  "elements": {
    "semiMajorAxisAU": 1.52371243,
    "eccentricity": 0.09336511,
    "inclinationDeg": 1.85181869,
    "longitudeOfAscendingNodeDeg": 49.71320984,
    "longitudeOfPerihelionDeg": -23.91744784,
    "meanLongitudeDeg": -4.56813164,
    "rateSemiMajorAxis": 9.7e-7,
    "rateEccentricity": 0.00009149,
    "rateInclination": -0.00724757,
    "rateMeanLongitude": 19140.29934243,
    "ratePerihelion": 0.45223625,
    "rateNode": -0.26852431
  }
}
```

Distances are in AU with rates per Julian century (the example above is the shipped Mars record).
Validity is numeric Julian-day endpoints; the app parses no dates.
`validityStartJD` must be before `validityEndJD`.
All twelve `elements` fields are required; there is no default for a missing rate.
`semiMajorAxisAU` must be positive and `eccentricity` at least 0 and below 1: the app draws ellipses only.
The app evaluates the orbit at both validity endpoints, with every element advanced by its rate, and rejects the record if the orbit stops being an ellipse there, so a large `rateEccentricity` or `rateSemiMajorAxis` needs a narrower window.

Producing elements: for a planet, take Table 2a's own linear fit directly from `https://ssd.jpl.nasa.gov/planets/approx_pos.html`.
For anything else - a moon, an asteroid, a dwarf planet - use JPL Horizons (`https://ssd.jpl.nasa.gov/horizons/`) instead: look up osculating elements at epoch JD 2451545.0 TDB, frame ICRF/ecliptic J2000, centred on the parent (`@10` for the Sun, or the planet for a moon, for example `@599` for Jupiter), in au and degrees.
Map Horizons' output onto the fields above: `semiMajorAxisAU` = A, `eccentricity` = EC, `inclinationDeg` = IN, `longitudeOfAscendingNodeDeg` = OM, `longitudeOfPerihelionDeg` = OM + W, `meanLongitudeDeg` = OM + W + MA normalised to 0-360, `rateMeanLongitude` = N (deg/day) x 36525; leave every other rate at 0 unless a published secular fit exists for that body.
Osculating elements drift outside a short window, so keep `validityStartJD`/`validityEndJD` narrow - plus or minus 50 years around J2000 is a reasonable default - and say so in `provenance.accuracy`.
Do not paste JPL Small-Body Database (`https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html`) values in directly: SBDB's epoch is rarely J2000, so its numbers need re-deriving from Horizons at JD 2451545.0 first.

`legacy-lunar-schlyter/1` selects the app's built-in lunar solver and carries no elements; it only works for a body whose parent is Earth.

## Rotation

`iau-linear/1` - secular linear IAU rotation.

```json
"rotation": {
  "model": "iau-linear",
  "version": "1",
  "epochJD": 2451545.0,
  "frame": "equatorial-j2000",
  "angleUnit": "deg",
  "timeConvention": "tt-as-utc",
  "validityStartJD": 625295.0,
  "validityEndJD": 2816795.0,
  "coefficients": {
    "poleRightAscension": 317.269202, "poleDeclination": 54.432516, "primeMeridian": 176.049863,
    "poleRateRA": -0.10927547, "poleRateDec": -0.05827105, "rotationRate": 350.891982443297
  }
}
```

The example above is the shipped Mars record; `epochJD`, `frame`, `angleUnit`, `timeConvention`, `validityStartJD`, `validityEndJD` and all six `coefficients` fields are required.
Angles in degrees, pole rates in degrees per Julian century, rotation rate in degrees per day.
`poleDeclination` is within -90 to 90, `validityStartJD` is before `validityEndJD`, and the rotation must stay finite at both validity endpoints.
A retrograde rotator has a negative `rotationRate` - Venus is about -1.4814 and Uranus about -501.1601.

Periodic nutation and libration terms are **not** applied.
If your body has significant periodic terms, state their magnitude in `provenance.accuracy`.

`legacy-lunar-libration/1` selects the app's built-in lunar orientation.

## Appearance

```json
"appearance": {
  "presentation": "ellipsoid",
  "albedo": [0.15, 0.15, 0.15],
  "albedoScale": 1.0,
  "absoluteMagnitude": -1.52,
  "photometry": { "model": "lambert", "version": "1" },
  "textureID": "mars-2k"
}
```

`presentation` is `sphere` (equal radii required) or `ellipsoid` (polar must be less than equatorial).

`absoluteMagnitude` is the body's V(1,0), for example from its NSSDC fact sheet.
It is required for `lambert` and `lunar` photometry and optional for `emissive`.

`albedoScale` is positive and at most 100.

`albedo` is an RGB triple, each value 0 to 1.
Published geometric albedo is usually a single scalar, so a triple is normally that scalar repeated or split for tint.
Say which in `provenance.accuracy` rather than implying per-channel measurement.

`photometry` is `lambert/1` for ordinary diffuse bodies, `emissive/1` for self-lit ones, `lunar/1` for the app's lunar phase curve.

`textureID` must name an entry in `assets`, or be omitted.
A `major` record must have one.

## Assets

```json
"assets": [{
  "id": "mars-2k",
  "path": "texture.jpg",
  "format": "jpeg",
  "width": 2048,
  "height": 1024,
  "byteLimit": 750547,
  "sha256": "2d187f...",
  "required": false
}]
```

`path` is relative to the entry directory, so every entry can call its texture `texture.jpg` without collision.
Traversal (`..`), absolute paths and symlinks are rejected.
`id` must be unique across every body, not just within its record.

A texture in `assets` must be a JPEG: `format` `"jpeg"` and a `path` ending `.jpg` or `.jpeg`.
Width and height must each be a power of two, the width at most 2048 and the height at most 1024, and the file at most 16 MiB.
PNG and larger textures fail every body on current app builds, so downscale a larger source map to 2048 x 1024.

`byteLimit` is the file's exact byte count and `sha256` its exact digest.
Both are verified, so stamp them with the script rather than by hand.

`required: false` means the app draws the body with flat albedo if the asset is missing.
Prefer `false` - it degrades instead of failing.

Textures are plate carrée (equirectangular), 2:1: 2048 x 1024 in practice.

## Layers

```json
"layers": [{
  "type": "rings",
  "version": "1",
  "params": { "innerRadiusM": 69856529, "outerRadiusM": 140899719, "castsShadow": true },
  "assets": [{ "id": "saturn-rings-profile", "role": "profile", "path": "rings-profile.png", "format": "png", "width": 2048, "height": 1, "...": "stamped like any asset" }]
}]
```

A layer adds something drawn on top of the body's surface.
Each layer's `type/version` is a capability and must be listed under `requires` or `enhances`.
Under `enhances`, a build without the layer drops it and still draws the body; under `requires`, such a build skips the record.
Unknown params and out-of-range values reject the record, so a typo is reported rather than ignored.
Layer assets are stamped and verified like `assets`, but their format and size come from the layer type: the rings profile is a PNG.

### `rings/1`

A flat ring disc in the body's equatorial plane, lit by the Sun and shadowed by the body.

| Param | Range | Default | Notes |
| --- | --- | --- | --- |
| `innerRadiusM` | metres | required | Inner edge, from the body's centre. |
| `outerRadiusM` | metres | required | Outer edge, at most 20 equatorial radii. |
| `opacityScale` | 0 to 4 | 1 | Multiplies the profile's opacity. |
| `brightness` | 0 to 8 | 1 | Multiplies scattered light. |
| `tint` | three values, 0 to 4 | `[1, 1, 1]` | Colour multiplier. |
| `litAsymmetry` | -0.95 to 0.95 | -0.3 | Forward or back scattering on the sunlit face. |
| `unlitAsymmetry` | -0.95 to 0.95 | 0.6 | Forward or back scattering seen through the unlit face. |
| `castsShadow` | true or false | true | Whether the rings shade the body's surface. |

The `profile` asset is a PNG with alpha, one pixel high and up to 2048 wide, sampled from the inner to the outer edge.

## Provenance

```json
"provenance": {
  "sources": ["https://..."],
  "attribution": "JPL Solar System Dynamics (orbit); NAIF / IAU (rotation); ... (texture).",
  "licence": "Public domain (US government); texture CC BY 4.0.",
  "modelVersion": "Standish Table 2a via JPL approximate positions; IAU 2015 via pck00011.tpc.",
  "accuracy": "State the model's real limits here.",
  "coverage": "What span and what falls back if an asset is absent."
}
```

`attribution` is shown to users on the app's Data Sources screen, so it must be correct and complete.
Only admitted records are credited, so nothing is claimed for content the app is not drawing.

`accuracy` is the field reviewers read hardest.
State what is omitted and how wrong it makes the result.
"Table 2b corrections are omitted; heliocentric error reaches 0.68 degrees at J2000" is useful.
"High accuracy" is not.
