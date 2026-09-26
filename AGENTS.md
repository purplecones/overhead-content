# Overhead content: instructions for coding agents

You are working in `purplecones/overhead-content`, the content repository the Overhead iOS app fetches at launch.
People contribute by opening pull requests here; nothing in this repository is code that ships in the app.
Your job is to add or change one entry correctly, prove it with the validator, and open a pull request a reviewer can merge without asking questions.

## The one rule

Every number and every file must be traceable to a source the reviewer can open, under a licence the app may use.
If you cannot name the source, do not write the value.
If you cannot name the licence, do not add the file.

## Never edit the rules

A content pull request changes only `content/`.
Do not edit `scripts/`, `schema/` or `.github/`, even to make the validator pass.
If the validator seems wrong, leave it alone and say so in the pull request, quoting its output; the maintainer decides.

## Repository map

```
content/index.json                         which entries exist, per kind, in display order
content/bodies/<id>/                       planets, moons, asteroids: record.json, texture.jpg, README.md
content/events/solar-eclipses/<id>/        eclipses the app lists: record.json, README.md
content/craft/<domain>/<id>/               3D models: record.json, model.glb, README.md
content/transit-feeds/<id>/                GTFS-realtime feeds the backend ingests: record.json, README.md
schema/*.schema.json                       the structural contract for each kind
docs/schema.md  docs/events.md  docs/craft.md  docs/transit-feeds.md   field references
scripts/validate.py                        the verdict: what CI and the reviewer run
scripts/stamp.py                           writes digests and sizes into records
scripts/eclipses/from-nasa-canon.py        generates eclipse records from NASA's table
```

A kind's key in `index.json` is its folder path.
Each entry is a directory named by its id holding `record.json`, `README.md`, and only the assets the record declares.
The order of ids under `bodies` is the on-screen order; never sort that array.

## Procedure, every time

1. Read the field reference for the kind under `docs/` and open the neighbouring entry you will copy.
2. Create `content/<kind>/<id>/` with `record.json` and `README.md`; add `<id>` to `content/index.json` under the kind's key.
3. Put assets in the same directory and declare them in the record.
4. Run, from the repository root:

       python3 -m venv .venv && . .venv/bin/activate
       python3 -m pip install -r requirements-dev.txt
       python3 scripts/stamp.py content
       python3 scripts/validate.py content

   `stamp.py` fills in every `sha256`, `byteLimit`, `width` and `height`; never type those by hand.
   `validate.py` prints `path: problem`; fix each one and rerun until it prints nothing and exits 0.
5. Write the entry's `README.md`: what it is, each source as a link, the licence, and the attribution the licence requires.
6. Commit with a message such as `feat(bodies): add Ceres` and open a pull request using the template.
   For a body, tell the person how to test it on their phone before the review: open `overhead://content?source=https://github.com/<owner>/overhead-content/tree/<branch>` on the phone, or paste that GitHub URL under Options, Content.
   The app reads bodies, events and craft, so a phone preview shows all three; satellite models are admitted but not drawn yet.

One entry per pull request unless the entries only make sense together.

## Per kind

### Bodies (`content/bodies/`)

A major body with a `kepler-standish-table2a` orbit is drawn whatever its parent: the elements are parent-relative in `ecliptic-j2000`, so a moon of another planet draws exactly like a planet does once it is major.
Minor-tier records, and a `legacy-lunar-schlyter` orbit for any parent but Earth, are the only bodies not drawn (the latter is rejected outright, not merely left undrawn); do not add either unless the person has accepted that.

- Copy a planet record (`jupiter` is a clean example) for any new body.
- Orbit elements for a planet come straight from JPL's Table 2a fit (`https://ssd.jpl.nasa.gov/planets/approx_pos.html`); for anything else, generate them from JPL Horizons (`https://ssd.jpl.nasa.gov/horizons/`) instead.
  Look up osculating elements at epoch JD 2451545.0 TDB, frame ICRF/ecliptic J2000, centred on the parent (`@10` for the Sun, or the planet for a moon, for example `@599` for Jupiter), in au and degrees.
  Map them onto the schema: `semiMajorAxisAU` = A, `eccentricity` = EC, `inclinationDeg` = IN, `longitudeOfAscendingNodeDeg` = OM, `longitudeOfPerihelionDeg` = OM + W, `meanLongitudeDeg` = OM + W + MA normalised to 0-360, `rateMeanLongitude` = N (deg/day) x 36525; leave every other rate at 0 unless a published secular fit exists for that body.
  Osculating elements drift outside a short window, so keep `validityStartJD`/`validityEndJD` narrow (plus or minus 50 years around J2000 is a reasonable default) and say so in `provenance.accuracy`.
  The JPL Small-Body Database (`https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html`) is fine for finding an object, but do not paste its elements straight into a record: its epoch is rarely J2000, so its numbers need re-deriving from Horizons at JD 2451545.0 first.
