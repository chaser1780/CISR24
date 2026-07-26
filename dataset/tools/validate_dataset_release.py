#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import h5py


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_ROOT = PROJECT_ROOT / "releases" / "CISR24"
EXPECTED_PER_CELL = {"train": 1000, "val": 200, "test": 200}
EXPECTED_SNR = tuple(range(-20, 21, 2))


def read_rows(path: Path):
    with path.open("r", newline="") as handle:
        return [
            {key.replace("-", "_"): value for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def h5_key(handle, canonical):
    if canonical in handle:
        return canonical
    legacy = canonical.replace("-", "_")
    if legacy in handle:
        return legacy
    raise KeyError(f"Missing HDF5 dataset: /{canonical}")


def load_classes(path: Path):
    rows = read_rows(path)
    class_names = [row["class_name"] for row in rows]
    class_ids = [int(row["class_id"]) for row in rows]
    return rows, class_names, class_ids


def summarize_split(manifest_path: Path, h5_path: Path, class_names):
    rows = read_rows(manifest_path)
    counts = Counter()
    pair_counts = Counter()
    ids = set()
    sample_ids = set()
    seeds = set()
    h5_indices = []
    for row in rows:
        cls = row["class_name"]
        snr = int(round(float(row["snr_db"])))
        counts[cls] += 1
        pair_counts[(cls, snr)] += 1
        ids.add(int(row["class_id"]))
        sample_ids.add(row["sample_id"])
        seeds.add(row["seed"])
        h5_indices.append(int(row["h5_index"]))

    h5_rows = 0
    attrs = {}
    if h5_path.exists():
        with h5py.File(h5_path, "r") as handle:
            h5_rows = int(handle["/iq"].shape[0])
            attrs = {k: handle.attrs[k] for k in handle.attrs.keys()}

    return {
        "rows": len(rows),
        "class_counts": dict(counts),
        "pair_counts": pair_counts,
        "class_id_set": sorted(ids),
        "sample_ids": sample_ids,
        "seeds": seeds,
        "seeds_unique": len(seeds) == len(rows),
        "min_h5_index": min(h5_indices) if h5_indices else None,
        "max_h5_index": max(h5_indices) if h5_indices else None,
        "h5_indices": h5_indices,
        "h5_rows": h5_rows,
        "attrs": attrs,
        "all_class_names_present": sorted(counts) == sorted(class_names),
        "h5_exists": h5_path.exists(),
    }


def main():
    parser = argparse.ArgumentParser(description="Validate CISR24 clean release consistency")
    parser.add_argument("--release_root", default=str(DEFAULT_RELEASE_ROOT))
    parser.add_argument("--classes_csv", default=str(PROJECT_ROOT / "classes.csv"))
    parser.add_argument("--output_json", default="")
    args = parser.parse_args()

    release_root = Path(args.release_root)
    classes_csv = Path(args.classes_csv)
    _, class_names, class_ids = load_classes(classes_csv)

    result = {
        "release_root": release_root.name,
        "classes_csv": classes_csv.name,
        "expected_num_classes": len(class_names),
        "expected_class_ids": class_ids,
        "splits": {},
        "checks": {},
    }

    split_names = ["train", "val", "test"]
    split_data = {}
    for split in split_names:
        manifest_path = release_root / "manifests" / f"cisr24_{split}_manifest.csv"
        h5_path = release_root / "hdf5" / f"cisr24_{split}.h5"
        split_data[split] = summarize_split(manifest_path, h5_path, class_names)
        result["splits"][split] = {
            "rows": split_data[split]["rows"],
            "class_id_set": split_data[split]["class_id_set"],
            "min_h5_index": split_data[split]["min_h5_index"],
            "max_h5_index": split_data[split]["max_h5_index"],
            "h5_rows": split_data[split]["h5_rows"],
            "all_class_names_present": split_data[split]["all_class_names_present"],
        }

    result["checks"]["class_ids_match"] = all(
        split_data[split]["class_id_set"] == class_ids
        for split in split_names
    )
    result["checks"]["h5_index_in_range"] = all(
        (
            split_data[split]["h5_exists"]
            and len(split_data[split]["h5_indices"]) == split_data[split]["h5_rows"]
            and set(split_data[split]["h5_indices"])
            == set(range(1, split_data[split]["h5_rows"] + 1))
        )
        for split in split_names
    )
    result["checks"]["sample_ids_disjoint"] = all(
        len(split_data[a]["sample_ids"] & split_data[b]["sample_ids"]) == 0
        for idx, a in enumerate(split_names)
        for b in split_names[idx + 1 :]
    )
    result["checks"]["seeds_disjoint"] = all(
        len(split_data[a]["seeds"] & split_data[b]["seeds"]) == 0
        for idx, a in enumerate(split_names)
        for b in split_names[idx + 1 :]
    )
    result["checks"]["seeds_unique_within_split"] = all(
        split_data[split]["seeds_unique"] for split in split_names
    )
    result["checks"]["per_class_balanced"] = all(
        len(set(split_data[split]["class_counts"].values())) == 1
        for split in split_names
    )
    result["checks"]["per_class_snr_balanced"] = all(
        set(split_data[split]["pair_counts"])
        == {(class_name, snr) for class_name in class_names for snr in EXPECTED_SNR}
        and set(split_data[split]["pair_counts"].values()) == {EXPECTED_PER_CELL[split]}
        for split in split_names
    )
    result["checks"]["exact_split_sizes"] = all(
        split_data[split]["rows"] == len(class_ids) * len(EXPECTED_SNR) * EXPECTED_PER_CELL[split]
        for split in split_names
    )
    result["checks"]["all_class_names_present"] = all(
        split_data[split]["all_class_names_present"] for split in split_names
    )

    print(json.dumps(result, indent=2, default=str))
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if all(result["checks"].values()) else 1)


if __name__ == "__main__":
    main()
