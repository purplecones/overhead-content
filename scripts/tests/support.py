import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[1]))

import json
from pathlib import Path


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def make_root(tmp: Path) -> Path:
    root = tmp / "content"
    write_json(root / "index.json", {"schemaVersion": 1, "kinds": {}})
    return root


def write_entry(root: Path, kind: str, id: str, record: dict, files: dict | None = None,
                readme: str = "# Entry\n\nSource: test.\n") -> Path:
    directory = root / kind / id
    write_json(directory / "record.json", record)
    (directory / "README.md").write_text(readme)
    for name, data in (files or {}).items():
        (directory / name).write_bytes(data)
    index = json.loads((root / "index.json").read_text())
    index["kinds"].setdefault(kind, [])
    if id not in index["kinds"][kind]:
        index["kinds"][kind].append(id)
    write_json(root / "index.json", index)
    return directory


def messages(problems) -> list[str]:
    return [f"{p.path}: {p.message}" for p in problems]
