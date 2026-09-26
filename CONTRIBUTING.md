# Contributing

## Before you start

Two things get pull requests rejected more than anything else: content nobody can license, and numbers nobody can trace.

Every record names its sources.
If you cannot say where a number came from, do not put it in a record.
If you cannot say who made a texture and under what licence, do not commit the texture.

Public-domain government data (NASA, JPL, USGS, NAIF) and clearly licensed open sources are safe.
An image found through a search engine is not, no matter where it ends up being hosted.

## Working with a coding agent

`AGENTS.md` is written for your agent.
Point it at the repository and describe the entry; it follows the same steps below and runs the same checks.
You still read the result, test it on your phone, and sign the pull request.

## Adding a body

1. **Fork this repository** and create a branch.

2. **Create the entry directory**: `content/bodies/<id>/`, and add `<id>` to `content/index.json` under `bodies`, at the position you want it shown.
   The id is lowercase, hyphen-separated, and stable forever - it is how the app identifies the body across releases.

3. **Write `record.json`.** Copy a planet record (`jupiter`, for example) as your starting point rather than writing one from scratch; no shipped record is `minor` tier yet, so a planet is the nearest real example either way.
   [docs/schema.md](docs/schema.md) is the field reference.

4. **Add your assets** into the same directory and declare them in the record's `assets` array.
   Write the entry's `README.md`: sources, attribution and licence.
   Assets must be public domain, CC0, CC BY or CC BY-SA.

5. **Stamp and validate.** Do not fill in `sha256`, `byteLimit`, `width` or `height` by hand.
   Run `python3 scripts/stamp.py content`, then `python3 scripts/validate.py content`, and fix everything it prints.
   Continuous integration runs the same two commands on your pull request.

6. **Test it in the app** by pointing Overhead at your fork or branch. See the README.

7. **Open the pull request.** Describe where each number and each asset came from.

## What the reviewer checks

- The body is where it should be, at the right size, with a plausible orientation.
- Every source in `provenance.sources` is reachable and actually says what the record claims.
- `provenance.accuracy` states the model's real limits rather than a reassuring sentence.
  If the orbit model omits corrections, say which and how large the resulting error is.
- The licence is real and the attribution is correct.
- The texture is the body's visible appearance unless there is a stated reason otherwise.

## Tiers

`major` bodies are fully modelled: they get a frame slot, a texture and their own rendering.
They cost more to draw, so make one only when you have the radii and a real texture.

`minor` bodies are admitted into the catalogue but not drawn: the app has no minor-body rendering yet, only a reserved place for when it does.
They cost almost nothing to admit, so there can be very many of them, but add one only when the person accepts that it will not appear on screen yet.

Tier is a description of what the record supports, not a request.
A record that declares `major` must supply what a major body needs - real radii and a texture - and is rejected if it does not.
Promoting a minor body later is a pull request that adds a texture, not a schema migration.

Start at `minor` if you do not have a good texture, and say so plainly: it will sit in the catalogue undrawn until someone adds one.

## Capabilities

`capabilities.requires` lists what the app must implement to draw your record at all.
A build that lacks any of them skips the record and draws everything else.

`capabilities.enhances` lists what improves the record if present and is ignored if absent.
Use it for anything optional, so your record still draws on older builds.

Do not invent capability names.
The app implements a fixed set, and a record requiring an unimplemented one is skipped everywhere until the app gains it.

## Adding a solar eclipse

Run `python3 scripts/eclipses/from-nasa-canon.py content --from <year> --to <year>` rather than writing a record.
To name an eclipse, add its date to `TITLES` in that script and rerun it.
[docs/events.md](docs/events.md) is the field reference.

## Adding a craft model

1. Export a `.glb` with Y up and the nose or bow along -Z, positions and normals only, colours in the material.
2. Create `content/craft/<domain>/<id>/` with `model.glb`, a `record.json` copied from `craft/aircraft/peregrine`, and a `README.md` naming the author, the source URL and the licence.
3. Set `dimensions` to the real vehicle's length and span in metres, and `matches` to the classes or types it stands for.
4. Add `<id>` to `content/index.json` under `craft/<domain>`, then stamp and validate.
[docs/craft.md](docs/craft.md) is the field reference, including the class ids for each domain and the licences accepted.

## Adding a transit feed

Transit feed records track an agency's live vehicle positions and follow their own schema, separate from bodies.

1. **Find the feeds.** Locate the agency's GTFS-realtime feed URLs (vehicle positions and, if published separately, trip updates), its static GTFS URL, and its data licence.

2. **Create the entry directory**: `content/transit-feeds/<id>/record.json`, by copying a neighbouring record as your starting point.
   Add `<id>` to `content/index.json` under `transit-feeds`.
   [docs/transit-feeds.md](docs/transit-feeds.md) is the field reference.

3. **Never write a key's value in a record.** A record only names a secret; it never carries the secret itself.
   If the feed requires a key, set `realtime.key` (or `static.key`) to `{ "secret": "TRANSIT_KEY_<NAME>", "query": "<param>" }` or to the same shape with `"header"` instead of `"query"`.
   The secret name must start with `TRANSIT_KEY_`, followed only by `A-Z`, `0-9`, and underscore.
   The maintainer adds the actual value as a Worker secret of that exact name once the record is merged; until then the feed is admitted but dormant, reported as `awaiting-secret`.

4. **Test it.** Run `npm run transit:try -- path/to/record.json` in the Overhead repository.
   It validates the record, fetches its live feeds once, and prints what the ingest would commit.
   Paste its output into the pull request.

5. **Cite the licence and credit exactly as the agency states them.** A feed nobody can credit is not admitted.

## Style

- No em dashes. Use a plain `-`.
- Two-space indentation in JSON.
- One entry per pull request unless the entries genuinely belong together.
