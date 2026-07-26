"""Minimal NumPy/HDF5 loader for CISR24."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import h5py
import numpy as np


SPLITS = ("train", "val", "test")


def resolve_dataset_root(root: str | Path | None = None) -> Path:
    value = root if root is not None else os.environ.get("CISR24_DATASET_ROOT")
    if value is None:
        raise ValueError("pass root or set CISR24_DATASET_ROOT")
    return Path(value).expanduser().resolve()


def resolve_h5_path(root: Path, split: str) -> Path:
    canonical = root / "hdf5" / f"cisr24_{split}.h5"
    if canonical.exists():
        return canonical
    raise FileNotFoundError(f"no HDF5 file found for split={split} under {root}")


def h5_key(handle: h5py.File, canonical: str) -> str:
    if canonical in handle:
        return canonical
    legacy = canonical.replace("-", "_")
    if legacy in handle:
        return legacy
    raise KeyError(f"missing /{canonical}")


def h5_scalar(dataset: h5py.Dataset, index: int) -> int | float:
    if dataset.ndim == 2 and dataset.shape[0] == 1:
        return dataset[0, index].item()
    return dataset[index].item()


class CISR24Split:
    """Random-access view of one fixed CISR24 split, without normalization."""

    def __init__(self, root: str | Path | None, split: str) -> None:
        if split not in SPLITS:
            raise ValueError(f"split must be one of {SPLITS}")
        self.root = resolve_dataset_root(root)
        self.split = split
        self.path = resolve_h5_path(self.root, split)
        self._handle: h5py.File | None = None
        with h5py.File(self.path, "r") as handle:
            self._length = int(handle[h5_key(handle, "iq")].shape[0])

    def __len__(self) -> int:
        return self._length

    def _open(self) -> h5py.File:
        if self._handle is None:
            self._handle = h5py.File(self.path, "r")
        return self._handle

    def __getitem__(self, index: int) -> dict[str, np.ndarray | int | float]:
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError(index)
        handle = self._open()
        iq = np.asarray(handle[h5_key(handle, "iq")][index], dtype=np.float32)
        if iq.shape != (2, 1024):
            raise ValueError(f"unexpected I/Q shape at row {index}: {iq.shape}")
        return {
            "iq": iq,
            "class_id": int(h5_scalar(handle[h5_key(handle, "class-id")], index)),
            "snr_db": float(h5_scalar(handle[h5_key(handle, "snr-db")], index)),
            "sample_index": int(h5_scalar(handle[h5_key(handle, "sample-index")], index)),
        }

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "CISR24Split":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect one CISR24 sample")
    parser.add_argument("root", type=Path)
    parser.add_argument("--split", choices=SPLITS, default="test")
    parser.add_argument("--index", type=int, default=0)
    args = parser.parse_args()
    with CISR24Split(args.root, args.split) as dataset:
        sample = dataset[args.index]
        print(
            f"rows={len(dataset)} iq_shape={sample['iq'].shape} "
            f"class_id={sample['class_id']} snr_db={sample['snr_db']} "
            f"sample_index={sample['sample_index']}"
        )


if __name__ == "__main__":
    main()
