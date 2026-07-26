#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
BUILD_ROOT="${CISR24_BUILD_ROOT:?set CISR24_BUILD_ROOT to a new build directory}"
PAPER_PDF="${CISR24_PAPER_PDF:?set CISR24_PAPER_PDF to the authoritative main.pdf}"
RELEASE_NAME="CISR24"
STAGING_ROOT="${BUILD_ROOT}/staging/${RELEASE_NAME}"
FINAL_ROOT="${BUILD_ROOT}/final/${RELEASE_NAME}"
LOG_ROOT="${BUILD_ROOT}/logs"

if [[ -n "$(git -C "${SOURCE_ROOT}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "Source repository must be clean." >&2
  exit 1
fi
if [[ -e "${STAGING_ROOT}" || -e "${FINAL_ROOT}" ]]; then
  echo "Staging and final release paths must not already exist." >&2
  exit 1
fi

mkdir -p "${STAGING_ROOT}/provenance" "${LOG_ROOT}"
touch "${STAGING_ROOT}/.INCOMPLETE"
git -C "${SOURCE_ROOT}" archive \
  --format=tar.gz \
  --prefix=CISR24-source/ \
  --output="${STAGING_ROOT}/provenance/CISR24-source.tar.gz" \
  HEAD

export CISR24_OUTPUT_ROOT="${STAGING_ROOT}"
export CISR24_PAPER_PDF="${PAPER_PDF}"
bash "${SCRIPT_DIR}/run_cisr24_full.sh" 2>&1 | tee "${LOG_ROOT}/build.log"

cp "${SCRIPT_DIR}/README.md" "${STAGING_ROOT}/README.md"
cp "${SCRIPT_DIR}/CHANGELOG.md" "${STAGING_ROOT}/CHANGELOG.md"
cp -a "${SCRIPT_DIR}/docs" "${STAGING_ROOT}/docs"
mkdir -p "${STAGING_ROOT}/loaders"
cp "${SCRIPT_DIR}/loaders/cisr24.py" "${STAGING_ROOT}/loaders/cisr24.py"

for manifest in "${STAGING_ROOT}"/manifests/*.csv; do
  gzip -9 -c "${manifest}" > "${manifest}.gz"
done

if [[ -f "${SCRIPT_DIR}/LICENSE-CODE" && -f "${SCRIPT_DIR}/LICENSE-DATA" && -f "${SCRIPT_DIR}/CITATION.cff" ]]; then
  cp "${SCRIPT_DIR}/LICENSE-CODE" "${STAGING_ROOT}/LICENSE-CODE"
  cp "${SCRIPT_DIR}/LICENSE-DATA" "${STAGING_ROOT}/LICENSE-DATA"
  cp "${SCRIPT_DIR}/CITATION.cff" "${STAGING_ROOT}/CITATION.cff"
else
  echo "LICENSE-CODE, LICENSE-DATA, and CITATION.cff are required." >&2
  exit 1
fi

cp "${LOG_ROOT}/build.log" "${STAGING_ROOT}/provenance/build.log"
rm "${STAGING_ROOT}/.INCOMPLETE"
touch "${STAGING_ROOT}/SUCCESS"
python3 "${SCRIPT_DIR}/tools/audit_naming.py" \
  --release-root "${STAGING_ROOT}" \
  --output-json "${STAGING_ROOT}/audit/naming.json"
python3 "${SCRIPT_DIR}/tools/release_gate.py" \
  --release_root "${STAGING_ROOT}" \
  --output_json "${STAGING_ROOT}/audit/release_gate.json"
python3 "${SCRIPT_DIR}/tools/make_release_index.py" "${STAGING_ROOT}"
(
  cd "${STAGING_ROOT}"
  sha256sum -c SHA256SUMS
)

mkdir -p "$(dirname "${FINAL_ROOT}")"
mv "${STAGING_ROOT}" "${FINAL_ROOT}"
echo "Final release candidate: ${FINAL_ROOT}"
