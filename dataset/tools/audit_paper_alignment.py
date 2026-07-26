#!/usr/bin/env python3
"""Validate a CISR24 release against Tables II and III of the paper."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import h5py
import numpy as np


SPLITS = ("train", "val", "test")
EXPECTED_PER_CELL = {"train": 1000, "val": 200, "test": 200}
EXPECTED_SNR = tuple(range(-20, 21, 2))
EXPECTED_ACTIVE_LENGTHS = {576, 640, 704, 768, 832}
EXPECTED_RELEASE_NAME = "CISR24"
EXPECTED_PAPER_SHA256 = "b839ae9dc6111f35d59f31bea366e7f9a91297499679ef4eb64f29750a7a4648"

CLASS_ROWS = (
    (0, "communication", "BPSK", "single-carrier-linear-modulation"),
    (1, "communication", "QPSK", "single-carrier-linear-modulation"),
    (2, "communication", "8PSK", "single-carrier-linear-modulation"),
    (3, "communication", "16QAM", "single-carrier-linear-modulation"),
    (4, "communication", "4FSK", "continuous-phase-frequency-modulation"),
    (5, "communication", "8FSK", "continuous-phase-frequency-modulation"),
    (6, "communication", "GMSK", "continuous-phase-frequency-modulation"),
    (7, "communication", "OFDM-BPSK", "ofdm-communication"),
    (8, "communication", "OFDM-QPSK", "ofdm-communication"),
    (9, "communication", "OFDM-16QAM", "ofdm-communication"),
    (10, "sensing", "Rect", "intra-pulse-sensing"),
    (11, "sensing", "Barker", "intra-pulse-sensing"),
    (12, "sensing", "LFM", "intra-pulse-sensing"),
    (13, "sensing", "Costas", "intra-pulse-sensing"),
    (14, "sensing", "Frank", "intra-pulse-sensing"),
    (15, "sensing", "P4", "intra-pulse-sensing"),
    (16, "isac", "LFM-BPSK", "lfm-psk"),
    (17, "isac", "LFM-QPSK", "lfm-psk"),
    (18, "isac", "LFM-8PSK", "lfm-psk"),
    (19, "isac", "LFM-MSK", "lfm-cpm"),
    (20, "isac", "LFM-GMSK", "lfm-cpm"),
    (21, "isac", "OFDM-LFM-BPSK", "ofdm-lfm"),
    (22, "isac", "OFDM-LFM-QPSK", "ofdm-lfm"),
    (23, "isac", "OFDM-LFM-16QAM", "ofdm-lfm"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument(
        "--full-iq-scan",
        action="store_true",
        help="read every I/Q value and reject NaN or infinity",
    )
    parser.add_argument(
        "--redact-root",
        action="store_true",
        help="store only the release directory name in the JSON report",
    )
    return parser.parse_args()


def field(row: dict[str, str], canonical: str) -> str:
    if canonical in row:
        return row[canonical]
    legacy = canonical.replace("-", "_")
    if legacy in row:
        return row[legacy]
    raise KeyError(f"manifest field is missing: {canonical}")


def optional_field(row: dict[str, str], canonical: str) -> str:
    try:
        return field(row, canonical)
    except KeyError:
        return ""


def resolve_split_files(root: Path, split: str) -> tuple[Path, Path]:
    canonical_manifest = root / "manifests" / f"cisr24_{split}_manifest.csv"
    canonical_h5 = root / "hdf5" / f"cisr24_{split}.h5"
    if canonical_manifest.exists() and canonical_h5.exists():
        return canonical_manifest, canonical_h5
    raise FileNotFoundError(f"missing canonical CISR24 files for split={split}")


def dataset_key(handle: h5py.File, canonical: str) -> str:
    if canonical in handle:
        return canonical
    legacy = canonical.replace("-", "_")
    if legacy in handle:
        return legacy
    raise KeyError(f"missing HDF5 dataset /{canonical}")


def numeric(value: str) -> float | None:
    if value in {"", "NaN", "nan", "none"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def scan_iq(iq: h5py.Dataset, chunk_size: int = 512) -> bool:
    for start in range(0, iq.shape[0], chunk_size):
        block = np.asarray(iq[start : start + chunk_size])
        if not np.isfinite(block).all():
            return False
    return True


def main() -> int:
    args = parse_args()
    root = args.release_root.expanduser().resolve()
    blockers: list[str] = []
    warnings: list[str] = []
    split_results = {}
    per_class_values = defaultdict(lambda: defaultdict(set))
    split_sample_ids: dict[str, set[str]] = {}
    split_seeds: dict[str, set[int]] = {}
    expected_by_name = {row[2]: row for row in CLASS_ROWS}
    classes_path = root / "classes.csv"
    if classes_path.exists():
        with classes_path.open(newline="", encoding="utf-8") as handle:
            class_rows = list(csv.DictReader(handle))
        actual_taxonomy = [
            (
                int(row["class_id"]),
                row["super_class"],
                row["class_name"],
                row["family"],
            )
            for row in class_rows
        ]
        if actual_taxonomy != list(CLASS_ROWS):
            blockers.append("classes.csv does not match the paper taxonomy and families")
    else:
        blockers.append("missing classes.csv")
    labels_path = root / "label_names.txt"
    if labels_path.exists():
        labels = labels_path.read_text(encoding="utf-8").splitlines()
        if labels != [row[2] for row in CLASS_ROWS]:
            blockers.append("label_names.txt does not match paper class order")
    else:
        blockers.append("missing label_names.txt")
    release_meta_path = root / "audit" / "release_meta.json"
    release_meta = {}
    if release_meta_path.exists():
        release_meta = json.loads(release_meta_path.read_text(encoding="utf-8"))
    else:
        blockers.append("missing audit/release_meta.json")

    for split in SPLITS:
        manifest_path, h5_path = resolve_split_files(root, split)

        counts = Counter()
        sample_ids = set()
        seeds = set()
        seed_rows = 0
        mismatch_count = 0
        h5_indices = set()
        release_names = set()
        families = defaultdict(set)
        global_values = defaultdict(set)

        with h5py.File(h5_path, "r") as handle:
            required_keys = {"iq", "class-id", "snr-db", "sample-index"}
            if not required_keys.issubset(set(handle.keys())):
                blockers.append(f"{split}: HDF5 does not use the canonical hyphenated schema")
            iq = handle[dataset_key(handle, "iq")]
            expected_rows = 24 * len(EXPECTED_SNR) * EXPECTED_PER_CELL[split]
            scalar_specs = {
                "class-id": (np.dtype("uint16"), (1, expected_rows)),
                "snr-db": (np.dtype("float32"), (1, expected_rows)),
                "sample-index": (np.dtype("uint32"), (1, expected_rows)),
            }
            for name, (expected_dtype, expected_shape) in scalar_specs.items():
                dataset = handle[dataset_key(handle, name)]
                if dataset.dtype != expected_dtype or dataset.shape != expected_shape:
                    blockers.append(
                        f"{split}: /{name} is {dataset.shape} {dataset.dtype}, "
                        f"expected {expected_shape} {expected_dtype}"
                    )
            class_ds = np.asarray(handle[dataset_key(handle, "class-id")]).reshape(-1)
            snr_ds = np.asarray(handle[dataset_key(handle, "snr-db")]).reshape(-1)
            sample_ds = np.asarray(handle[dataset_key(handle, "sample-index")]).reshape(-1)
            if iq.shape != (expected_rows, 2, 1024) or iq.dtype != np.dtype("float32"):
                blockers.append(
                    f"{split}: /iq is {iq.shape} {iq.dtype}, expected "
                    f"({expected_rows}, 2, 1024) float32"
                )
            finite = scan_iq(iq) if args.full_iq_scan else None
            if finite is False:
                blockers.append(f"{split}: /iq contains NaN or infinity")

            with manifest_path.open(newline="", encoding="utf-8") as manifest:
                reader = csv.DictReader(manifest)
                canonical_fields = {
                    "sample-id",
                    "split",
                    "h5-rel-path",
                    "h5-dataset",
                    "h5-index",
                    "class-id",
                    "super-class",
                    "class-name",
                    "waveform-family",
                    "snr-db",
                    "fs-hz",
                    "n-samples",
                    "seed",
                    "active-len",
                    "start-offset",
                    "channel-profile",
                    "release-name",
                    "iid-or-ood",
                    "effective-snr-basis",
                    "gmsk-bt",
                    "cpfsk-modulation-index",
                    "cpfsk-tone-spacing-hz",
                }
                if not canonical_fields.issubset(set(reader.fieldnames or ())):
                    blockers.append(f"{split}: manifest does not use canonical kebab-case fields")
                for row_number, row in enumerate(reader, start=1):
                    class_name = field(row, "class-name")
                    class_id = int(field(row, "class-id"))
                    snr_db = int(round(float(field(row, "snr-db"))))
                    h5_index = int(field(row, "h5-index"))
                    if h5_index in h5_indices:
                        mismatch_count += 1
                    h5_indices.add(h5_index)
                    sample_id = field(row, "sample-id")
                    seed = int(field(row, "seed"))
                    sample_index = int(sample_id.removeprefix("sample_"))
                    expected = expected_by_name.get(class_name)
                    if expected is None or (class_id, field(row, "super-class")) != expected[:2]:
                        mismatch_count += 1
                    family = field(row, "waveform-family")
                    families[class_name].add(family)
                    counts[(class_name, snr_db)] += 1
                    sample_ids.add(sample_id)
                    seeds.add(seed)
                    seed_rows += 1
                    release_names.add(field(row, "release-name"))
                    for name in (
                        "fs-hz",
                        "n-samples",
                        "channel-profile",
                        "iid-or-ood",
                        "effective-snr-basis",
                        "h5-dataset",
                        "h5-rel-path",
                    ):
                        global_values[name].add(field(row, name))
                    active_len = int(float(field(row, "active-len")))
                    start_offset = int(float(field(row, "start-offset")))
                    if start_offset < 0 or start_offset + active_len > 1024:
                        mismatch_count += 1

                    index = h5_index - 1
                    if (
                        index < 0
                        or index >= class_ds.size
                        or int(class_ds[index]) != class_id
                        or int(round(float(snr_ds[index]))) != snr_db
                        or int(sample_ds[index]) != sample_index
                    ):
                        mismatch_count += 1

                    for name in (
                        "active-len",
                        "sps",
                        "symbol-rate-hz",
                        "rrc-beta",
                        "nfft",
                        "cp-len",
                        "n-active",
                        "ofdm-num-symbols",
                        "chirp-bw-hz",
                        "chirp-dir",
                        "barker-len",
                        "costas-len",
                        "costas-df-hz",
                        "frank-order",
                        "p4-len",
                        "gmsk-bt",
                        "cpfsk-modulation-index",
                        "cpfsk-tone-spacing-hz",
                    ):
                        value = optional_field(row, name)
                        parsed = numeric(value)
                        if parsed is not None:
                            per_class_values[class_name][name].add(parsed)
                        elif name == "chirp-dir" and value not in {"", "none"}:
                            per_class_values[class_name][name].add(value)

            if release_names != {EXPECTED_RELEASE_NAME}:
                blockers.append(f"{split}: release-name is not CISR24")
            h5_release = str(handle.attrs.get("release_name", ""))
            if h5_release != EXPECTED_RELEASE_NAME:
                blockers.append(f"{split}: HDF5 release_name is not CISR24")
            expected_attrs = {
                "split": split,
                "effective_snr_basis": "active_burst",
            }
            for name, expected_value in expected_attrs.items():
                actual = handle.attrs.get(name)
                if isinstance(actual, bytes):
                    actual = actual.decode()
                if str(actual) != expected_value:
                    blockers.append(f"{split}: HDF5 attribute {name}={actual!r}")
            for name, expected_value in (("fs_hz", 10_000_000), ("record_len", 1024), ("total_count", expected_rows)):
                raw_value = handle.attrs.get(name)
                actual = np.asarray(raw_value).reshape(-1) if raw_value is not None else np.asarray([])
                if actual.size != 1 or int(round(float(actual[0]))) != expected_value:
                    blockers.append(f"{split}: HDF5 attribute {name} is incorrect")

        expected_globals = {
            "fs-hz": {"10000000.000000", "10000000"},
            "n-samples": {"1024"},
            "channel-profile": {"clean_awgn"},
            "iid-or-ood": {"iid"},
            "effective-snr-basis": {"active_burst"},
            "h5-dataset": {"/iq"},
            "h5-rel-path": {f"hdf5/cisr24_{split}.h5"},
        }
        for name, allowed in expected_globals.items():
            if not global_values[name] or not global_values[name].issubset(allowed):
                blockers.append(f"{split}: manifest {name}={sorted(global_values[name])}")

        wrong_cells = {
            f"{name}@{snr}": counts[(name, snr)]
            for _, _, name, _ in CLASS_ROWS
            for snr in EXPECTED_SNR
            if counts[(name, snr)] != EXPECTED_PER_CELL[split]
        }
        if wrong_cells:
            blockers.append(f"{split}: {len(wrong_cells)} class/SNR cells have wrong counts")
        if mismatch_count:
            blockers.append(f"{split}: {mismatch_count} manifest/HDF5 taxonomy mismatches")
        expected_rows = 24 * len(EXPECTED_SNR) * EXPECTED_PER_CELL[split]
        if h5_indices != set(range(1, expected_rows + 1)):
            blockers.append(f"{split}: h5-index does not cover 1..{expected_rows} exactly once")
        if len(sample_ids) != seed_rows:
            blockers.append(f"{split}: duplicate sample IDs")
        if len(seeds) != seed_rows:
            blockers.append(
                f"{split}: {seed_rows - len(seeds)} rows reuse a seed within the split"
            )

        wrong_families = {
            name: sorted(families[name])
            for _, _, name, expected_family in CLASS_ROWS
            if families[name] != {expected_family}
        }
        if wrong_families:
            blockers.append(f"{split}: waveform-family does not match Table II")

        split_sample_ids[split] = sample_ids
        split_seeds[split] = seeds
        split_results[split] = {
            "rows": seed_rows,
            "unique_sample_ids": len(sample_ids),
            "unique_seeds": len(seeds),
            "wrong_count_cells": wrong_cells,
            "wrong_families": wrong_families,
            "manifest_hdf5_mismatches": mismatch_count,
            "iq_finite": finite,
            "canonical_names": True,
        }

    for index, left in enumerate(SPLITS):
        for right in SPLITS[index + 1 :]:
            if split_sample_ids[left] & split_sample_ids[right]:
                blockers.append(f"sample IDs overlap between {left} and {right}")
            if split_seeds[left] & split_seeds[right]:
                blockers.append(f"seeds overlap between {left} and {right}")

    class_results = []
    for class_id, super_class, class_name, family in CLASS_ROWS:
        values = per_class_values[class_name]
        issues = []
        active = {int(value) for value in values["active-len"]}
        if class_name not in {"OFDM-BPSK", "OFDM-QPSK", "OFDM-16QAM", "OFDM-LFM-BPSK", "OFDM-LFM-QPSK", "OFDM-LFM-16QAM"}:
            if active != EXPECTED_ACTIVE_LENGTHS:
                issues.append(f"active-len={sorted(active)}")
        else:
            if active != {576, 864}:
                issues.append(f"active-len={sorted(active)}")

        if class_name in {"BPSK", "QPSK", "8PSK", "16QAM"}:
            if values["sps"] != {4.0} or values["symbol-rate-hz"] != {2_500_000.0}:
                issues.append("single-carrier rate/sps mismatch")
            if values["rrc-beta"] != {0.25, 0.35}:
                issues.append("RRC beta mismatch")
        if class_name in {"4FSK", "8FSK"}:
            if values["cpfsk-modulation-index"] and values["cpfsk-modulation-index"] != {0.5}:
                issues.append("CPFSK modulation-index mismatch")
            if not values["cpfsk-modulation-index"]:
                issues.append("CPFSK modulation index missing")
            if values["cpfsk-tone-spacing-hz"] != {625_000.0}:
                issues.append("CPFSK spacing mismatch")
            if values["sps"] != {8.0} or values["symbol-rate-hz"] != {1_250_000.0}:
                issues.append("CPFSK rate/sps does not realize 0.625 MHz spacing")
        if class_name in {"GMSK", "LFM-GMSK"}:
            if values["gmsk-bt"] and values["gmsk-bt"] != {0.3}:
                issues.append("GMSK BT mismatch")
            if not values["gmsk-bt"]:
                issues.append("GMSK BT missing")
        if class_name.startswith("OFDM-"):
            if values["nfft"] != {256.0} or values["cp-len"] != {32.0}:
                issues.append("OFDM Nfft/Ncp mismatch")
            if values["n-active"] != {96.0, 128.0}:
                issues.append("OFDM active-carrier mismatch")
            if values["ofdm-num-symbols"] != {2.0, 3.0}:
                issues.append("OFDM symbol-count mismatch")
        if class_name == "Barker" and values["barker-len"] != {7.0, 11.0, 13.0}:
            issues.append("Barker length mismatch")
        if class_name == "Costas":
            if values["costas-len"] != {7.0, 11.0, 13.0}:
                issues.append("Costas length mismatch")
            if values["costas-df-hz"] != {250_000.0, 500_000.0}:
                issues.append("Costas frequency-step mismatch")
        if class_name == "Frank" and values["frank-order"] != {4.0}:
            issues.append("Frank order mismatch")
        if class_name == "P4" and values["p4-len"] != {16.0, 32.0}:
            issues.append("P4 length mismatch")
        if class_name == "LFM" or class_name.startswith("LFM-") or class_name.startswith("OFDM-LFM-"):
            if values["chirp-bw-hz"] != {2_000_000.0, 3_000_000.0, 4_000_000.0}:
                issues.append("chirp bandwidth mismatch")
            if values["chirp-dir"] != {"up", "down"}:
                issues.append("chirp direction mismatch")
        if issues:
            blockers.append(f"{class_name}: {'; '.join(issues)}")
        class_results.append(
            {
                "class_id": class_id,
                "super_class": super_class,
                "class_name": class_name,
                "waveform_family": family,
                "status": "fail" if issues else "pass",
                "issues": issues,
            }
        )

    config = release_meta.get("config", {})
    config_checks = {
        "fs_hz": 10_000_000,
        "record_len": 1024,
        "snr_db": list(EXPECTED_SNR),
        "counts_per_snr": EXPECTED_PER_CELL,
        "rrc_rolloff_choices": [0.25, 0.35],
        "rrc_span_symbols": 8,
        "single_carrier_sps": 4,
        "gmsk_bt": 0.3,
        "cpfsk_sps": 8,
        "cpfsk_modulation_index": 0.5,
        "cpfsk_tone_spacing_hz": 625_000,
        "ofdm_nfft": 256,
        "ofdm_cp": 32,
        "ofdm_active_choices": [96, 128],
        "ofdm_symbol_choices": [2, 3],
        "ofdm_pilot_count": 4,
        "chirp_bandwidth_choices_hz": [2_000_000, 3_000_000, 4_000_000],
        "costas_frequency_step_choices_hz": [250_000, 500_000],
        "ofdm_lfm_chirp_layout": "comb_data_every4",
        "ofdm_lfm_mix_alpha": 0.35,
        "ofdm_lfm_regular_pilots": True,
    }
    for name, expected in config_checks.items():
        if config.get(name) != expected:
            blockers.append(f"release_meta config {name} does not match the paper")
    meta_release_name = str(release_meta.get("release_name", ""))
    if release_meta and meta_release_name != EXPECTED_RELEASE_NAME:
        blockers.append("release_meta release_name is not CISR24")
    if release_meta.get("generation_status") != "complete":
        blockers.append("release_meta generation_status is not complete")
    if release_meta.get("generated_sample_count") != 705_600:
        blockers.append("release_meta generated_sample_count is not 705600")
    if release_meta.get("git_probe_ok") is not True:
        blockers.append("release_meta did not obtain a valid Git provenance probe")
    git_commit = str(release_meta.get("git_commit", ""))
    if len(git_commit) != 40 or any(char not in "0123456789abcdef" for char in git_commit.lower()):
        blockers.append("release_meta git_commit is not a full 40-character commit")
    if release_meta.get("git_dirty") is not False:
        blockers.append("release_meta source tree is not clean")
    source_provenance = release_meta.get("source_provenance", {})
    if (
        source_provenance.get("git_clean") is not True
        or source_provenance.get("git_commit") != git_commit
        or len(str(source_provenance.get("source_archive_sha256", ""))) != 64
        or len(str(source_provenance.get("generator_sha256", ""))) != 64
        or len(str(source_provenance.get("config_sha256", ""))) != 64
    ):
        blockers.append("release_meta source provenance is incomplete")
    if release_meta.get("paper_provenance", {}).get("sha256") != EXPECTED_PAPER_SHA256:
        blockers.append("release_meta paper SHA-256 is not the authoritative main.pdf")
    if release_meta.get("generator_schema_version") != "CISR24-generator-2.1":
        blockers.append("release_meta generator schema version is incorrect")

    if not args.full_iq_scan:
        blockers.append("full I/Q finite scan was not requested")

    result = {
        "dataset": "CISR24",
        "paper_reference": "main.pdf Tables II and III",
        "release_root": root.name if args.redact_root else str(root),
        "status": "pass" if not blockers else "fail",
        "release_blockers": blockers,
        "warnings": warnings,
        "splits": split_results,
        "classes": class_results,
    }
    text = json.dumps(result, indent=2, sort_keys=False)
    print(text)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