- Rotation from NAIF `pck00011.tpc`, radii and GM from JPL or NSSDC fact sheets.
  Take all radii from one source.
- Textures: NASA, USGS Astrogeology, or Solar System Scope (CC BY 4.0) are safe.
  Equirectangular, 2:1, a JPEG named `texture.jpg` with `"format": "jpeg"`, 2048 x 1024 pixels (width and height must be powers of two, at most 2048 x 1024).
  Downscale a larger source map; the app rejects PNG textures and larger dimensions.
- `appearance.absoluteMagnitude` is required for `lambert` and `lunar` photometry: the body's V(1,0), for example from its NSSDC fact sheet.
- `presentation` is `sphere` only when the two radii are equal, otherwise `ellipsoid`.
- `tier` is `major` when you have a texture; radii and rotation are required either way now, so texture is the only thing tier still depends on.
  Without a texture, use `minor`.
  A major body's `parent` must be `sun`, `earth`, or another major body in the index that requires only capabilities current app builds implement.
- `provenance.accuracy` must state what the model omits and how large the error is.
- The app fails every body at once when one body record breaks a rule.
  `validate.py` mirrors those rules, including the orbit and rotation evaluation at both validity endpoints, so treat any problem it reports on a body as blocking.
  It cannot judge whether the body looks right, so still ask the person to check it on their phone before merging.
- Reference: `docs/schema.md`.

### Solar eclipses (`content/events/solar-eclipses/`)

- Do not hand-write records.
  Run the generator for the years needed:

      python3 scripts/eclipses/from-nasa-canon.py content --from 2037 --to 2040

- To add a title and summary, add the date to `TITLES` in the generator and rerun it.
- `greatest` is UTC.
  NASA's tables list Terrestrial Dynamical Time; the generator subtracts Delta T.
- Reference: `docs/events.md`.

### Craft models (`content/craft/aircraft|vessels|satellites|transit/`)

- The model is a `.glb`: glTF 2.0 binary, triangles with positions and normals, no textures, colours in `baseColorFactor`.
- Y up, nose or bow along -Z.
  If the person's model faces another way, rotate it in the exporter, not in the record.
  In Blender, the nose points along Blender's +Y and the model is exported with `+Y Up`: the glTF exporter maps Blender (x, y, z) to glTF (x, z, -y).
- `dimensions` are the real vehicle's length and span in metres, from the manufacturer or Wikipedia with the page cited.
- `matches.classes` come from the domain's list in `docs/craft.md`; `matches.types` are ICAO designators (aircraft), MMSI (vessels), or NORAD numbers (satellites).
  Set `default: true` only if the domain has none, and the person wants this model for everything unmatched.
- `licence` must be one of `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `MIT`, `public-domain`, and the README must name the author.
  NASA's 3D resources are `public-domain`.
  Sketchfab models are acceptable only under CC0 or CC BY, downloaded from the model's own page.
- `validate.py` mirrors the structural checks of the app's model loader.
  A phone pointed at the branch shows the model on matching craft once they are close enough to draw as bodies; satellite models are admitted but not drawn yet.
- Reference: `docs/craft.md`.

### Transit feeds (`content/transit-feeds/`)

- Find the agency's GTFS-realtime vehicle positions and trip updates URLs, static GTFS URL, and data licence page.
- Never put a key's value in a record.
  A key is named as `{ "secret": "TRANSIT_KEY_<NAME>", "query": "<param>" }` (or `"header"`); the maintainer sets the value.
- Fetch each feed URL in the record once (for example with `curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' <url>`) and paste each URL's status code and size into the pull request.
  The maintainer runs the ingest's own check, `npm run transit:try`, during review; it lives in a private repository.
- Reference: `docs/transit-feeds.md`.

## What gets a pull request closed

- A texture, model, or number with no source, or with a source that does not say what the record claims.
- A licence not on the list, or "found online".
- Hand-typed digests, or a record `stamp.py --check` reports as stale.
- A sorted `bodies` array, an em dash, or JSON not indented with two spaces.
- More than one unrelated entry in one pull request.
- Any change to `scripts/`, `schema/` or `.github/` in a content pull request.

## Pull request description

Use `.github/pull_request_template.md`.
State what was added, list each source with what it provided, name the licence and attribution, say that `validate.py` printed nothing and exited 0, and say whether it was checked on a phone.

## Prompts a person can give you

- "Add the dwarf planet Ceres as a major body, with its Dawn texture and sources."
- "Add a CC0 container ship model for cargo vessels; here is the GLB and its Sketchfab page."
- "Add the ISS model from NASA's 3D resources as satellite 25544."
- "Add the eclipses for 2037 to 2040 and give the 2037 Australian one a title."
- "Add the Chicago CTA transit feed."
