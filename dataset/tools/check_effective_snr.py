#!/usr/bin/env python3
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import h5py
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_ROOT = PROJECT_ROOT / "releases" / "CISR24"


def sample_rows(manifest_path: Path, per_class: int, target_snr: int):
    chosen = defaultdict(list)
    with manifest_path.open("r", newline="") as handle:
        for source_row in csv.DictReader(handle):
            row = {key.replace("-", "_"): value for key, value in source_row.items()}
            if int(round(float(row["snr_db"]))) != target_snr:
                continue
            cls = row["class_name"]
            if len(chosen[cls]) < per_class:
                chosen[cls].append(row)
    return chosen


def effective_snr(sig: np.ndarray, start: int, active_len: int):
    active = sig[start : start + active_len]
    noise = np.concatenate([sig[:start], sig[start + active_len :]])
    noise_power = float(np.mean(np.abs(noise) ** 2))
    active_power = float(np.mean(np.abs(active) ** 2))
    signal_power = max(active_power - noise_power, 1e-12)
    return 10.0 * math.log10(signal_power / max(noise_power, 1e-12))


def main():
    parser = argparse.ArgumentParser(description="Estimate effective active-burst SNR from released HDF5 samples")
    parser.add_argument("--release_root", default=str(DEFAULT_RELEASE_ROOT))
    parser.add_argument("--split", default="train", choices=["train", "val", "test"])
    parser.add_argument("--target_snr", type=int, default=20)
    parser.add_argument("--per_class", type=int, default=8)
    parser.add_argument("--output_json", default="")
    args = parser.parse_args()

    release_root = Path(args.release_root)
    manifest_path = release_root / "manifests" / f"cisr24_{args.split}_manifest.csv"
    h5_path = release_root / "hdf5" / f"cisr24_{args.split}.h5"

    chosen = sample_rows(manifest_path, per_class=args.per_class, target_snr=args.target_snr)
    result = {"split": args.split, "target_snr": args.target_snr, "per_class": {}, "overall": {}}
    all_values = []

    with h5py.File(h5_path, "r") as handle:
        iq = handle["/iq"]
        for cls, rows in sorted(chosen.items()):
            vals = []
            for row in rows:
                idx = int(row["h5_index"]) - 1
                sample = np.asarray(iq[idx, :, :], dtype=np.float32)
                sig = sample[0] + 1j * sample[1]
                vals.append(
                    effective_snr(
                        sig,
                        start=int(row["start_offset"]),
                        active_len=int(row["active_len"]),
                    )
                )
            arr = np.asarray(vals, dtype=np.float64)
            all_values.extend(arr.tolist())
            result["per_class"][cls] = {
                "n": int(arr.size),
                "mean": float(arr.mean()),
                "std": float(arr.std(ddof=0)),
                "min": float(arr.min()),
                "max": float(arr.max()),
            }

    all_arr = np.asarray(all_values, dtype=np.float64)
    result["overall"] = {
        "n": int(all_arr.size),
        "mean": float(all_arr.mean()),
        "std": float(all_arr.std(ddof=0)),
        "min": float(all_arr.min()),
        "max": float(all_arr.max()),
    }

    print(json.dumps(result, indent=2))
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
