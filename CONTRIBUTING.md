# Contributing

## Before you start

Two things get pull requests rejected more than anything else: content nobody can license, and numbers nobody can trace.

Every record names its sources.
If you cannot say where a number came from, do not put it in a record.
If you cannot say who made a texture and under what licence, do not commit the texture.

Public-domain government data (NASA, JPL, USGS, NAIF) and clearly licensed open sources are safe.
An image found through a search engine is not, no matter where it ends up being hosted.

## Adding a body

1. **Fork this repository** and create a branch.

2. **Create the entry directory**: `content/bodies/<id>/`.
   The id is lowercase, hyphen-separated, and stable forever - it is how the app identifies the body across releases.

3. **Write `record.json`.** Copy an existing record of the same tier as your starting point rather than writing one from scratch.
   [docs/schema.md](docs/schema.md) is the field reference.

4. **Add your assets** into the same directory and declare them in the record's `assets` array.

5. **Stamp the asset metadata.** Do not fill in `sha256`, `byteLimit`, `width` or `height` by hand - they must match the bytes exactly or the app rejects the asset.
   Run the stamping script from the app repository against your entry directory.

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
They are expensive, and the number of them is capped.

`minor` bodies are drawn as batched points.
They cost almost nothing, so there can be very many of them.

Tier is a description of what the record supports, not a request.
A record that declares `major` must supply what a major body needs - real radii and a texture - and is rejected if it does not.
Promoting a minor body later is a pull request that adds a texture, not a schema migration.

Start at `minor` if you do not have a good texture.
A correctly placed point is worth more than a major body wearing someone else's map.

## Capabilities

`capabilities.requires` lists what the app must implement to draw your record at all.
A build that lacks any of them skips the record and draws everything else.

`capabilities.enhances` lists what improves the record if present and is ignored if absent.
Use it for anything optional, so your record still draws on older builds.

Do not invent capability names.
The app implements a fixed set, and a record requiring an unimplemented one is skipped everywhere until the app gains it.

## Style

- No em dashes. Use a plain `-`.
- Two-space indentation in JSON.
- One entry per pull request unless the entries genuinely belong together.
