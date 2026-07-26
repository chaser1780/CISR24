#!/usr/bin/env python3
"""Audit active-burst SNR across every CISR24 split, class, and SNR level."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import h5py
import numpy as np


SPLITS = ("train", "val", "test")
EXPECTED_SNR = tuple(range(-20, 21, 2))
DEFAULT_TOLERANCES = {
    "mean_db": 0.30,
    "class_db": 0.50,
    "class_std_db": 0.50,
    "active_minus_noise_db": 1.00,
}


def normalized_rows(path: Path, per_cell: int):
    selected = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for source in csv.DictReader(handle):
            row = {key.replace("-", "_"): value for key, value in source.items()}
            key = (row["class_name"], int(round(float(row["snr_db"]))))
            if len(selected[key]) < per_cell:
                selected[key].append(row)
    return selected


def measure_energy(iq: h5py.Dataset, rows) -> tuple[float, int, float, int]:
    if not rows:
        return 0.0, 0, 0.0, 0
    indices = np.asarray([int(row["h5_index"]) - 1 for row in rows])
    samples = np.asarray(iq[indices], dtype=np.float64)
    signal = samples[:, 0, :] + 1j * samples[:, 1, :]
    power = np.abs(signal) ** 2
    starts = np.asarray([int(float(row["start_offset"])) for row in rows])
    lengths = np.asarray([int(float(row["active_len"])) for row in rows])
    positions = np.arange(signal.shape[1])[None, :]
    active_mask = (positions >= starts[:, None]) & (
        positions < (starts + lengths)[:, None]
    )
    active_energy = float(power[active_mask].sum())
    active_count = int(active_mask.sum())
    noise_energy = float(power[~active_mask].sum())
    noise_count = int((~active_mask).sum())
    return active_energy, active_count, noise_energy, noise_count


def estimate_active_minus_noise(measurement: tuple[float, int, float, int]) -> float:
    active_energy, active_count, noise_energy, noise_count = measurement
    if active_count == 0 or noise_count == 0:
        return float("nan")
    active_power = active_energy / active_count
    noise_power = noise_energy / noise_count
    clean_power = active_power - noise_power
    if clean_power <= 0 or noise_power <= 0:
        return float("nan")
    return 10.0 * math.log10(clean_power / noise_power)


def estimate_from_noise_reference(measurement: tuple[float, int, float, int]) -> float:
    _, _, noise_energy, noise_count = measurement
    if noise_count == 0:
        return float("nan")
    noise_power = noise_energy / noise_count
    if noise_power <= 0:
        return float("nan")
    # Every clean active burst is normalized to unit average power before AWGN.
    return -10.0 * math.log10(noise_power)


def load_tolerances(root: Path, args: argparse.Namespace) -> dict[str, float]:
    tolerances = dict(DEFAULT_TOLERANCES)
    meta_path = root / "audit" / "release_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        configured = meta.get("config", {}).get("release_gate", {})
        mappings = {
            "snr_mean_tol_db": "mean_db",
            "snr_class_tol_db": "class_db",
            "snr_std_tol_db": "class_std_db",
            "snr_active_minus_noise_tol_db": "active_minus_noise_db",
        }
        for source, target in mappings.items():
            if source in configured:
                tolerances[target] = float(configured[source])
    overrides = {
        "mean_db": args.mean_tolerance_db,
        "class_db": args.class_tolerance_db,
        "class_std_db": args.class_std_tolerance_db,
        "active_minus_noise_db": args.active_minus_noise_tolerance_db,
    }
    for name, value in overrides.items():
        if value is not None:
            tolerances[name] = value
    return tolerances


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--per-cell", type=int, default=200)
    parser.add_argument("--mean-tolerance-db", type=float)
    parser.add_argument("--class-tolerance-db", type=float)
    parser.add_argument("--class-std-tolerance-db", type=float)
    parser.add_argument("--active-minus-noise-tolerance-db", type=float)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    root = args.release_root.expanduser().resolve()
    tolerances = load_tolerances(root, args)
    cells = {}
    aggregates = {}
    diagnostic_failures = []
    gate_failures = []
    selection_failures = []
    with (root / "classes.csv").open(newline="", encoding="utf-8") as handle:
        class_names = [row["class_name"] for row in csv.DictReader(handle)]
    expected_keys = {
        (class_name, snr_db)
        for class_name in class_names
        for snr_db in EXPECTED_SNR
    }
    for split in SPLITS:
        manifest = root / "manifests" / f"cisr24_{split}_manifest.csv"
        h5_path = root / "hdf5" / f"cisr24_{split}.h5"
        selected = normalized_rows(manifest, args.per_cell)
        actual_keys = set(selected)
        for class_name, snr_db in sorted(expected_keys - actual_keys):
            selection_failures.append(f"{split}/{class_name}/{snr_db}dB: missing cell")
        for class_name, snr_db in sorted(actual_keys - expected_keys):
            selection_failures.append(f"{split}/{class_name}/{snr_db}dB: unexpected cell")
        split_snr_measurements = defaultdict(lambda: [0.0, 0, 0.0, 0])
        with h5py.File(h5_path, "r") as handle:
            iq = handle["iq"]
            for (class_name, target_snr), rows in sorted(selected.items()):
                if len(rows) != args.per_cell:
                    selection_failures.append(
                        f"{split}/{class_name}/{target_snr}dB: "
                        f"selected {len(rows)}, expected {args.per_cell}"
                    )
                measurement = measure_energy(iq, rows)
                estimate = estimate_from_noise_reference(measurement)
                error = estimate - target_snr
                active_minus_noise = estimate_active_minus_noise(measurement)
                key = f"{split}/{class_name}/{target_snr}dB"
                passed = np.isfinite(estimate) and abs(error) <= tolerances["class_db"]
                cells[key] = {
                    "n": len(rows),
                    "target_snr_db": target_snr,
                    "noise_reference_snr_db": estimate,
                    "noise_reference_error_db": error,
                    "active_minus_noise_snr_db": active_minus_noise,
                    "passed": bool(passed),
                }
                if not passed:
                    diagnostic_failures.append(key)
                aggregate = split_snr_measurements[target_snr]
                for idx, value in enumerate(measurement):
                    aggregate[idx] += value

        for target_snr in EXPECTED_SNR:
            measurement = tuple(split_snr_measurements[target_snr])
            noise_estimate = estimate_from_noise_reference(measurement)
            noise_error = noise_estimate - target_snr
            active_estimate = estimate_active_minus_noise(measurement)
            active_error = active_estimate - target_snr
            class_errors = [
                cells[f"{split}/{class_name}/{target_snr}dB"][
                    "noise_reference_error_db"
                ]
                for class_name in class_names
                if f"{split}/{class_name}/{target_snr}dB" in cells
            ]
            error_std = float(np.std(class_errors)) if class_errors else float("nan")
            key = f"{split}/{target_snr}dB"
            passed = (
                np.isfinite(noise_estimate)
                and abs(noise_error) <= tolerances["mean_db"]
                and np.isfinite(error_std)
                and error_std <= tolerances["class_std_db"]
                and np.isfinite(active_estimate)
                and abs(active_error) <= tolerances["active_minus_noise_db"]
            )
            aggregates[key] = {
                "n": sum(
                    len(selected.get((class_name, target_snr), ()))
                    for class_name in class_names
                ),
                "target_snr_db": target_snr,
                "noise_reference_snr_db": noise_estimate,
                "noise_reference_error_db": noise_error,
                "class_error_std_db": error_std,
                "active_minus_noise_snr_db": active_estimate,
                "active_minus_noise_error_db": active_error,
                "passed": bool(passed),
            }
            if not passed:
                gate_failures.append(key)

    status = (
        "pass"
        if not gate_failures and not diagnostic_failures and not selection_failures
        else "fail"
    )
    payload = {
        "release_root": root.name,
        "method": (
            "per-class inactive-noise calibration plus pooled "
            "active-minus-inactive normalization check"
        ),
        "per_cell": args.per_cell,
        "tolerances_db": tolerances,
        "total_cells": len(cells),
        "total_aggregates": len(aggregates),
        "gate_failures": gate_failures,
        "selection_failures": selection_failures,
        "failed_cells": diagnostic_failures,
        "status": status,
        "aggregates": aggregates,
        "cells": cells,
    }
    text = json.dumps(payload, indent=2)
    print(text)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
