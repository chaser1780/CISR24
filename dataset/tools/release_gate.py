#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path


DEFAULT_THRESHOLDS = {
    "snr_mean_tol_db": 0.30,
    "snr_class_tol_db": 0.50,
    "snr_std_tol_db": 0.50,
    "snr_active_minus_noise_tol_db": 1.00,
    "active_len_class_acc_max": 0.25,
    "active_len_super_acc_max": 0.60,
    "feature_oracle_acc_max": 0.45,
}


def load_json(path: Path):
    with path.open("r") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description="Enforce full-release audit thresholds for CISR24")
    parser.add_argument("--release_root", required=True)
    parser.add_argument("--output_json", default="")
    args = parser.parse_args()

    release_root = Path(args.release_root)
    audit_root = release_root / "audit"
    validate_path = audit_root / "validate_release.json"
    shortcut_path = audit_root / "shortcut_audit_train.json"
    meta_path = audit_root / "release_meta.json"
    paper_alignment_path = audit_root / "paper_alignment.json"
    snr_grid_path = audit_root / "effective_snr_grid.json"
    waveform_conformance_path = audit_root / "waveform_conformance.json"
    naming_path = audit_root / "naming.json"

    validate_payload = load_json(validate_path)
    shortcut_payload = load_json(shortcut_path)
    paper_payload = load_json(paper_alignment_path) if paper_alignment_path.exists() else {}
    snr_grid_payload = load_json(snr_grid_path) if snr_grid_path.exists() else {}
    waveform_payload = (
        load_json(waveform_conformance_path) if waveform_conformance_path.exists() else {}
    )
    naming_payload = load_json(naming_path) if naming_path.exists() else {}
    thresholds = dict(DEFAULT_THRESHOLDS)
    meta = {}
    if meta_path.exists():
        meta = load_json(meta_path)
        thresholds.update(meta.get("config", {}).get("release_gate", {}))

    checks = {}
    checks["validate_all_true"] = all(bool(v) for v in validate_payload["checks"].values())
    checks["waveform_conformance_passed"] = waveform_payload.get("status") == "pass"
    checks["canonical_naming_passed"] = (
        naming_payload.get("status") == "pass"
        and naming_payload.get("dataset_name") == "CISR24"
        and all(naming_payload.get("checks", {}).values())
    )
    checks["release_meta_complete"] = (
        meta.get("generation_status") == "complete"
        and meta.get("generated_sample_count") == 705_600
        and meta.get("git_probe_ok") is True
        and meta.get("git_dirty") is False
        and len(str(meta.get("git_commit", ""))) == 40
        and meta.get("source_provenance", {}).get("git_clean") is True
        and len(str(meta.get("source_provenance", {}).get("source_archive_sha256", ""))) == 64
        and meta.get("paper_provenance", {}).get("sha256")
        == "b839ae9dc6111f35d59f31bea366e7f9a91297499679ef4eb64f29750a7a4648"
        and meta.get("generator_schema_version") == "CISR24-generator-2.1"
    )
    checks["paper_alignment_passed"] = (
        paper_payload.get("status") == "pass"
        and all(
            paper_payload.get("splits", {}).get(split, {}).get("iq_finite") is True
            for split in ("train", "val", "test")
        )
    )
    checks["effective_snr_grid_passed"] = snr_grid_payload.get("status") == "pass"
    actual_snr_tolerances = snr_grid_payload.get("tolerances_db", {})
    checks["effective_snr_thresholds_match"] = actual_snr_tolerances == {
        "mean_db": float(thresholds["snr_mean_tol_db"]),
        "class_db": float(thresholds["snr_class_tol_db"]),
        "class_std_db": float(thresholds["snr_std_tol_db"]),
        "active_minus_noise_db": float(
            thresholds["snr_active_minus_noise_tol_db"]
        ),
    }

    expected_shortcut_samples = 24 * 21 * 100
    shortcut_metrics = shortcut_payload.get("model_metrics", [])
    checks["shortcut_protocol_complete"] = (
        shortcut_payload.get("status") == "complete"
        and shortcut_payload.get("protocol_version") == "2.1"
        and shortcut_payload.get("train_split") == "train"
        and shortcut_payload.get("test_split") == "test"
        and shortcut_payload.get("per_class_per_snr") == 100
        and shortcut_payload.get("snr_grid") == list(range(-20, 21, 2))
        and shortcut_payload.get("train_samples") == expected_shortcut_samples
        and shortcut_payload.get("test_samples") == expected_shortcut_samples
        and shortcut_payload.get("artifacts_complete") is True
        and len(shortcut_metrics) == 12
        and all(
            math.isfinite(float(row[key])) and 0.0 <= float(row[key]) <= 1.0
            for row in shortcut_metrics
            for key in ("accuracy", "balanced_accuracy", "macro_f1")
        )
    )

    checks["active_len_class_acc_ok"] = float(shortcut_payload["active_len_only_best_class_acc"]) <= float(
        thresholds["active_len_class_acc_max"]
    )
    checks["active_len_super_acc_ok"] = float(shortcut_payload["active_len_only_best_super_acc"]) <= float(
        thresholds["active_len_super_acc_max"]
    )
    feature_oracle = shortcut_payload["sampled_feature_benchmark"].get("nearest_centroid_test_acc")
    checks["feature_oracle_ok"] = feature_oracle is not None and feature_oracle == feature_oracle and float(feature_oracle) <= float(
        thresholds["feature_oracle_acc_max"]
    )

    passed = all(checks.values())
    payload = {
        "release_root": release_root.name,
        "thresholds": thresholds,
        "checks": checks,
        "status": "passed" if passed else "failed_audit",
    }
    text = json.dumps(payload, indent=2)
    print(text)
    if args.output_json:
        Path(args.output_json).write_text(text)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
