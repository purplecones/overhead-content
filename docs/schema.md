# Record schema

Schema version 1.

A record is a single JSON object in `content/<kind>/<id>/record.json`.
There is no limit on the number of entries or the size of the index; review is the limit.

## Identity

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | string | `"body"`. Singular, while the index key is plural (`"bodies"`). |
| `id` | string | Must equal the directory name. Lowercase, hyphen-separated, permanent. |
| `tier` | string | `"major"` or `"minor"`. |
| `displayName` | string | What people read on screen. |
| `parent` | string | The id this body orbits, for example `"sun"` or `"earth"`. |

The app cross-checks `kind` and `id` against the path and rejects a record that disagrees with where it lives.

## Capabilities

```json
"capabilities": {
  "requires": ["kepler-standish-table2a/1", "iau-linear/1", "lambert/1"],
  "enhances": []
}
```

`requires` is hard: a build missing any entry skips the record entirely.
`enhances` is optional and may be omitted.
Every capability is `name/version`.

Implemented capabilities are the model ids listed under Orbit, Rotation and Photometry below.

## Physical

| Field | Unit | Notes |
| --- | --- | --- |
| `equatorialRadiusM` | metres | Must be positive. |
| `polarRadiusM` | metres | Must be positive, and less than equatorial for an ellipsoid. |
| `gravitationalParameterM3S2` | m^3/s^2 | GM, not mass. |

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
  "validityStartJD": 625673.5,
  "validityEndJD": 2816787.5,
  "elements": { }
}
```

Distances are in AU with rates per Julian century.
Validity is numeric Julian-day endpoints; the app parses no dates.

`legacy-lunar-schlyter/1` selects the app's built-in lunar solver and carries no elements.

## Rotation

`iau-linear/1` - secular linear IAU rotation.

```json
"rotation": {
  "model": "iau-linear",
  "version": "1",
  "frame": "equatorial-j2000",
  "coefficients": {
    "poleRightAscension": 0.0, "poleDeclination": 0.0, "primeMeridian": 0.0,
    "poleRateRA": 0.0, "poleRateDec": 0.0, "rotationRate": 0.0
  }
}
```

Angles in degrees, pole rates in degrees per Julian century, rotation rate in degrees per day.
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

`albedo` is an RGB triple.
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

`byteLimit` is the file's exact byte count and `sha256` its exact digest.
Both are verified, so stamp them with the script rather than by hand.

`required: false` means the app draws the body with flat albedo if the asset is missing.
Prefer `false` - it degrades instead of failing.

Textures are plate carrée (equirectangular), 2:1.

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
Layer assets are stamped and verified exactly like `assets`.

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
