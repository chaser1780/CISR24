#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MATLAB_CODE="addpath('${SCRIPT_DIR}/matlab'); run_cisr24_full();"
RELEASE_ROOT="${CISR24_OUTPUT_ROOT:-${SCRIPT_DIR}/releases/CISR24}"
TOOLS_ROOT="${SCRIPT_DIR}/tools"
SOURCE_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
PAPER_PDF="${CISR24_PAPER_PDF:?set CISR24_PAPER_PDF to the authoritative main.pdf}"
SOURCE_ARCHIVE="${RELEASE_ROOT}/provenance/CISR24-source.tar.gz"

export CISR24_OUTPUT_ROOT="${RELEASE_ROOT}"
matlab -batch "$MATLAB_CODE"

mkdir -p "${RELEASE_ROOT}/audit"

matlab -batch "addpath('${SCRIPT_DIR}/matlab'); verify_cisr24_waveform_conformance('${RELEASE_ROOT}/audit/waveform_conformance.json');"

python3 "${TOOLS_ROOT}/finalize_release_metadata.py" \
  --release-root "${RELEASE_ROOT}" \
  --source-root "${SOURCE_ROOT}" \
  --source-archive "${SOURCE_ARCHIVE}" \
  --paper-pdf "${PAPER_PDF}"

python3 "${TOOLS_ROOT}/validate_dataset_release.py" \
  --release_root "${RELEASE_ROOT}" \
  --classes_csv "${RELEASE_ROOT}/classes.csv" \
  --output_json "${RELEASE_ROOT}/audit/validate_release.json"

python3 "${TOOLS_ROOT}/check_effective_snr_grid.py" \
  --release-root "${RELEASE_ROOT}" \
  --per-cell 200 \
  --output-json "${RELEASE_ROOT}/audit/effective_snr_grid.json"

python3 "${TOOLS_ROOT}/audit_shortcuts.py" \
  --release_root "${RELEASE_ROOT}" \
  --classes_csv "${RELEASE_ROOT}/classes.csv" \
  --train_split train \
  --test_split test \
  --per_cell 100 \
  --output_json "${RELEASE_ROOT}/audit/shortcut_audit_train.json"

python3 "${TOOLS_ROOT}/audit_paper_alignment.py" \
  --release-root "${RELEASE_ROOT}" \
  --full-iq-scan \
  --redact-root \
  --output-json "${RELEASE_ROOT}/audit/paper_alignment.json"

python3 "${TOOLS_ROOT}/audit_naming.py" \
  --release-root "${RELEASE_ROOT}" \
  --output-json "${RELEASE_ROOT}/audit/naming.json"

python3 "${TOOLS_ROOT}/release_gate.py" \
  --release_root "${RELEASE_ROOT}" \
  --output_json "${RELEASE_ROOT}/audit/release_gate.json"

python3 "${TOOLS_ROOT}/make_release_index.py" "${RELEASE_ROOT}"
