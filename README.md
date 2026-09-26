# Overhead content

Community content for [Overhead](https://github.com/purplecones/overhead), a native iOS aircraft, vessel and sky viewer.

This repository is the catalogue the app reads.
Adding a planet, a moon, an asteroid or a spacecraft to Overhead means opening a pull request here, not shipping a new build of the app.
The app fetches the latest release of this repository, so merged content reaches people when a release is cut, without an App Store release.

## What is here

```
content/
  index.json                       what entries exist, per kind, in display order
  bodies/<id>/                     planets, moons and asteroids: record.json, texture.jpg, README.md
  events/solar-eclipses/<id>/      the eclipses the app lists: record.json, README.md
  craft/<domain>/<id>/             3D models for aircraft, vessels, satellites and transit: record.json, model.glb, README.md
  transit-feeds/<id>/              live transit feeds the backend ingests: record.json, README.md
schema/                            one JSON Schema per kind
scripts/
  validate.py                      checks the whole tree; what CI and reviewers run
  stamp.py                         writes asset digests and sizes into records
  eclipses/from-nasa-canon.py      generates eclipse records from NASA's table
AGENTS.md                          instructions for a coding agent making a contribution
```

`index.json` names the entries; a kind's key is its folder path, and each entry is a directory holding a `record.json`, a `README.md`, and the assets the record declares.
The record filename is the same across every kind, so a new kind is a new folder, a new schema and a new validator rule rather than a change to the app.
There is no limit on how many entries a kind holds; review is the limit.

## How the app reads it

The app reads `index.json`, then `content/<kind>/<id>/record.json` for each entry the index lists, in the order the index lists them.
That order is load-bearing: it becomes the on-screen order of the bodies.
Alphabetising the array silently reorders what people see.

Each record declares the capabilities it needs.
The app admits the records it can draw and skips the ones it cannot, with a reason, rather than rejecting the whole catalogue.
That is what lets this repository move ahead of the app: a record that asks for a feature the installed version does not have is skipped by old builds and drawn by new ones, without the record changing.

An unknown kind is ignored rather than treated as an error, for the same reason.

Every kind fails safe on its own terms.
An eclipse record is admitted only if the app's own calculation agrees with it; a craft model only if it parses; a body only if the app implements what it requires.

## Testing your change before you open a pull request

You do not need to build the app.
Fork this repository, push your branch, and point the app at it: paste your fork, branch or pull request URL under Options, Content, or open this link on the phone:

    overhead://content?source=https://github.com/<you>/overhead-content/tree/<branch>

The catalogue reloads in the running session, and anything the app could not show is listed there with the reason.
Tap "Return to official content" when you are done; updating the app does this too.
Check that your body appears, is the right size relative to its neighbours, sits where it should in its orbit, and that its texture is oriented correctly.

Then open the pull request.

## Contributing with a coding agent

Clone your fork, open it in Claude Code, Codex, Cursor or any agent that reads `AGENTS.md`, and ask for what you want:

    Add Jupiter's moon Europa as a minor body, with sources.

The agent finds the procedure, the field references and the two commands to run in `AGENTS.md`, and stops when `scripts/validate.py` is clean.
Check the result on your phone, then open the pull request it prepared.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the process and [docs/schema.md](docs/schema.md) for the field reference.

Pull requests are reviewed before merging.
Content that is inaccurate, mislicensed or unattributed will not be merged, however good it looks.

## Licence

Records and text are licensed CC BY 4.0; see [LICENSE](LICENSE).
Every record carries its own `provenance` block naming the actual sources, licence and attribution for that entry's data and assets, and that block governs the entry.
