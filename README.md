# Overhead content

Community content for Overhead, a native iOS aircraft, vessel and sky viewer.

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
Current app builds limit bodies: at most 14 major bodies and 64 body records, each `record.json` at most 256 KB, each asset at most 16 MiB and 64 MiB of body assets in all, with `index.json` at most 64 KB.
`scripts/validate.py` enforces these limits, and they will lift in a later app release.

## How the app reads it

The app reads `index.json`, then `content/<kind>/<id>/record.json` for each entry the index lists, in the order the index lists them.
Current app builds read only `bodies`; the other kinds reach the app in a later release.
That order is load-bearing: it becomes the on-screen order of the bodies.
Alphabetising the array silently reorders what people see.

Each record declares the capabilities it needs.
A record that requires a capability the installed app does not implement is skipped, with a reason, and the rest are drawn.
That is what lets this repository move ahead of the app: a record that asks for a feature the installed version does not have is skipped by old builds and drawn by new ones, without the record changing.

An unknown kind is ignored rather than treated as an error, for the same reason.

A capability problem - a requirement the app does not implement, a model the record uses without listing it, or a layer that fails - is the only body defect current builds skip safely, by skipping that one record or dropping that one layer.
Any other body defect - a record that does not decode, an out-of-range number, a texture of the wrong format or size, a limit exceeded - fails the whole package on current builds, so every contributed body disappears for everyone.
That is why `scripts/validate.py` mirrors the app's body rules one for one, and why it must pass before a body is merged.
The app release that reads events and craft is designed to fail safe per record: an eclipse record admitted only if the app's own calculation agrees with it, a craft model only if it parses.

## Testing your change before you open a pull request

You do not need to build the app.
Current app builds preview bodies only; the app release that reads events and craft from this repository has not shipped yet, so for those `scripts/validate.py` is the check until it does.
Fork this repository, push your branch, and point the app at it: paste your fork, branch or pull request URL under Options, Content, or open this link on the phone:

    overhead://content?source=https://github.com/<owner>/overhead-content/tree/<branch>

The catalogue reloads in the running session, and anything the app could not show is listed there with the reason.
Tap "Return to official content" when you are done; updating the app does this too.
Check that your body appears, is the right size relative to its neighbours, sits where it should in its orbit, and that its texture is oriented correctly.

Then open the pull request.

## Contributing with a coding agent

Clone your fork, open it in Claude Code, Codex, Cursor or any agent that reads `AGENTS.md`, and ask for what you want:

    Add the dwarf planet Ceres as a major body, with its Dawn texture and sources.

The agent finds the procedure, the field references and the two commands to run in `AGENTS.md`, and stops when `scripts/validate.py` is clean.
For a body, that is not the finish line: the validator checks every rule the app applies, but it cannot tell whether the body looks right, so check the result on your phone before you open the pull request it prepared.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the process and [docs/schema.md](docs/schema.md) for the field reference.

Pull requests are reviewed before merging.
Content that is inaccurate, mislicensed or unattributed will not be merged, however good it looks.

## Licence

Records and text are licensed CC BY 4.0; see [LICENSE](LICENSE).
Every record carries its own `provenance` block naming the actual sources, licence and attribution for that entry's data and assets, and that block governs the entry.
