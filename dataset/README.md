# CISR24

CISR24 is the controlled complex-baseband benchmark introduced in the paper
"DDTFNet: A Dual-Domain I/Q-STFT Token-Fusion Transformer for Unified ISAC
Waveform Recognition." It defines one closed-set task over 24 waveform classes:
10 communication, 6 sensing, and 8 integrated sensing and communication (ISAC)
classes.

## Paper protocol

| Property | Setting |
| --- | --- |
| Sampling rate | 10 MHz |
| Record | 1024 complex samples (102.4 us) |
| Storage | two-channel float32 I/Q in HDF5 |
| SNR | -20 dB to 20 dB, step 2 dB (21 levels) |
| Channel | clean AWGN |
| SNR reference | active-burst average power |
| Train | 1000 samples/class/SNR; 504,000 total |
| Validation | 200 samples/class/SNR; 100,800 total |
| Test | 200 samples/class/SNR; 100,800 total |
| Total | 705,600 samples |

The full release is available from the
[CISR24 Hugging Face dataset](https://huggingface.co/datasets/okra123/CISR24).
The authoritative label order is [classes.csv](classes.csv). The complete
waveform definitions are in [docs/DATASET_SPEC.md](docs/DATASET_SPEC.md).
The exact loop/seed pseudocode is in
[docs/GENERATION_ALGORITHM.md](docs/GENERATION_ALGORITHM.md), and public artifact
availability is defined by [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

## Release status

The regenerated CISR24 payload passes the complete technical release gate:

- all 24 classes and seven waveform families follow Tables II and III;
- all 705,600 records have balanced class/SNR cells and collision-free seeds;
- train, validation, and test samples and seeds are mutually disjoint;
- every manifest row matches its HDF5 row and all I/Q values are finite;
- all 1,512 class/SNR/split SNR cells pass the declared tolerances;
- waveform-conformance and low-dimensional shortcut audits pass.

Machine-readable results are distributed with the data under `audit/`. See
[docs/PAPER_ALIGNMENT.md](docs/PAPER_ALIGNMENT.md) for the per-class evidence.

## Generate CISR24

Required MATLAB products:

- MATLAB R2025a or a compatible release;
- Communications Toolbox;
- Phased Array System Toolbox.

Smoke test:

```matlab
addpath('dataset/matlab');
generate_cisr24_smoke_test();
```

Full generation is intentionally explicit because it replaces the complete
705,600-record payload:

```matlab
addpath('dataset/matlab');
cfg = cisr24_default_config();
cfg.force_overwrite = false;
generate_cisr24_dataset(cfg);
```

Set `CISR24_OUTPUT_ROOT` to the desired data volume before generation. If it is
unset, the generator writes to `dataset/releases/CISR24`.
Public files use `cisr24_{train,val,test}.h5` and matching manifests.

## Validate

```bash
python3 dataset/tools/audit_paper_alignment.py \
  --release-root "$CISR24_OUTPUT_ROOT" \
  --full-iq-scan \
  --output-json "$CISR24_OUTPUT_ROOT/audit/paper_alignment.json"
```

Do not publish unless the command exits successfully with all release-blocking
checks true, including unique seeds within every split.

## Publication layout

GitHub should contain documentation, taxonomy, generation and validation code,
a loader, checksums, citation metadata, and a tiny example only. The full HDF5
payload is about 5.6 GiB and the training HDF5 file exceeds GitHub's practical
single-file limits. The full data is hosted on
[Hugging Face](https://huggingface.co/datasets/okra123/CISR24). See
[docs/PUBLIC_RELEASE.md](docs/PUBLIC_RELEASE.md). Quantitative shortcut evidence
follows [docs/SHORTCUT_AUDIT.md](docs/SHORTCUT_AUDIT.md).

Dataset artifacts are licensed under CC BY 4.0 and source code is licensed
under Apache License 2.0. CISR24 is authored by QI Maoqian. The version DOI will
be added after the final Hugging Face revision is frozen.
