# CISR24 storage schema

## HDF5

Each split file contains:

| Dataset | Dtype | Shape | Meaning |
| --- | --- | --- | --- |
| `/iq` | float32 | `[N, 2, 1024]` | I and Q channels |
| `/class-id` | uint16 | `[1, N]` | IDs 0 through 23 |
| `/snr-db` | float32 | `[1, N]` | SNR in dB |
| `/sample-index` | uint32 | `[1, N]` | global 1-based sample index |

Root attributes include `release_name`, `split`, `fs_hz`, `record_len`,
`total_count`, and `effective_snr_basis`. The public loader also recognizes the
legacy underscore aliases for provenance files, but canonical releases use the
hyphenated names above to match the paper.

No normalization, random crop, or test-time augmentation is applied when
reading the fixed 1024-sample records.

## Manifest

Each manifest row maps one HDF5 row to its taxonomy, generation condition, and
waveform parameters. Canonical field names use lowercase kebab case, including:

```text
sample-id, split, h5-rel-path, h5-dataset, h5-index,
class-id, super-class, class-name, waveform-family,
snr-db, fs-hz, n-samples, seed, active-len, start-offset,
channel-profile, release-name, iid-or-ood, effective-snr-basis
```

Waveform-specific fields include `symbol-rate-hz`, `sps`, `nfft`, `cp-len`,
`n-active`, `chirp-bw-hz`, `chirp-dir`, `pulse-width-us`, `barker-len`,
`costas-len`, `frank-order`, `p4-len`, `rrc-beta`, `ofdm-num-symbols`,
`costas-df-hz`, `costas-perm-id`, `chip-samples`, `gmsk-bt`,
`cpfsk-modulation-index`, and `cpfsk-tone-spacing-hz`. Barker and Costas may distribute a target active length
across chips by one-sample differences; for those classes, `chip-samples` is
`NaN` and `chip-samples-min`/`chip-samples-max` record the actual bounds.
Non-applicable values are encoded as `NaN`.
