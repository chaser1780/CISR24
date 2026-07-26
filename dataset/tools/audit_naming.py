#!/usr/bin/env python3
"""Enforce the canonical CISR24 name across a public release."""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import tarfile
import tempfile
from pathlib import Path

import h5py


DATASET_NAME = "CISR24"
SPLITS = ("train", "val", "test")
EXPECTED_ROWS = {"train": 504_000, "val": 100_800, "test": 100_800}
BANNED_TOKENS = (
    "CISR" + "22",
    "cisr" + "22",
    "CISR24-" + "1024-Clean-v1.1.1",
    "cisr24_" + "clean",
)


def token_hits(data: bytes, location: str) -> list[str]:
    issues = []
    for token in BANNED_TOKENS:
        count = data.count(token.encode("ascii"))
        if count:
            issues.append(f"{location}: banned naming token occurs {count} time(s)")
    return issues


def scan_source_archive(path: Path) -> list[str]:
    issues = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            issues.extend(token_hits(member.name.encode("utf-8"), f"{path}:member"))
            if not member.isfile():
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            data = extracted.read()
            issues.extend(token_hits(data, f"{path}:{member.name}"))
            if member.name.endswith(".h5"):
                with tempfile.NamedTemporaryFile(suffix=".h5") as handle:
                    handle.write(data)
                    handle.flush()
                    with h5py.File(handle.name, "r") as h5:
                        if str(h5.attrs.get("release_name", "")) != DATASET_NAME:
                            issues.append(
                                f"{path}:{member.name}: release_name is not {DATASET_NAME}"
                            )
    return issues


def scan_manifest(root: Path, split: str) -> tuple[dict[str, object], list[str]]:
    issues = []
    relative_h5 = f"hdf5/cisr24_{split}.h5"
    csv_path = root / "manifests" / f"cisr24_{split}_manifest.csv"
    gzip_path = csv_path.with_suffix(".csv.gz")
    raw = csv_path.read_bytes()
    issues.extend(token_hits(raw, str(csv_path)))
    rows = 0
    release_names = set()
    h5_paths = set()
    with io.StringIO(raw.decode("utf-8"), newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            release_names.add(row.get("release-name", ""))
            h5_paths.add(row.get("h5-rel-path", ""))
    if rows != EXPECTED_ROWS[split]:
        issues.append(f"{csv_path}: {rows} rows, expected {EXPECTED_ROWS[split]}")
    if release_names != {DATASET_NAME}:
        issues.append(f"{csv_path}: release-name values are not exactly {DATASET_NAME}")
    if h5_paths != {relative_h5}:
        issues.append(f"{csv_path}: h5-rel-path values are not exactly {relative_h5}")
    if not gzip_path.exists():
        issues.append(f"missing {gzip_path}")
    else:
        with gzip.open(gzip_path, "rb") as handle:
            compressed_content = handle.read()
        issues.extend(token_hits(compressed_content, str(gzip_path)))
        if compressed_content != raw:
            issues.append(f"{gzip_path}: decompressed content differs from CSV")
    return {
        "rows": rows,
        "release_names": sorted(release_names),
        "h5_rel_paths": sorted(h5_paths),
    }, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    root = args.release_root.expanduser().resolve()
    issues = []
    checks: dict[str, bool] = {}

    checks["root_name_exact"] = root.name == DATASET_NAME
    if not checks["root_name_exact"]:
        issues.append(f"release root directory must be named {DATASET_NAME}")

    expected_payload = {
        *(f"hdf5/cisr24_{split}.h5" for split in SPLITS),
        *(f"manifests/cisr24_{split}_manifest.csv" for split in SPLITS),
        *(f"manifests/cisr24_{split}_manifest.csv.gz" for split in SPLITS),
    }
    actual_payload = {
        path.relative_to(root).as_posix()
        for folder in (root / "hdf5", root / "manifests")
        for path in folder.glob("*")
        if path.is_file()
    }
    checks["payload_names_exact"] = actual_payload == expected_payload
    if not checks["payload_names_exact"]:
        issues.append("payload filenames do not match the canonical CISR24 layout")

    hdf5_release_names = {}
    for split in SPLITS:
        path = root / "hdf5" / f"cisr24_{split}.h5"
        with h5py.File(path, "r") as handle:
            value = str(handle.attrs.get("release_name", ""))
        hdf5_release_names[split] = value
        if value != DATASET_NAME:
            issues.append(f"{path}: release_name is not {DATASET_NAME}")
    checks["hdf5_release_names_exact"] = set(hdf5_release_names.values()) == {
        DATASET_NAME
    }

    manifest_results = {}
    for split in SPLITS:
        manifest_results[split], manifest_issues = scan_manifest(root, split)
        issues.extend(manifest_issues)
    checks["manifest_names_exact"] = not any(
        row["release_names"] != [DATASET_NAME]
        or row["h5_rel_paths"] != [f"hdf5/cisr24_{split}.h5"]
        for split, row in manifest_results.items()
    )

    source_archive = root / "provenance" / "CISR24-source.tar.gz"
    if source_archive.exists():
        issues.extend(scan_source_archive(source_archive))
    else:
        issues.append(f"missing {source_archive}")

    excluded = {args.output_json.resolve()} if args.output_json else set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.resolve() in excluded:
            continue
        if path.suffix in {".h5", ".gz", ".png", ".pdf", ".npz"}:
            continue
        issues.extend(token_hits(path.read_bytes(), str(path.relative_to(root))))
    checks["no_banned_names"] = not issues

    payload = {
        "dataset_name": DATASET_NAME,
        "release_root": root.name,
        "checks": checks,
        "hdf5_release_names": hdf5_release_names,
        "manifests": manifest_results,
        "issues": issues,
        "status": "pass" if all(checks.values()) and not issues else "fail",
    }
    text = json.dumps(payload, indent=2)
    print(text)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
