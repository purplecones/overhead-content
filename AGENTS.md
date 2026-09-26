# Overhead content: instructions for coding agents

You are working in `purplecones/overhead-content`, the content repository the Overhead iOS app fetches at launch.
People contribute by opening pull requests here; nothing in this repository is code that ships in the app.
Your job is to add or change one entry correctly, prove it with the validator, and open a pull request a reviewer can merge without asking questions.

## The one rule

Every number and every file must be traceable to a source the reviewer can open, under a licence the app may use.
If you cannot name the source, do not write the value.
If you cannot name the licence, do not add the file.

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

       python3 -m pip install -r requirements-dev.txt
       python3 scripts/stamp.py content
       python3 scripts/validate.py content

   `stamp.py` fills in every `sha256`, `byteLimit`, `width` and `height`; never type those by hand.
   `validate.py` prints `path: problem`; fix each one and rerun until it prints nothing and exits 0.
5. Write the entry's `README.md`: what it is, each source as a link, the licence, and the attribution the licence requires.
6. Commit with a message such as `feat(bodies): add Europa` and open a pull request using the template.
   Tell the person how to test it on their phone before the review: open `overhead://content?source=https://github.com/<fork>/overhead-content/tree/<branch>` on the phone, or paste that GitHub URL under Options, Content.

One entry per pull request unless the entries only make sense together.

## Per kind

### Bodies (`content/bodies/`)

- Copy the nearest existing record: a planet for a planet, `moon` for a moon.
- Orbit elements from JPL (`https://ssd.jpl.nasa.gov/planets/approx_pos.html` for planets), rotation from NAIF `pck00011.tpc`, radii and GM from JPL or NSSDC fact sheets.
  Take all radii from one source.
- Textures: NASA, USGS Astrogeology, or Solar System Scope (CC BY 4.0) are safe.
  Equirectangular, 2:1, JPEG or PNG.
- `tier` is `major` only when you have radii, rotation, and a texture; otherwise `minor`.
- `provenance.accuracy` must state what the model omits and how large the error is.
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
- `dimensions` are the real vehicle's length and span in metres, from the manufacturer or Wikipedia with the page cited.
- `matches.classes` come from the domain's list in `docs/craft.md`; `matches.types` are ICAO designators (aircraft), MMSI (vessels), or NORAD numbers (satellites).
  Set `default: true` only if the domain has none, and the person wants this model for everything unmatched.
- `licence` must be one of `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `MIT`, `public-domain`, and the README must name the author.
  NASA's 3D resources are `public-domain`.
  Sketchfab models are acceptable only under CC0 or CC BY, downloaded from the model's own page.
- `validate.py` mirrors the app's loader's structural checks; a model that passes here loads on the phone.
- Reference: `docs/craft.md`.

### Transit feeds (`content/transit-feeds/`)

- Find the agency's GTFS-realtime vehicle positions and trip updates URLs, static GTFS URL, and data licence page.
- Never put a key's value in a record.
  A key is named as `{ "secret": "TRANSIT_KEY_<NAME>", "query": "<param>" }` (or `"header"`); the maintainer sets the value.
- Test with `npm run transit:try -- <record>` in the Overhead app repository if it is available, and paste the output into the pull request.
- Reference: `docs/transit-feeds.md`.

## What gets a pull request closed

- A texture, model, or number with no source, or with a source that does not say what the record claims.
- A licence not on the list, or "found online".
- Hand-typed digests, or a record `stamp.py --check` reports as stale.
- A sorted `bodies` array, an em dash, or JSON not indented with two spaces.
- More than one unrelated entry in one pull request.

## Pull request description

Use `.github/pull_request_template.md`.
State what was added, list each source with what it provided, name the licence and attribution, paste the last lines of `validate.py`, and say whether it was checked on a phone.

## Prompts a person can give you

- "Add Jupiter's moon Europa as a minor body, with sources."
- "Give Europa a texture from USGS and promote it to major."
- "Add a CC0 container ship model for cargo vessels; here is the GLB and its Sketchfab page."
- "Add the ISS model from NASA's 3D resources as satellite 25544."
- "Add the eclipses for 2037 to 2040 and give the 2037 Australian one a title."
- "Add the Chicago CTA transit feed."
