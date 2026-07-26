# CISR24 Dataset Specification

## 1. Scope

`CISR24` is a native 24-class complex-baseband IQ benchmark for
unified recognition of:

- communication waveforms
- radar sensing waveforms
- ISAC waveforms

The public release ID is `CISR24`. It is not a filtered view
of a larger label space. All manifests, HDF5 files, class IDs, and label names
are generated directly in the 24-class label space defined by the paper.

## 2. Final Taxonomy

### 2.1 Communication classes: 10

- `BPSK`
- `QPSK`
- `8PSK`
- `16QAM`
- `4FSK`
- `8FSK`
- `GMSK`
- `OFDM-BPSK`
- `OFDM-QPSK`
- `OFDM-16QAM`

### 2.2 Radar sensing classes: 6

- `Rect`
- `Barker`
- `LFM`
- `Costas`
- `Frank`
- `P4`

### 2.3 ISAC classes: 8

- `LFM-BPSK`
- `LFM-QPSK`
- `LFM-8PSK`
- `LFM-MSK`
- `LFM-GMSK`
- `OFDM-LFM-BPSK`
- `OFDM-LFM-QPSK`
- `OFDM-LFM-16QAM`

## 3. Global Record Definition

- sampling rate: `fs = 10 MHz`
- record length: `L = 1024`
- record duration: `102.4 us`
- representation: complex baseband IQ
- numeric type: `float32`

## 4. Clean Release Rules

These rules apply to every class.

### 4.1 Baseband only

All classes are generated and stored in complex baseband.

- no class-specific fixed carriers
- no superclass-specific center-frequency assignments

### 4.2 Power normalization and SNR definition

For every example:

1. generate the active waveform burst
2. apply random initial phase
3. normalize the active burst to unit average power
4. embed the burst into the `1024`-sample record with random start offset
5. add complex AWGN using the active-burst power as the SNR reference

The release audit verifies this convention independently from the nominal SNR
labels. It gates every class/SNR cell using the inactive interval's pure-noise
power, then pools records at each split/SNR level to check unit-power active
burst normalization with an active-minus-inactive estimate.

Interpretation:

- `snr_db` in the manifest refers to active-burst SNR
- `effective_snr_basis = active_burst`

### 4.3 Clean-version randomization only

Allowed:

- random symbol realization or code realization
- random pulse or burst start offset
- random initial phase
- AWGN at target `snr_db`
- waveform-internal parameter draws from small discrete sets

Not included in this clean release:

- CFO
- IQ imbalance
- multipath fading
- delayed radar echoes
- clipping
- quantization stress

These remain evaluation-time or future robust-variant factors.

## 5. Split Policy

Balanced IID benchmark:

- train: `1000` examples per class per SNR
- val: `200` examples per class per SNR
- test: `200` examples per class per SNR

SNR grid:

- `-20, -18, ..., 20 dB`
- total SNR levels: `21`

Independent generation:

- train/val/test are generated independently
- different splits use different seeds
- no split is obtained by slicing the same mother waveform bank

## 6. Activity-Length Control

To reduce activity-length leakage, the rebuild intentionally increases overlap
between waveform families.

### 6.1 Support policy

- communication single-carrier bursts use active support from
  `{576, 640, 704, 768, 832}`
- radar pulse-like classes also concentrate in the same broad support range
- OFDM uses native packet lengths from `2` or `3` OFDM symbols
- OFDM-LFM shares the same native packet lengths, avoids standalone preamble concatenation, and uses a hybrid partial chirp-subcarrier design on data carriers

### 6.2 Release criterion

The release must be accompanied by a shortcut audit. At minimum:

- `active_len`
- `bw95`
- spectral centroid
- spectral spread
- crest factor
- envelope sparsity
- peak count in the periodogram

## 7. Waveform-Specific Design

## 7.1 Communication: single-carrier classes

Applies to:

- `BPSK`
- `QPSK`
- `8PSK`
- `16QAM`
- `4FSK`
- `8FSK`
- `GMSK`

### Linear modulations

Applies to:

- `BPSK`
- `QPSK`
- `8PSK`
- `16QAM`

Rules:

- `sps = 4` and `Rs = 2.5 Msps`
- Gray mapping
- root-raised-cosine pulse shaping
- `beta in {0.25, 0.35}`
- span `= 8` symbols
- `16QAM` uses unit-average-power normalization before pulse shaping

### 4FSK / 8FSK

Implementation:

- canonical CPFSK construction with continuous phase
- `sps = 8` and `Rs = 1.25 Msps`
- modulation index `h = 0.5`
- adjacent tone spacing `Δf = h * Rs = 0.625 MHz`
- tone spacing is stored in metadata as `cpfsk_tone_spacing_hz`

### GMSK

Rules:

- `BT = 0.3`
- `sps = 4`
- `Rs = 2.5 Msps`

## 7.2 Communication: OFDM classes

Applies to:

- `OFDM-BPSK`
- `OFDM-QPSK`
- `OFDM-16QAM`

Default numerology:

- `N_fft = 256`
- `N_cp = 32`
- `N_active in {96, 128}`
- OFDM symbols per packet `M in {2, 3}`

