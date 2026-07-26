#!/usr/bin/env python3
"""Attach verifiable source, paper, and runtime provenance to release metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

import h5py
import matplotlib
import numpy as np
import sklearn


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(source_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--paper-pdf", type=Path, required=True)
    args = parser.parse_args()

    root = args.release_root.expanduser().resolve()
    source = args.source_root.expanduser().resolve()
    source_archive = args.source_archive.expanduser().resolve()
    paper = args.paper_pdf.expanduser().resolve()
    commit = git(source, "rev-parse", "HEAD")
    dirty = git(source, "status", "--porcelain=v1", "--untracked-files=all")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("source Git commit is not a full SHA-1")
    if dirty:
        raise RuntimeError("source Git repository is not clean")
    for path in (source_archive, paper):
        if not path.is_file():
            raise FileNotFoundError(path)

    meta_path = root / "audit" / "release_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("git_commit") != commit:
        raise RuntimeError("generator commit does not match source snapshot commit")
    if meta.get("generation_status") != "complete":
        raise RuntimeError("generation is not complete")
    meta["source_provenance"] = {
        "git_commit": commit,
        "git_clean": True,
        "source_archive": "provenance/CISR24-source.tar.gz",
        "source_archive_sha256": sha256(source_archive),
        "generator_sha256": sha256(source / "dataset" / "matlab" / "generate_cisr24_dataset.m"),
        "config_sha256": sha256(source / "dataset" / "matlab" / "cisr24_default_config.m"),
    }
    meta["paper_provenance"] = {
        "file_name": "main.pdf",
        "sha256": sha256(paper),
        "note": "alignment source only; the paper file is not modified by generation",
    }
    meta["rng"] = {
        "algorithm": "MATLAB twister",
        "base_seed": 20260410,
        "allocation": "split/class/SNR/local-sample collision-free stride formula",
    }
    meta["generator_schema_version"] = "CISR24-generator-2.1"
    meta["python_environment"] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "h5py": h5py.__version__,
        "scikit_learn": sklearn.__version__,
        "matplotlib": matplotlib.__version__,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta["source_provenance"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
