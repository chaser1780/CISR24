# Changelog

## 2026-07-28 metadata correction

- align the accompanying paper title and model name with the final manuscript:
  `CDTFNet: A Cross-Domain Token-Fusion Transformer for Waveform-Level
  Electromagnetic Awareness in Low-Altitude Intelligent Networks`;
- record that this correction changes documentation only.

No HDF5 payload, manifest, class definition, generator, audit result, license,
or release version changed. DOI 10.57967/hf/9724 and GitHub tag `v1.1.1`
remain immutable release snapshots; the mutable repository HEAD contains this
metadata correction.

## 1.1.1

- adopt the paper dataset name `CISR24` across public generation and storage;
- use the seven waveform-family groups defined by Table II;
- use canonical HDF5 names `/class-id`, `/snr-db`, and `/sample-index`;
- use collision-free per-record seed allocation;
- constrain Barker and Costas records to the paper's active-length set;
- realize the paper's 0.625 MHz CPFSK spacing with h=0.5 and sps=8;
- use centered alias-free OFDM-LFM chirp bases and independent data per symbol;
- add a full paper-alignment audit, loader, data card, schema, and release guide;
- add a 1,512-cell effective-SNR audit and enforce paper/SNR/full-IQ results in
  the release gate.

The full 705,600-record payload was generated and passed the complete release
gate. The version remains metadata and is not part of the dataset name.
