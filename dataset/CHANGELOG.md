# Changelog

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
