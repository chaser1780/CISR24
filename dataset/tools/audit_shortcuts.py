#!/usr/bin/env python3
"""Run a reproducible low-dimensional shortcut audit for CISR24."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
import platform
import time
from collections import Counter, defaultdict
from pathlib import Path

import h5py
import matplotlib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    normalized_mutual_info_score,
)
from sklearn.neighbors import NearestCentroid
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_ROOT = PROJECT_ROOT / "releases" / "CISR24"
SNR_GRID = tuple(range(-20, 21, 2))
SUPERCLASS_NAMES = ("communication", "sensing", "isac")
SPECTRAL_FEATURES = (
    "bw95_mhz",
    "spectral_centroid_mhz",
    "spectral_spread_mhz",
    "crest_factor",
    "envelope_sparsity",
    "periodogram_peak_count",
)
FEATURE_MODES = {
    "record_only": ("energy_span95_samples",) + SPECTRAL_FEATURES,
    "metadata_assisted": ("active_len",) + SPECTRAL_FEATURES,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release_root", type=Path, default=DEFAULT_RELEASE_ROOT)
    parser.add_argument("--classes_csv", type=Path, default=PROJECT_ROOT / "classes.csv")
    parser.add_argument("--train_split", default="train", choices=("train", "val", "test"))
    parser.add_argument("--test_split", default="test", choices=("train", "val", "test"))
    parser.add_argument("--per_cell", type=int, default=100)
    parser.add_argument("--audit_seed", type=int, default=20260722)
    parser.add_argument("--n_permutations", type=int, default=200)
    parser.add_argument("--output_json", type=Path)
    parser.add_argument("--artifact_dir", type=Path)
    return parser.parse_args()


def load_taxonomy(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["class_id"]))
    class_names = [row["class_name"] for row in rows]
    class_to_id = {row["class_name"]: int(row["class_id"]) for row in rows}
    class_to_super = {row["class_name"]: row["super_class"] for row in rows}
    super_to_id = {name: idx for idx, name in enumerate(SUPERCLASS_NAMES)}
    return class_names, class_to_id, class_to_super, super_to_id


def read_manifest(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key.replace("-", "_"): value for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def deterministic_rank(sample_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{sample_id}".encode()).hexdigest()


def select_rows(rows, class_names, per_cell: int, seed: int):
    grouped = defaultdict(list)
    for row in rows:
        key = (row["class_name"], int(round(float(row["snr_db"]))))
        grouped[key].append(row)
    expected = {(name, snr) for name in class_names for snr in SNR_GRID}
    if set(grouped) != expected:
        missing = sorted(expected - set(grouped))
        unexpected = sorted(set(grouped) - expected)
        raise ValueError(f"manifest cell mismatch: missing={missing[:4]}, unexpected={unexpected[:4]}")
    selected = {}
    for key in sorted(grouped):
        candidates = sorted(
            grouped[key], key=lambda row: deterministic_rank(row["sample_id"], seed)
        )
        if len(candidates) < per_cell:
            raise ValueError(f"{key} has {len(candidates)} rows, requires {per_cell}")
        selected[key] = candidates[:per_cell]
    return selected


def energy_span95(signal):
    power = np.abs(signal) ** 2 + 1e-12
    cdf = np.cumsum(power)
    lo = int(np.searchsorted(cdf, 0.025 * cdf[-1]))
    hi = int(np.searchsorted(cdf, 0.975 * cdf[-1]))
    return float(hi - lo + 1)


def periodogram_features(signal, fs_hz=10e6, nfft=2048):
    spectrum = np.fft.fftshift(np.fft.fft(signal, nfft))
    psd = np.abs(spectrum) ** 2 + 1e-12
    cdf = np.cumsum(psd)
    lo = int(np.searchsorted(cdf, 0.025 * cdf[-1]))
    hi = int(np.searchsorted(cdf, 0.975 * cdf[-1]))
    bw95_mhz = (hi - lo) / nfft * fs_hz / 1e6
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / fs_hz))
    weights = psd / psd.sum()
    centroid = float((freqs * weights).sum())
    spread = float(np.sqrt(((freqs - centroid) ** 2 * weights).sum()))
    core = psd[1:-1]
    peaks = (core > psd[:-2]) & (core >= psd[2:]) & (core >= 0.10 * psd.max())
    envelope = np.abs(signal).astype(np.float64)
    rms = float(np.sqrt(np.mean(envelope**2) + 1e-12))
    crest = float(envelope.max() / max(rms, 1e-12))
    l1 = np.linalg.norm(envelope, 1)
    l2 = np.linalg.norm(envelope, 2)
    n = envelope.size
    sparsity = float(
        (np.sqrt(n) - l1 / max(l2, 1e-12)) / max(np.sqrt(n) - 1.0, 1e-12)
    )
    return np.asarray(
        [bw95_mhz, centroid / 1e6, spread / 1e6, crest, sparsity, peaks.sum()],
        dtype=np.float64,
    )


def extract_split(
    root: Path,
    split: str,
    selected,
    class_to_id,
    class_to_super,
    super_to_id,
):
    h5_path = root / "hdf5" / f"cisr24_{split}.h5"
    records = []
    record_features = []
    oracle_features = []
    with h5py.File(h5_path, "r") as handle:
        iq = handle["iq"]
        for key in sorted(selected):
            rows = sorted(selected[key], key=lambda row: int(row["h5_index"]))
            indices = np.asarray([int(row["h5_index"]) - 1 for row in rows])
            samples = np.asarray(iq[indices], dtype=np.float32)
            for row, sample in zip(rows, samples):
                signal = sample[0].astype(np.float64) + 1j * sample[1].astype(np.float64)
                start = int(float(row["start_offset"]))
                active_len = int(float(row["active_len"]))
                active = signal[start : start + active_len]
                record_features.append(
                    np.concatenate(([energy_span95(signal)], periodogram_features(signal)))
                )
                oracle_features.append(
                    np.concatenate(([float(active_len)], periodogram_features(active)))
                )
                class_name = row["class_name"]
                super_name = class_to_super[class_name]
                records.append(
                    {
                        "split": split,
                        "sample_id": row["sample_id"],
                        "class_id": class_to_id[class_name],
                        "class_name": class_name,
                        "superclass_id": super_to_id[super_name],
                        "superclass_name": super_name,
                        "snr_db": int(round(float(row["snr_db"]))),
                        "start_offset": start,
                        "active_len": active_len,
                    }
                )
    return {
        "records": records,
        "record_only": np.asarray(record_features, dtype=np.float64),
        "metadata_assisted": np.asarray(oracle_features, dtype=np.float64),
        "class_y": np.asarray([row["class_id"] for row in records], dtype=np.int64),
        "super_y": np.asarray([row["superclass_id"] for row in records], dtype=np.int64),
        "snr": np.asarray([row["snr_db"] for row in records], dtype=np.int64),
    }


def metric_payload(y_true, y_pred):
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
    }


def models(seed: int):
    return {
        "nearest_centroid": make_pipeline(StandardScaler(), NearestCentroid()),
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, solver="lbfgs", random_state=seed),
        ),
        "shallow_random_forest": RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=seed,
        ),
    }


def evaluate_models(train, test, seed: int):
    summaries = []
    by_snr = []
    confusion_rows = []
    for mode in FEATURE_MODES:
        for target, y_key in (("class", "class_y"), ("superclass", "super_y")):
            for model_name, model in models(seed).items():
                model.fit(train[mode], train[y_key])
                prediction = model.predict(test[mode])
                metrics = metric_payload(test[y_key], prediction)
                summaries.append(
                    {"mode": mode, "target": target, "model": model_name, **metrics}
                )
                matrix = confusion_matrix(test[y_key], prediction)
                for true_label in range(matrix.shape[0]):
                    for predicted_label in range(matrix.shape[1]):
                        confusion_rows.append(
                            {
                                "mode": mode,
                                "target": target,
                                "model": model_name,
                                "true_label": true_label,
                                "predicted_label": predicted_label,
                                "count": int(matrix[true_label, predicted_label]),
                            }
                        )
                for snr in SNR_GRID:
                    mask = test["snr"] == snr
                    snr_metrics = metric_payload(test[y_key][mask], prediction[mask])
                    by_snr.append(
                        {
                            "mode": mode,
                            "target": target,
                            "model": model_name,
                            "snr_db": snr,
                            **snr_metrics,
                        }
                    )
    return summaries, by_snr, confusion_rows


def majority_mapping(train_values, train_y, test_values):
    counts = defaultdict(Counter)
    for value, label in zip(train_values, train_y):
        counts[value][int(label)] += 1
    fallback = Counter(int(label) for label in train_y).most_common(1)[0][0]
    mapping = {value: counter.most_common(1)[0][0] for value, counter in counts.items()}
    return np.asarray([mapping.get(value, fallback) for value in test_values])


def metadata_lookup_oracles(train, test):
    train_len = train["metadata_assisted"][:, 0]
    test_len = test["metadata_assisted"][:, 0]
    train_support = [
        (row["start_offset"], row["active_len"]) for row in train["records"]
    ]
    test_support = [
        (row["start_offset"], row["active_len"]) for row in test["records"]
    ]
    result = {"active_len": {}, "start_offset_and_active_len": {}}
    for target, y_key in (("class", "class_y"), ("superclass", "super_y")):
        pred = majority_mapping(train_len, train[y_key], test_len)
        result["active_len"][target] = metric_payload(test[y_key], pred)
        support_pred = majority_mapping(train_support, train[y_key], test_support)
        result["start_offset_and_active_len"][target] = metric_payload(
            test[y_key], support_pred
        )
    return result


def quantile_edges(values, bins=16):
    return np.unique(np.quantile(values, np.linspace(0, 1, bins + 1)))


def apply_quantile_codes(values, edges):
    if edges.size <= 2:
        return np.zeros(values.shape[0], dtype=np.int64)
    return np.digitize(values, edges[1:-1], right=True)


def mutual_information_rows(train, test, seed: int, n_permutations: int):
    rng = np.random.default_rng(seed)
    rows = []
    for mode, feature_names in FEATURE_MODES.items():
        X_train = train[mode]
        X_test = test[mode]
        discrete = np.zeros(X_test.shape[1], dtype=bool)
        if mode == "metadata_assisted":
            discrete[0] = True
        for target, y_key in (("class", "class_y"), ("superclass", "super_y")):
            y = test[y_key]
            mi = mutual_info_classif(
                X_test, y, discrete_features=discrete, random_state=seed
            )
            for index, feature in enumerate(feature_names):
                edges = quantile_edges(X_train[:, index])
                codes = apply_quantile_codes(X_test[:, index], edges)
                nmi = float(normalized_mutual_info_score(y, codes))
                null_values = [
                    normalized_mutual_info_score(rng.permutation(y), codes)
                    for _ in range(n_permutations)
                ]
                rows.append(
                    {
                        "mode": mode,
                        "target": target,
                        "feature": feature,
                        "evaluation_split": test["records"][0]["split"],
                        "mutual_information_nats": float(mi[index]),
                        "normalized_mutual_information": nmi,
                        "permutation_nmi_mean": float(np.mean(null_values)),
                        "permutation_nmi_p95": float(np.quantile(null_values, 0.95)),
                    }
                )
    return rows


def write_csv(path: Path, rows, fieldnames=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_feature_table(path: Path, train, test):
    fields = [
        "split",
        "sample_id",
        "class_id",
        "class_name",
        "superclass_id",
        "superclass_name",
        "snr_db",
        "start_offset",
        "active_len",
    ]
    fields += [f"record_{name}" for name in FEATURE_MODES["record_only"]]
    fields += [f"oracle_{name}" for name in FEATURE_MODES["metadata_assisted"]]
    with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for payload in (train, test):
            for index, record in enumerate(payload["records"]):
                row = dict(record)
                row.update(
                    {
                        f"record_{name}": float(payload["record_only"][index, feature_index])
                        for feature_index, name in enumerate(FEATURE_MODES["record_only"])
                    }
                )
                row.update(
                    {
                        f"oracle_{name}": float(
                            payload["metadata_assisted"][index, feature_index]
                        )
                        for feature_index, name in enumerate(
                            FEATURE_MODES["metadata_assisted"]
                        )
                    }
                )
                writer.writerow(row)


def write_feature_cache(path: Path, payload):
    np.savez_compressed(
        path,
        record_only=payload["record_only"],
        metadata_assisted=payload["metadata_assisted"],
        class_y=payload["class_y"],
        super_y=payload["super_y"],
        snr=payload["snr"],
        sample_ids=np.asarray([row["sample_id"] for row in payload["records"]]),
    )


def feature_summary_rows(test, class_names):
    rows = []
    group_specs = (
        ("class", test["class_y"], tuple(class_names)),
        ("superclass", test["super_y"], SUPERCLASS_NAMES),
    )
    for mode, features in FEATURE_MODES.items():
        for group_type, labels, names in group_specs:
            for group_id, group_name in enumerate(names):
                for snr in SNR_GRID:
                    mask = (labels == group_id) & (test["snr"] == snr)
                    for feature_index, feature in enumerate(features):
                        values = test[mode][mask, feature_index]
                        rows.append(
                            {
                                "mode": mode,
                                "group_type": group_type,
                                "group_id": group_id,
                                "group_name": group_name,
                                "snr_db": snr,
                                "feature": feature,
                                "n": int(values.size),
                                "median": float(np.median(values)),
                                "q25": float(np.quantile(values, 0.25)),
                                "q75": float(np.quantile(values, 0.75)),
                            }
                        )
    return rows


def save_figure(fig, base_path: Path):
    fig.tight_layout()
    fig.savefig(base_path.with_suffix(".png"), dpi=180, bbox_inches="tight")
    fig.savefig(base_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def plot_distributions(train, mode: str, artifact_dir: Path):
    features = FEATURE_MODES[mode]
    columns = 3
    rows = math.ceil(len(features) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(12, 3.4 * rows))
    axes = np.asarray(axes).reshape(-1)
    for index, feature in enumerate(features):
        data = [
            train[mode][train["super_y"] == super_id, index]
            for super_id in range(len(SUPERCLASS_NAMES))
        ]
        axes[index].boxplot(data, tick_labels=SUPERCLASS_NAMES, showfliers=False)
        axes[index].set_title(feature)
        axes[index].tick_params(axis="x", rotation=20)
    for axis in axes[len(features) :]:
        axis.axis("off")
    save_figure(fig, artifact_dir / f"{mode}_feature_distributions")


def plot_class_medians(train, class_names, mode: str, artifact_dir: Path):
    medians = np.asarray(
        [
            np.median(train[mode][train["class_y"] == class_id], axis=0)
            for class_id in range(len(class_names))
        ]
    )
    scale = medians.std(axis=0) + 1e-9
    normalized = (medians - medians.mean(axis=0)) / scale
    fig, axis = plt.subplots(figsize=(10, 8))
    image = axis.imshow(normalized, aspect="auto", cmap="coolwarm", vmin=-2.5, vmax=2.5)
    axis.set_yticks(range(len(class_names)), labels=class_names)
    axis.set_xticks(range(len(FEATURE_MODES[mode])), labels=FEATURE_MODES[mode], rotation=35, ha="right")
    axis.set_title(f"{mode.replace('_', ' ').title()} class-median z-scores")
    fig.colorbar(image, ax=axis, label="z-score across class medians")
    save_figure(fig, artifact_dir / f"{mode}_class_median_heatmap")


def plot_active_length_contingency(train, class_names, artifact_dir: Path):
    lengths = sorted({row["active_len"] for row in train["records"]})
    matrix = np.zeros((len(class_names), len(lengths)), dtype=np.int64)
    length_to_index = {value: index for index, value in enumerate(lengths)}
    for row in train["records"]:
        matrix[row["class_id"], length_to_index[row["active_len"]]] += 1
    normalized = matrix / np.maximum(matrix.sum(axis=1, keepdims=True), 1)
    fig, axis = plt.subplots(figsize=(10, 8))
    image = axis.imshow(normalized, aspect="auto", cmap="viridis")
    axis.set_yticks(range(len(class_names)), labels=class_names)
    axis.set_xticks(range(len(lengths)), labels=lengths, rotation=35, ha="right")
    axis.set_xlabel("active length")
    axis.set_title("Class-conditional active-length distribution")
    fig.colorbar(image, ax=axis, label="fraction within class")
    save_figure(fig, artifact_dir / "active_length_contingency")


def plot_mi(mi_rows, artifact_dir: Path):
    for mode, features in FEATURE_MODES.items():
        fig, axis = plt.subplots(figsize=(10, 4.5))
        positions = np.arange(len(features))
        width = 0.36
        for offset, target in ((-width / 2, "class"), (width / 2, "superclass")):
            values = [
                next(
                    row["normalized_mutual_information"]
                    for row in mi_rows
                    if row["mode"] == mode
                    and row["target"] == target
                    and row["feature"] == feature
                )
                for feature in features
            ]
            axis.bar(positions + offset, values, width, label=target)
        axis.set_xticks(positions, labels=features, rotation=35, ha="right")
        axis.set_ylabel("normalized mutual information")
        axis.set_title(f"{mode.replace('_', ' ').title()} feature-label information")
        axis.legend()
        save_figure(fig, artifact_dir / f"{mode}_mutual_information")


def plot_accuracy_by_snr(rows, artifact_dir: Path):
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    for axis, target in zip(axes, ("class", "superclass")):
        for mode in FEATURE_MODES:
            for model_name in ("nearest_centroid", "logistic_regression", "shallow_random_forest"):
                subset = [
                    row
                    for row in rows
                    if row["mode"] == mode
                    and row["target"] == target
                    and row["model"] == model_name
                ]
                subset.sort(key=lambda row: row["snr_db"])
                axis.plot(
                    [row["snr_db"] for row in subset],
                    [row["balanced_accuracy"] for row in subset],
                    marker="o",
                    markersize=3,
                    label=f"{mode}/{model_name}",
                )
        axis.set_ylabel(f"{target} balanced accuracy")
        axis.grid(True, alpha=0.3)
    axes[-1].set_xlabel("SNR (dB)")
    axes[0].legend(fontsize=7, ncol=2)
    save_figure(fig, artifact_dir / "shortcut_accuracy_by_snr")


def relative_artifacts(root: Path, paths):
    result = []
    for path in paths:
        try:
            result.append(path.resolve().relative_to(root.resolve()).as_posix())
        except ValueError:
            result.append(str(path.resolve()))
    return result


def main() -> int:
    started_utc = dt.datetime.now(dt.timezone.utc)
    started_clock = time.perf_counter()
    args = parse_args()
    root = args.release_root.expanduser().resolve()
    output_json = args.output_json or root / "audit" / "shortcut_audit.json"
    artifact_dir = args.artifact_dir or output_json.parent / "shortcut"
    output_json = output_json.expanduser().resolve()
    artifact_dir = artifact_dir.expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    class_names, class_to_id, class_to_super, super_to_id = load_taxonomy(
        args.classes_csv
    )

    split_payloads = {}
    for split, seed_offset in ((args.train_split, 0), (args.test_split, 1)):
        manifest = root / "manifests" / f"cisr24_{split}_manifest.csv"
        rows = read_manifest(manifest)
        selected = select_rows(rows, class_names, args.per_cell, args.audit_seed + seed_offset)
        split_payloads[split] = extract_split(
            root,
            split,
            selected,
            class_to_id,
            class_to_super,
            super_to_id,
        )
    train = split_payloads[args.train_split]
    test = split_payloads[args.test_split]

    metadata_oracles = metadata_lookup_oracles(train, test)
    model_summaries, by_snr, confusion_rows = evaluate_models(
        train, test, args.audit_seed
    )
    mi_rows = mutual_information_rows(
        train, test, args.audit_seed, args.n_permutations
    )
    summary_rows = feature_summary_rows(test, class_names)

    metrics_path = artifact_dir / "shortcut_model_metrics.csv"
    snr_path = artifact_dir / "shortcut_accuracy_by_snr.csv"
    mi_path = artifact_dir / "shortcut_mutual_information.csv"
    summary_path = artifact_dir / "shortcut_feature_summary.csv"
    confusion_path = artifact_dir / "shortcut_confusion_matrices.csv"
    feature_path = artifact_dir / "shortcut_features.csv.gz"
    train_cache_path = artifact_dir / "shortcut_features_train.npz"
    test_cache_path = artifact_dir / "shortcut_features_test.npz"
    write_csv(metrics_path, model_summaries)
    write_csv(snr_path, by_snr)
    write_csv(mi_path, mi_rows)
    write_csv(summary_path, summary_rows)
    write_csv(confusion_path, confusion_rows)
    write_feature_table(feature_path, train, test)
    write_feature_cache(train_cache_path, train)
    write_feature_cache(test_cache_path, test)
    for mode in FEATURE_MODES:
        plot_distributions(train, mode, artifact_dir)
        plot_class_medians(train, class_names, mode, artifact_dir)
    plot_mi(mi_rows, artifact_dir)
    plot_accuracy_by_snr(by_snr, artifact_dir)
    plot_active_length_contingency(train, class_names, artifact_dir)

    figure_paths = sorted(artifact_dir.glob("*.png")) + sorted(artifact_dir.glob("*.pdf"))
    artifact_paths = [
        metrics_path,
        snr_path,
        mi_path,
        summary_path,
        confusion_path,
        feature_path,
        train_cache_path,
        test_cache_path,
        *figure_paths,
    ]
    nearest_oracle = next(
        row
        for row in model_summaries
        if row["mode"] == "metadata_assisted"
        and row["target"] == "class"
        and row["model"] == "nearest_centroid"
    )
    max_class_balanced = max(
        row["balanced_accuracy"]
        for row in model_summaries
        if row["target"] == "class"
    )
    max_oracle_class_balanced = max(
        row["balanced_accuracy"]
        for row in model_summaries
        if row["target"] == "class" and row["mode"] == "metadata_assisted"
    )
    result = {
        "status": "complete",
        "protocol_version": "2.1",
        "release_root": root.name,
        "started_utc": started_utc.isoformat(),
        "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "duration_seconds": time.perf_counter() - started_clock,
        "train_split": args.train_split,
        "test_split": args.test_split,
        "audit_seed": args.audit_seed,
        "per_class_per_snr": args.per_cell,
        "snr_grid": list(SNR_GRID),
        "train_samples": len(train["records"]),
        "test_samples": len(test["records"]),
        "sample_counts": {
            args.train_split: len(train["records"]),
            args.test_split: len(test["records"]),
        },
        "nfft": 2048,
        "n_permutations": args.n_permutations,
        "dependencies": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "h5py": h5py.__version__,
            "scikit_learn": sklearn.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "feature_modes": {
            "record_only": {
                "features": list(FEATURE_MODES["record_only"]),
                "uses_manifest_active_support": False,
            },
            "metadata_assisted": {
                "features": list(FEATURE_MODES["metadata_assisted"]),
                "uses_manifest_active_support": True,
                "interpretation": "privileged-information risk upper bound",
            },
        },
        "chance_baselines": {
            "class_uniform": 1.0 / len(class_names),
            "superclass_uniform": 1.0 / len(SUPERCLASS_NAMES),
            "superclass_majority_for_class_balanced_data": 10.0 / 24.0,
        },
        "metadata_only": metadata_oracles,
        "active_len_only": metadata_oracles["active_len"],
        "active_len_only_best_class_acc": metadata_oracles["active_len"]["class"]["accuracy"],
        "active_len_only_best_super_acc": metadata_oracles["active_len"]["superclass"]["accuracy"],
        "sampled_feature_benchmark": {
            "n_samples": len(train["records"]) + len(test["records"]),
            "per_class_per_snr": args.per_cell,
            "target_snr": "all",
            "feature_set": list(FEATURE_MODES["metadata_assisted"]),
            "nearest_centroid_test_acc": nearest_oracle["accuracy"],
        },
        "max_shortcut_class_balanced_accuracy": max_class_balanced,
        "max_metadata_assisted_class_balanced_accuracy": max_oracle_class_balanced,
        "model_metrics": model_summaries,
        "mutual_information": mi_rows,
        "artifacts_complete": all(path.exists() and path.stat().st_size > 0 for path in artifact_paths),
        "artifacts": relative_artifacts(root, artifact_paths),
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, indent=2)
    output_json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["artifacts_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
