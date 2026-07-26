# Public release procedure

## Repository versus data host

Use GitHub for source code, documentation, schemas, class mappings, checksums,
small examples, and download instructions. The full dataset is hosted at
<https://huggingface.co/datasets/okra123/CISR24>. The training HDF5 is larger
than 4 GiB and must not be committed to Git or used as a normal GitHub Release
asset.

Recommended public repository contents:

```text
CISR24/
  README.md
  DATA_CARD.md
  LICENSE-CODE
  LICENSE-DATA
  CITATION.cff
  CHANGELOG.md
  classes.csv
  docs/DATASET_SPEC.md
  docs/PAPER_ALIGNMENT.md
  docs/GENERATION_ALGORITHM.md
  docs/REPRODUCIBILITY.md
  docs/SCHEMA.md
  docs/SHORTCUT_AUDIT.md
  matlab/
  loaders/
  smoke_v1/
  tools/
  release/v1.1.1/files.csv
  release/v1.1.1/SHA256SUMS
```

Recommended hosted data contents:

```text
CISR24/
  hdf5/cisr24_train.h5
  hdf5/cisr24_val.h5
  hdf5/cisr24_test.h5
  manifests/cisr24_train_manifest.csv.gz
  manifests/cisr24_val_manifest.csv.gz
  manifests/cisr24_test_manifest.csv.gz
  audit/
  provenance/
  classes.csv
  label_names.txt
  audit/release_meta.json
  files.csv
  SHA256SUMS
```

## Release gate

Do not upload until all of the following are complete:

- generate the full dataset with the canonical CISR24 generator;
- verify 705,600 unique seeds and disjoint split seed sets;
- verify every class and SNR cell count;
- scan all I/Q values for finiteness and exact `[N,2,1024]` float32 schema;
- verify every manifest row against its HDF5 row;
- audit effective SNR across all classes, SNR levels, and splits, with
  per-class noise-power gates and pooled active-power checks;
- run shortcut audits and record thresholds/results;
- generate per-file SHA-256 checksums;
- reproduce the loader quickstart in a clean environment;
- select data/code licenses and confirm citation authors and DOI;
- create a clean Git commit and record it in release metadata.

After the final Hugging Face revision is frozen, generate its DOI and record it
in `CITATION.cff` and the paper's dataset reference. Tag the matching GitHub
source revision and link both records. The attached paper PDF is the source of
truth for this alignment and is not modified by this release workflow. Do not
cite only a mutable branch URL.
