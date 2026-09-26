# Craft records

Schema version 1.

A craft record supplies the 3D model the app draws for a class of aircraft, vessel, satellite or transit vehicle, or for one specific type.
The live feeds decide where each craft is; the record decides only what it looks like.

`content/craft/<domain>/<id>/record.json` beside `model.glb` and a `README.md`, checked by `schema/craft.schema.json` and `scripts/validate.py`.
The app release that draws craft from this repository has not shipped yet, so a phone preview does not show a model; `scripts/validate.py` is the check until it does.
The domains are `aircraft`, `vessels`, `satellites` and `transit`.

## Fields

| Field | Meaning |
| --- | --- |
| `kind` | `"craft"` |
| `id` | Directory name; lowercase, hyphen-separated, permanent |
| `name` | What the model is, for the Data Sources screen |
| `licence` | One of `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `MIT`, `public-domain` |
| `model` | The asset: always `id` `model`, `path` `model.glb`, `format` `glb`, stamped `byteLimit` and `sha256`, `required` true |
| `dimensions.length` | Real length in metres, nose to tail or bow to stern |
| `dimensions.span` | Real width in metres: wingspan, beam, or solar array span |
| `matches.classes` | Class ids this model stands in for, from the domain's list below |
| `matches.types` | Specific types this model is the exact match for |
| `matches.default` | Whether this is the domain's model when nothing else matches; one per domain |
| `provenance` | `sources` URLs and an `attribution` line |

## Matching

The app resolves each craft on screen to the first of: a record listing its specific type, a record listing its class, the domain's default, the model built into the app.
Two records may not claim the same type, and a domain has at most one default; the earlier record in `index.json` keeps the claim.

| Domain | Classes | Types |
| --- | --- | --- |
| `aircraft` | `airplane`, `propeller`, `helicopter`, `glider`, `balloon`, `parachutist`, `ultralight`, `drone`, `space-vehicle`, `ground-vehicle`, `obstacle` | ICAO aircraft type designators, such as `A320`, `B738`, `C172`, `H60` |
| `vessels` | `fishing`, `tug`, `sailing`, `pleasure`, `high-speed`, `service`, `passenger`, `cargo`, `tanker`, `other` | A nine-digit MMSI, for one named ship |
| `satellites` | `payload`, `rocket-body`, `debris` | NORAD catalogue numbers, such as `25544` for the ISS |
| `transit` | `bus`, `subway`, `light-rail`, `rail`, `ferry`, `cable` | None yet |

## The model

- glTF 2.0 binary (`.glb`), one buffer, triangle meshes with positions and normals, no textures.
  Colour comes from each material's `baseColorFactor`.
- Y is up and the nose, bow or direction of travel points along -Z.
  Export from Blender with `+Y Up` and the model facing +Y in Blender's own frame: the glTF exporter maps Blender (x, y, z) to glTF (x, z, -y), so Blender's +Y becomes glTF's -Z.
- Authored units do not matter: the app scales the model uniformly so its extent along Z equals `dimensions.length`.
- Keep it as light as it can be while reading well at a few hundred pixels.
  There is no vertex or byte limit, but a phone draws dozens of these at once, so a heavy model costs everyone frames.
- `python3 scripts/validate.py content` mirrors the structural checks of the app's model loader (`GlobeGLB.swift`, `GlobeAircraftAsset.swift`), so a model it rejects would fail to load in the app too.

## Licence

Only the licences above are accepted, because the app shows the model to the public.
A model found through an image search, ripped from a game, or exported from a flight simulator is not acceptable however good it looks.
Name the author and the source URL in `provenance` and in the README.
