# Transit feed records

Schema version 1.

A transit feed record is a single JSON object at `content/transit-feeds/<id>/record.json`, with a `README.md` beside it naming the agency's terms.
The same rules are checked by `lib/transit/record.js` in the Overhead repository, the ingest's validator.
That validator is authoritative; this document mirrors it.

## Identity

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | string | Must be `"transit-feed"`. |
| `id` | string | Must equal the directory name. Lowercase, hyphen-separated, at most 24 characters. |
| `agency` | string | The operator's name, at most 200 characters. |

The `id` is permanent once merged, because it prefixes every vehicle, stop, and route id the app stores.

## Coverage

```json
"coverage": { "minLat": 41.2, "minLon": -71.9, "maxLat": 43.0, "maxLon": -69.9 }
```

This is the box the Worker intersects with interest circles.
It may be generous but not global.
It is capped at 10 degrees each way in latitude and longitude.
`minLat` must be less than `maxLat`, and `minLon` must be less than `maxLon`.

## Modes and positioning

`modes` is a non-empty array of distinct values from the GTFS `route_type` families: `bus`, `subway`, `light-rail`, `rail`, `ferry`, `cable`.

`positioning` is `"gps"` when `vehiclePositions` carries coordinates.
It is `"predicted"` when the Worker must place vehicles from `tripUpdates` instead.
A `predicted` record may leave `realtime.vehiclePositions` empty.
A `gps` record needs at least one URL there.

## Realtime and static feeds

```json
"realtime": {
  "vehiclePositions": ["https://cdn.mbta.com/realtime/VehiclePositions.pb"],
  "tripUpdates": ["https://cdn.mbta.com/realtime/TripUpdates.pb"],
  "refreshSeconds": 10,
  "key": null
},
"static": {
  "gtfs": ["https://cdn.mbta.com/MBTA_GTFS.zip"],
  "key": null
}
```

`realtime.vehiclePositions` and `realtime.tripUpdates` are arrays because some agencies split a network across feeds; the MTA subway has eight.
`static.gtfs` is an array for the same reason; MTA bus publishes one zip per borough plus MTA Bus Company, and the pack build merges them.
Each array holds up to 16 URLs.
`realtime.refreshSeconds` is an integer from 5 to 300.
It is the cadence the Worker fetches this feed at, no matter how many phones are watching.

Every URL must be `https`.
`http` is accepted only with a logged warning, for agencies that serve nothing else.

## Keys

`realtime.key` and `static.key` are each `null`, or an object naming a Worker secret:

```json
{ "secret": "TRANSIT_KEY_MTA_BUS_TIME", "query": "key" }
```

or

```json
{ "secret": "TRANSIT_KEY_MTA_BUS_TIME", "header": "apikey" }
```

`secret` must start with `TRANSIT_KEY_`, followed by 1 to 52 characters from `A-Z`, `0-9`, and underscore.
That prefix keeps a record from ever naming another binding in the Worker's environment, such as the Maincloud ingest token.
Exactly one of `query` or `header` must be present, naming how the key is sent.

A record never contains the key's value.
Name the secret here; the maintainer adds it as a Worker secret of that exact name once the record is merged.
A `key.secret` that the Worker does not have leaves the record admitted but dormant, reported as `awaiting-secret`.

## Licence

```json
"licence": { "name": "MassDOT Developers License Agreement", "url": "https://www.mass.gov/files/documents/2017/10/27/develop_license_agree_0.pdf", "credit": "MBTA" }
```

`name`, `url`, and `credit` are all required text, at most 200 characters each.
`url` must be a valid URL.
`credit` is the exact string the app shows on its Data Sources screen.
A feed nobody can credit is not admitted.

## Provenance

```json
"provenance": { "verifiedAt": "2026-09-25", "notes": "Verified with npm run transit:try -- mbta." }
```

`verifiedAt` is required and must be `YYYY-MM-DD`.
`notes` is optional free text, at most 200 characters.

## Admission rules

These are applied identically by `lib/transit/record.js` in the Worker, the pack build, `npm run transit:try`, and the tests.

- Declared `kind` and `id` must match the path.
- An unknown field at any level rejects the record; its siblings are unaffected.
- Every URL must be `https`, except that `http` is accepted with a logged warning for agencies that serve nothing else.
- A `key.secret` the Worker does not have leaves the record admitted but dormant, reported as `awaiting-secret`.
- Licence `name`, `url`, and `credit` are required; a feed nobody can credit is not admitted.

Run `npm run transit:try -- path/to/record.json` in the Overhead repository before opening a pull request.
It validates the record, fetches its live feeds once, and prints what the ingest would commit.
Paste its output into the pull request.
