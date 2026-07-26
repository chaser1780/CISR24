# CISR24 reproducibility and availability

The public release is complete only when every row below has a versioned public
location. A mutable branch URL is not a substitute for a release tag or DOI.

| Artifact | Canonical release content | Public location |
| --- | --- | --- |
| HDF5 payload | `hdf5/cisr24_{train,val,test}.h5` | [DOI 10.57967/hf/9724](https://doi.org/10.57967/hf/9724) |
| Manifests and seeds | `manifests/cisr24_*_manifest.csv[.gz]` | same data DOI |
| Generator source | `provenance/CISR24-source.tar.gz` | [GitHub v1.1.1](https://github.com/chaser1780/CISR24/releases/tag/v1.1.1) and data DOI |
| Taxonomy and schema | `classes.csv`, `docs/SCHEMA.md` | GitHub tag and data revision |
| Release configuration | `audit/release_meta.json` | same dataset revision |
| Validation reports | `audit/*.json` | same dataset revision |
| Shortcut evidence | `audit/shortcut/` | same dataset revision |
| Integrity index | `files.csv`, `SHA256SUMS` | same dataset revision |
| Code license | `LICENSE-CODE` | GitHub tag and data revision |
| Data license | `LICENSE-DATA` | GitHub tag and data revision |
| Citation | `CITATION.cff` | GitHub tag and [data DOI](https://doi.org/10.57967/hf/9724) |

## Determinism

- RNG: MATLAB `twister`.
- Base seed: `20260410`.
- Every `(split, class, SNR, local sample)` has one unique manifest seed.
- Split membership is generated directly; no parent waveform pool is partitioned.
- The manifest records the exact HDF5 row and waveform parameters for each sample.

The release metadata records the clean source commit, MATLAB and toolbox
versions, exact Python environment, generation timestamps, configuration, and
paper SHA-256. The release gate rejects a missing Git probe, empty commit, dirty
source tree, incomplete generation, missing audit artifact, or checksum failure.

## Reproduction

Run generation only from the committed source snapshot and into a new staging
directory. The build retains an `.INCOMPLETE` marker until all audits pass. See
`GENERATION_ALGORITHM.md` for the exact algorithm and `PUBLIC_RELEASE.md` for the
packaging sequence.
