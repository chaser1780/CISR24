import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np


DATASET_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATASET_ROOT / "loaders"))

from cisr24 import CISR24Split  # noqa: E402


class CISR24SmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = DATASET_ROOT / "smoke_v1"
        manifest = cls.root / "manifests" / "cisr24_train_manifest.csv"
        with manifest.open(newline="", encoding="utf-8") as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_taxonomy_and_seed_uniqueness(self):
        self.assertEqual(len(self.rows), 24)
        self.assertEqual([int(row["class-id"]) for row in self.rows], list(range(24)))
        self.assertEqual(len({row["seed"] for row in self.rows}), 24)
        self.assertEqual(
            {row["super-class"] for row in self.rows},
            {"communication", "sensing", "isac"},
        )

    def test_paper_schema_and_iq(self):
        path = self.root / "hdf5" / "cisr24_train.h5"
        with h5py.File(path, "r") as handle:
            self.assertEqual(set(handle), {"iq", "class-id", "snr-db", "sample-index"})
            self.assertEqual(handle["iq"].shape, (24, 2, 1024))
            self.assertEqual(handle["iq"].dtype, np.dtype("float32"))
            self.assertTrue(np.isfinite(handle["iq"][:]).all())
            self.assertEqual(handle.attrs["release_name"], "CISR24")

    def test_barker_and_costas_use_paper_active_lengths(self):
        expected = {"576", "640", "704", "768", "832"}
        by_name = {row["class-name"]: row for row in self.rows}
        self.assertIn(by_name["Barker"]["active-len"], expected)
        self.assertIn(by_name["Costas"]["active-len"], expected)
        for class_name in ("Barker", "Costas"):
            row = by_name[class_name]
            self.assertEqual(row["chip-samples"], "NaN")
            self.assertLessEqual(
                float(row["chip-samples-min"]), float(row["chip-samples-max"])
            )

    def test_cpfsk_rate_realizes_paper_tone_spacing(self):
        by_name = {row["class-name"]: row for row in self.rows}
        for class_name in ("4FSK", "8FSK"):
            row = by_name[class_name]
            self.assertEqual(float(row["sps"]), 8.0)
            self.assertEqual(float(row["symbol-rate-hz"]), 1_250_000.0)
            self.assertEqual(float(row["cpfsk-modulation-index"]), 0.5)
            self.assertEqual(float(row["cpfsk-tone-spacing-hz"]), 625_000.0)

    def test_gmsk_bt_is_explicit(self):
        by_name = {row["class-name"]: row for row in self.rows}
        for class_name in ("GMSK", "LFM-GMSK"):
            self.assertEqual(float(by_name[class_name]["gmsk-bt"]), 0.3)

    def test_loader(self):
        with CISR24Split(self.root, "train") as dataset:
            sample = dataset[0]
            self.assertEqual(len(dataset), 24)
            self.assertEqual(sample["iq"].shape, (2, 1024))
            self.assertEqual(sample["class_id"], 0)
            self.assertEqual(sample["sample_index"], 1)

    def test_release_gate_requires_passing_paper_and_snr_audits(self):
        gate = DATASET_ROOT / "tools" / "release_gate.py"
        base_validate = {"checks": {"complete": True}}
        base_shortcut = {
            "status": "complete",
            "protocol_version": "2.1",
            "train_split": "train",
            "test_split": "test",
            "per_class_per_snr": 100,
            "snr_grid": list(range(-20, 21, 2)),
            "train_samples": 50_400,
            "test_samples": 50_400,
            "artifacts_complete": True,
            "model_metrics": [
                {
                    "accuracy": 0.2,
                    "balanced_accuracy": 0.2,
                    "macro_f1": 0.2,
                }
                for _ in range(12)
            ],
            "active_len_only_best_class_acc": 0.1,
            "active_len_only_best_super_acc": 0.2,
            "sampled_feature_benchmark": {"nearest_centroid_test_acc": 0.3},
        }
        passing_paper = {
            "status": "pass",
            "splits": {
                split: {"iq_finite": True} for split in ("train", "val", "test")
            },
        }
        passing_snr = {
            "status": "pass",
            "tolerances_db": {
                "mean_db": 0.3,
                "class_db": 0.5,
                "class_std_db": 0.5,
                "active_minus_noise_db": 1.0,
            },
        }
        cases = (
            (None, None, 1),
            ({**passing_paper, "status": "fail"}, passing_snr, 1),
            (
                {
                    **passing_paper,
                    "splits": {
                        "train": {"iq_finite": False},
                        "val": {"iq_finite": True},
                        "test": {"iq_finite": True},
                    },
                },
                passing_snr,
                1,
            ),
            (passing_paper, {**passing_snr, "status": "fail"}, 1),
            (
                passing_paper,
                {
                    **passing_snr,
                    "tolerances_db": {
                        **passing_snr["tolerances_db"],
                        "class_db": 0.6,
                    },
                },
                1,
            ),
            (passing_paper, passing_snr, 0),
        )
        for paper_payload, snr_payload, expected_code in cases:
            with self.subTest(
                paper=None if paper_payload is None else paper_payload["status"],
                snr=None if snr_payload is None else snr_payload["status"],
                expected=expected_code,
            ):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    audit = root / "audit"
                    audit.mkdir()
                    (audit / "validate_release.json").write_text(
                        json.dumps(base_validate), encoding="utf-8"
                    )
                    (audit / "shortcut_audit_train.json").write_text(
                        json.dumps(base_shortcut), encoding="utf-8"
                    )
                    if paper_payload is not None:
                        (audit / "paper_alignment.json").write_text(
                            json.dumps(paper_payload), encoding="utf-8"
                        )
                    if snr_payload is not None:
                        (audit / "effective_snr_grid.json").write_text(
                            json.dumps(snr_payload), encoding="utf-8"
                        )
                    (audit / "release_meta.json").write_text(
                        json.dumps(
                            {
                                "generation_status": "complete",
                                "generated_sample_count": 705_600,
                                "git_probe_ok": True,
                                "git_dirty": False,
                                "git_commit": "a" * 40,
                                "source_provenance": {
                                    "git_clean": True,
                                    "source_archive_sha256": "b" * 64,
                                },
                                "paper_provenance": {
                                    "sha256": "b839ae9dc6111f35d59f31bea366e7f9a91297499679ef4eb64f29750a7a4648"
                                },
                                "generator_schema_version": "CISR24-generator-2.1",
                            }
                        ),
                        encoding="utf-8",
                    )
                    (audit / "waveform_conformance.json").write_text(
                        json.dumps({"status": "pass"}), encoding="utf-8"
                    )
                    (audit / "naming.json").write_text(
                        json.dumps(
                            {
                                "status": "pass",
                                "dataset_name": "CISR24",
                                "checks": {
                                    "root_name_exact": True,
                                    "payload_names_exact": True,
                                    "hdf5_release_names_exact": True,
                                    "manifest_names_exact": True,
                                    "no_banned_names": True,
                                },
                            }
                        ),
                        encoding="utf-8",
                    )
                    completed = subprocess.run(
                        [sys.executable, str(gate), "--release_root", str(root)],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(completed.returncode, expected_code)
                    payload = json.loads(completed.stdout)
                    self.assertEqual(
                        payload["checks"]["paper_alignment_passed"],
                        paper_payload is not None
                        and paper_payload["status"] == "pass"
                        and all(
                            paper_payload.get("splits", {})
                            .get(split, {})
                            .get("iq_finite")
                            is True
                            for split in ("train", "val", "test")
                        ),
                    )
                    self.assertEqual(
                        payload["checks"]["effective_snr_grid_passed"],
                        snr_payload is not None and snr_payload["status"] == "pass",
                    )

    def test_empty_release_fails_validator_without_crashing(self):
        validator = DATASET_ROOT / "tools" / "validate_dataset_release.py"
        manifest_header = "sample-id,class-name,snr-db,class-id,seed,h5-index\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "manifests").mkdir()
            (root / "hdf5").mkdir()
            for split in ("train", "val", "test"):
                (root / "manifests" / f"cisr24_{split}_manifest.csv").write_text(
                    manifest_header, encoding="utf-8"
                )
                with h5py.File(
                    root / "hdf5" / f"cisr24_{split}.h5", "w"
                ) as handle:
                    handle.create_dataset("iq", shape=(0, 2, 1024), dtype="float32")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(validator),
                    "--release_root",
                    str(root),
                    "--classes_csv",
                    str(DATASET_ROOT / "classes.csv"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stdout)
            self.assertFalse(all(payload["checks"].values()))


if __name__ == "__main__":
    unittest.main()
