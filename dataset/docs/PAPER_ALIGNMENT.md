# CISR24 paper-alignment audit

Source of truth: `main.pdf`, Tables II and III. The paper was read as an input
specification and was not modified. This document describes CISR24.

## Global result

The canonical release passes every technical paper-alignment and release-gate
check. The machine-readable results are:

- `../audit/paper_alignment.json`: all 24 classes pass with no blockers or
  warnings;
- `../audit/validate_release.json`: exact split sizes, class/SNR balance,
  HDF5 coverage, and unique, disjoint sample IDs and seeds;
- `../audit/waveform_conformance.json`: fixed waveform parameters and MATLAB
  waveform measurements match the paper;
- `../audit/effective_snr_grid.json`: all 1,512 class/SNR/split cells pass;
- `../audit/shortcut_audit_train.json`: the declared low-dimensional shortcut
  protocol is complete;
- `../audit/release_gate.json`: every technical gate is true.

The release contains 504,000 training, 100,800 validation, and 100,800 test
records. Each HDF5 file has shape `[N, 2, 1024]` and float32 I/Q values. All
manifest rows match HDF5 metadata, every I/Q value is finite, and no sample ID
or seed crosses split boundaries.

## Per-class result

`PASS` means the generated construction and observable parameter domains match
Table II. Fixed global parameters are also recorded in
`../audit/release_meta.json` and the generation source archive.

| ID | Class | Result | Paper-alignment evidence |
| ---: | --- | --- | --- |
| 0 | BPSK | PASS | `Na`, sps, Rs, RRC beta/span, and Gray mapping |
| 1 | QPSK | PASS | same single-carrier linear-modulation protocol |
| 2 | 8PSK | PASS | same single-carrier linear-modulation protocol |
| 3 | 16QAM | PASS | Gray mapping and unit-average-power QAM |
| 4 | 4FSK | PASS | CPFSK with h=0.5 and measured 0.625 MHz adjacent spacing |
| 5 | 8FSK | PASS | CPFSK with h=0.5 and measured 0.625 MHz adjacent spacing |
| 6 | GMSK | PASS | BT=0.3 and paper-aligned samples per symbol |
| 7 | OFDM-BPSK | PASS | Nfft=256, Ncp=32, active bins, symbols, pilots, and DC |
| 8 | OFDM-QPSK | PASS | same OFDM protocol with QPSK data carriers |
| 9 | OFDM-16QAM | PASS | same OFDM protocol with 16QAM data carriers |
| 10 | Rect | PASS | active lengths equal the five paper values |
| 11 | Barker | PASS | Barker lengths and active lengths match the paper support |
| 12 | LFM | PASS | active lengths, 2/3/4 MHz bandwidth, and chirp direction |
| 13 | Costas | PASS | code lengths, frequency steps, and active lengths |
| 14 | Frank | PASS | order 4 and paper active-length support |
| 15 | P4 | PASS | code lengths 16/32 and paper active-length support |
| 16 | LFM-BPSK | PASS | active lengths, bandwidth, direction, and BPSK coding |
| 17 | LFM-QPSK | PASS | same LFM-PSK protocol with QPSK coding |
| 18 | LFM-8PSK | PASS | same LFM-PSK protocol with 8PSK coding |
| 19 | LFM-MSK | PASS | LFM-carried MSK protocol |
| 20 | LFM-GMSK | PASS | LFM-carried GMSK with BT=0.3 |
| 21 | OFDM-LFM-BPSK | PASS | centered alias-free chirps and independent symbol data |
| 22 | OFDM-LFM-QPSK | PASS | centered alias-free chirps and independent symbol data |
| 23 | OFDM-LFM-16QAM | PASS | centered alias-free chirps and independent symbol data |
