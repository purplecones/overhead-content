# Overhead content

Community content for [Overhead](https://github.com/purplecones/overhead), a native iOS aircraft, vessel and sky viewer.

This repository is the catalogue the app reads at launch.
Adding a planet, a moon, an asteroid or a spacecraft to Overhead means opening a pull request here, not shipping a new build of the app.
The app fetches the latest catalogue every time it starts, so merged content reaches people without an App Store release.

## What is here

```
content/
  index.json            what entries exist, per kind
  bodies/
    mars/
      record.json       the body: orbit, rotation, size, appearance, provenance
      texture.jpg       the surface map the record declares
```

`index.json` names the entries; each entry is a directory holding a `record.json` and whatever assets that record declares.
The record filename is the same across every kind, so a future kind is a new schema and a new validator rather than a change to the app's resolver.

## How the app reads it

The app reads `index.json`, then `content/<kind>/<id>/record.json` for each entry the index lists, in the order the index lists them.
That order is load-bearing: it becomes the on-screen order of the bodies.
Alphabetising the array silently reorders what people see.

Each record declares the capabilities it needs.
The app admits the records it can draw and skips the ones it cannot, with a reason, rather than rejecting the whole catalogue.
That is what lets this repository move ahead of the app: a record that asks for a feature the installed version does not have is skipped by old builds and drawn by new ones, without the record changing.

An unknown kind is ignored rather than treated as an error, for the same reason.

## Testing your change before you open a pull request

You do not need to build the app.
Fork this repository, push your branch, and point the app at it from the in-app content settings - paste your fork or branch URL and the catalogue reloads immediately, in the running session.
Check that your body appears, is the right size relative to its neighbours, sits where it should in its orbit, and that its texture is oriented correctly.

Then open the pull request.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the process and [docs/schema.md](docs/schema.md) for the field reference.

Pull requests are reviewed before merging.
Content that is inaccurate, mislicensed or unattributed will not be merged, however good it looks.

## Licence

See [LICENSE](LICENSE).
Every record carries its own `provenance` block naming the actual sources, licence and attribution for that entry's data and assets, and that block governs the entry.
