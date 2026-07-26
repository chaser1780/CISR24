#!/usr/bin/env python3
"""Create files.csv and SHA256SUMS for a completed CISR24 release."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def role(path: Path) -> str:
    first = path.parts[0] if path.parts else ""
    return {
        "hdf5": "data",
        "manifests": "manifest",
        "audit": "audit",
        "provenance": "provenance",
    }.get(first, "metadata")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_root", type=Path)
    args = parser.parse_args()
    root = args.release_root.expanduser().resolve()
    index_path = root / "files.csv"
    checksum_path = root / "SHA256SUMS"
    excluded = {index_path, checksum_path}
    files = sorted(path for path in root.rglob("*") if path.is_file() and path not in excluded)
    rows = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        rows.append(
            {
                "path": relative,
                "role": role(Path(relative)),
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
        )
    with index_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("path", "role", "bytes", "sha256"),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    checksum_path.write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in rows),
        encoding="utf-8",
    )
    print(f"Indexed {len(rows)} files under {root}")


if __name__ == "__main__":
    main()
