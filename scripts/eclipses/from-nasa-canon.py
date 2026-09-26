#!/usr/bin/env python3
"""Write one solar eclipse record per central eclipse from NASA's canon table.

Usage:

    python3 scripts/eclipses/from-nasa-canon.py content --from 2016 --to 2036
    python3 scripts/eclipses/from-nasa-canon.py content --from 2016 --to 2036 --table SE2001-2100.html

Without --table the SE2001-2100 table is fetched from eclipse.gsfc.nasa.gov.
Each row gives the instant of greatest eclipse in Terrestrial Dynamical Time
and the Delta T used; the record stores UTC, which is TD minus Delta T, since
that is the clock the app and every observer read.

Only central eclipses (T, A, H) are written: a partial eclipse has no umbral
track for the app to play. Existing records are rewritten, so titles live in
TITLES here rather than in hand edits, and a rerun is a no-op.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TABLE_URL = "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html"
KIND_KEY = "events/solar-eclipses"
MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
TYPES = {"T": "total", "A": "annular", "H": "hybrid"}
ROW = re.compile(r"^\s*(\d{5})\s+(\d{4}) (\w{3}) (\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s+(-?\d+)\s+\d+\s+(\d+)\s+([TAHP])\S*\s+")

PROVENANCE = {
    "source": "NASA Five Millennium Canon of Solar Eclipses, table SE2001-2100",
    "url": TABLE_URL,
    "attribution": "Eclipse predictions by Fred Espenak, NASA/GSFC",
}

# Title and summary by UTC date. Everything else carries only the required fields.
TITLES: dict[str, tuple[str, str]] = {
    "2016-03-09": ("Indonesian total eclipse",
                   "Totality crossed Sumatra, Borneo and Sulawesi before heading out over the Pacific."),
    "2017-08-21": ("Great American Eclipse",
                   "The first total eclipse to cross the contiguous United States coast to coast since 1918."),
    "2019-07-02": ("Chile and Argentina total eclipse",
                   "Totality came ashore at La Serena late in the afternoon and ended at sunset near Buenos Aires."),
    "2020-12-14": ("Patagonian total eclipse",
                   "The shadow crossed northern Patagonia in Chile and Argentina."),
    "2023-04-20": ("Ningaloo hybrid eclipse",
                   "A rare hybrid, annular at its ends and total in the middle, seen as total from Exmouth in Western Australia."),
    "2023-10-14": ("Ring of fire across the Americas",
                   "An annular eclipse from Oregon to Texas and on through Central America to Brazil."),
    "2024-04-08": ("Great North American Eclipse",
                   "Totality crossed Mexico, the United States and Canada, with up to four and a half minutes of darkness."),
    "2026-08-12": ("Iberian total eclipse",
                   "Totality crosses Greenland, Iceland and northern Spain just before sunset."),
    "2027-08-02": ("Longest eclipse of the century",
                   "Six minutes and twenty-three seconds of totality over Luxor, on a track from Spain to the Horn of Africa."),
    "2028-07-22": ("Sydney's total eclipse",
                   "The shadow crosses Australia from the Kimberley to Sydney, then New Zealand's South Island."),
}


def load_table(path: str | None) -> str:
    if path:
        return Path(path).read_text(errors="replace")
    with urllib.request.urlopen(TABLE_URL, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def rows(table: str, first: int, last: int):
    text = re.sub(r"<[^>]+>", "", table)
    for line in text.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        _, year, month, day, hour, minute, second, delta_t, _, kind = match.groups()
        year = int(year)
        if year < first or year > last or kind not in TYPES:
            continue
        td = datetime(year, MONTHS[month], int(day), int(hour), int(minute), int(second), tzinfo=timezone.utc)
        utc = td - timedelta(seconds=int(delta_t))
        yield utc, TYPES[kind]


def write(root: Path, utc: datetime, kind: str) -> str:
    id = utc.strftime("%Y-%m-%d")
    directory = root / KIND_KEY / id
    directory.mkdir(parents=True, exist_ok=True)
    record = {"kind": "solar-eclipse", "id": id, "greatest": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "type": kind, "provenance": PROVENANCE}
    if id in TITLES:
        record["title"], record["summary"] = TITLES[id]
    (directory / "record.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    (directory / "README.md").write_text(
        f"# {record.get('title', kind.capitalize() + ' solar eclipse')} ({id})\n\n"
        f"Greatest eclipse {record['greatest']} UTC, converted from the table's Terrestrial Dynamical Time using its Delta T.\n"
        f"Source: <{TABLE_URL}>.\n"
        f"{PROVENANCE['attribution']}.\n")
    return id


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--from", dest="first", type=int, required=True)
    parser.add_argument("--to", dest="last", type=int, required=True)
    parser.add_argument("--table", help="a saved copy of the NASA table instead of fetching it")
    args = parser.parse_args(argv)
    ids = [write(args.root, utc, kind) for utc, kind in rows(load_table(args.table), args.first, args.last)]
    if not ids:
        print("no central eclipses found; is the table the SE2001-2100 page?", file=sys.stderr)
        return 1
    index_path = args.root / "index.json"
    index = json.loads(index_path.read_text())
    index["kinds"][KIND_KEY] = sorted(set(index["kinds"].get(KIND_KEY, [])) | set(ids))
    index_path.write_text(json.dumps(index, indent=2) + "\n")
    print(f"wrote {len(ids)} eclipse records, {args.first} to {args.last}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