Subcarrier layout:

- occupied subcarriers are symmetric around DC
- DC is always null
- `4` fixed pilot tones are inserted within the occupied subcarriers
- the remaining occupied subcarriers carry BPSK / QPSK / 16QAM data symbols

Time-domain lengths:

- `2` symbols -> `576`
- `3` symbols -> `864`

## 7.3 Radar sensing classes

All radar examples are treated as single-pulse intrapulse snapshots.

### Rect

- active support drawn from `{576, 640, 704, 768, 832}`

### Barker

- `Lb in {7, 11, 13}`
- chip counts and chip durations are chosen to overlap the support range of the
  other radar classes

### LFM

- chirp bandwidth `B in {2, 3, 4} MHz`
- chirp direction random in `{up, down}`
- active support drawn from `{576, 640, 704, 768, 832}`

### Costas

- `Nc in {7, 11, 13}`
- frequency step `Df in {0.25, 0.5} MHz`
- one valid Costas base permutation per length, plus symmetry-derived variants
- chosen permutation ID is written as `costas_perm_id`

### Frank

- order `M = 4`
- `16` phase chips
- chip samples in `{36, 40, 44, 48, 52}`

### P4

- code length `N in {16, 32}`
- chip samples chosen so total support stays close to the shared radar support
  range

## 7.4 ISAC classes

ISAC examples are defined as short packet-level or burst-level snapshots.

### LFM-single-carrier ISAC

Applies to:

- `LFM-BPSK`
- `LFM-QPSK`
- `LFM-8PSK`

Construction:

- generate a centered baseband LFM chirp over the target support
- apply symbol-wise PSK phase coding on top of the chirp
- chirp bandwidth `B in {2, 3, 4} MHz`
- chirp direction random
- this family is retained as a sensing-centric chirp-carried communication variant

Signal model:

- `x(t) = c_lfm(t) * exp(j*phi_k)`

### LFM-CPM ISAC

Applies to:

- `LFM-MSK`
- `LFM-GMSK`

Construction:

- generate a constant-envelope CPM waveform (`MSK` or `GMSK`)
- multiply it by a baseband LFM chirp over the same support
- chirp bandwidth `B in {2, 3, 4} MHz`
- chirp direction random

Signal model:

- `x(t) = s_cpm(t) * c_lfm(t)`

### OFDM-LFM ISAC

Applies to:

- `OFDM-LFM-BPSK`
- `OFDM-LFM-QPSK`
- `OFDM-LFM-16QAM`

Construction:

- use the same OFDM packet structure as the communication OFDM classes
- retain the same OFDM numerology and pilot layout as the communication OFDM classes
- keep the same OFDM active-bin layout as the communication OFDM classes
- retain regular OFDM pilots on all pilot bins
- select a comb-interleaved subset of data carriers as chirp-enhanced carriers
- synthesize the final time-domain symbol as a hybrid mixture of regular OFDM and chirp-shaped basis functions on that data-carrier subset
- keep inactive bins and DC null consistent with the communication OFDM classes
- retain `chirp_bw_hz` and `chirp_dir` in metadata
- no fixed chirp preamble is used

## 8. Release Storage

Full release root:

- `$CISR24_OUTPUT_ROOT` (or `dataset/releases/CISR24`)

Files:

- `hdf5/cisr24_train.h5`
- `hdf5/cisr24_val.h5`
- `hdf5/cisr24_test.h5`
- `manifests/cisr24_train_manifest.csv`
- `manifests/cisr24_val_manifest.csv`
- `manifests/cisr24_test_manifest.csv`
- `label_names.txt`
- `classes.csv`

## 9. Manifest Schema

Core fields:

- `sample-id`
- `split`
- `h5-rel-path`
- `h5-dataset`
- `h5-index`
- `class-id`
- `super-class`
- `class-name`
- `waveform-family`
- `snr-db`
- `fs-hz`
- `n-samples`
- `seed`
- `active-len`
- `start-offset`
- `channel-profile`
- `release-name`
- `iid-or-ood`

Waveform-parameter fields:

- `symbol-rate-hz`
- `sps`
- `nfft`
- `cp-len`
- `n-active`
- `chirp-bw-hz`
- `chirp-dir`
- `pulse-width-us`
- `barker-len`
- `costas-len`
- `frank-order`
- `p4-len`
- `rrc-beta`
- `ofdm-num-symbols`
- `costas-df-hz`
- `costas-perm-id`
- `chip-samples`
- `gmsk-bt`
- `cpfsk-modulation-index`
- `cpfsk-tone-spacing-hz`
- `effective-snr-basis`

## 10. Validation and Audit

Bundled tooling in `tools/` is expected to check:

- split sizes
- class balance
- per-class/per-SNR balance
- HDF5 index consistency
- split seed disjointness
- seed uniqueness within each split
- effective SNR consistency
- shortcut-feature baselines

## 11. Paper Framing

Recommended wording:

- `24-class unified waveform recognition across communication, radar sensing, and ISAC signals`
- `clean synthetic complex-baseband benchmark`

Avoid:

- `real-world dataset`
- `fully realistic RF capture benchmark`
- `complete ISAC channel benchmark`
