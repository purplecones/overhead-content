# Event records

Schema version 1.

Events are things that happen at a time, listed under the Explore menu's Events section.
Each event type is its own folder under `content/events/` and its own key in `content/index.json`, so a future type is a new folder, a new schema and a new validator rule.

## Solar eclipses

`content/events/solar-eclipses/<id>/record.json`, checked by `schema/solar-eclipse.schema.json`.

The repository decides which eclipses the app lists.
The app lists these under Explore > Solar eclipses; a phone preview of a branch shows them.
The app does not trust the record's numbers for anything it draws: it runs its own eclipse search from `greatest`, and admits the record only if its own eclipse falls within 10 minutes of `greatest` with a matching type.
A record that disagrees is skipped and the reason shows on the app's Content screen.

| Field | Required | Meaning |
| --- | --- | --- |
| `kind` | yes | `"solar-eclipse"` |
| `id` | yes | The UTC date of greatest eclipse, `YYYY-MM-DD`, and the directory name |
| `greatest` | yes | The instant of greatest eclipse in UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `type` | yes | `total`, `annular` or `hybrid`; partial eclipses are not listed because they have no track to play |
| `title` | no | A name people use, such as "Great American Eclipse"; otherwise the app shows the type |
| `summary` | no | One or two sentences: where the shadow went and what was notable |
| `provenance` | yes | `source`, `url` and `attribution` for `greatest` and `type` |

NASA's canon tables list greatest eclipse in Terrestrial Dynamical Time.
Subtract the row's Delta T to get UTC; `scripts/eclipses/from-nasa-canon.py` does this.

No coordinate, contact time or path is recorded.
They would be more numbers to transcribe and check, and the app computes them anyway.

### Adding or editing an eclipse

Run the generator for the years you want rather than typing a record:

    python3 scripts/eclipses/from-nasa-canon.py content --from 2037 --to 2040

Titles and summaries live in the generator's `TITLES` table so a rerun keeps them.
Add yours there, rerun, then `python3 scripts/validate.py content`.
