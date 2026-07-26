# CISR24 generation algorithm

The MATLAB implementation in `matlab/generate_cisr24_dataset.m` is the
executable source of truth. This pseudocode documents its release contract.

```text
for split_id, split in [train, val, test]:
  for class_id, waveform specification in classes.csv order:
    for snr_id, snr_db in [-20, -18, ..., 20]:
      for local_sample_id in [1, ..., count(split)]:
        seed = 20260410
             + 30000000 * split_id
             +  1000000 * class_id
             +    10000 * snr_id
             + local_sample_id
        rng(seed, "twister")

        parameters = draw only from the paper's class-specific sets
        burst = generate_complex_baseband_waveform(class_id, parameters)
        burst = burst * exp(j * uniform(0, 2*pi))
        burst = burst / sqrt(mean(abs(burst)^2))

        start = uniform_integer(0, 1024 - len(burst))
        record = complex_zeros(1024)
        record[start : start + len(burst)] = burst

        noise_power = 10^(-snr_db / 10)
        noise = sqrt(noise_power / 2) * (randn(1024) + j*randn(1024))
        record = record + noise

        append float32 [I, Q] to /iq
        append class_id, snr_db, and global sample index to HDF5
        append seed, support, taxonomy, and waveform parameters to manifest
```

`split_id`, `class_id`, and `snr_id` are zero based in the formula. The local
sample ID is one based. The resulting 705,600 seeds are unique and remain below
the `uint32` limit.

## Physical conformance rules

- Linear PSK/QAM uses RRC shaping with `sps=4`, `Rs=2.5 Msps`, span 8, and
  beta in `{0.25, 0.35}`.
- 4FSK/8FSK uses CPFSK `h=0.5`, `sps=8`, and `Rs=1.25 Msps`, giving actual
  adjacent tone spacing `0.625 MHz`.
- GMSK and LFM-GMSK use `BT=0.3`, pulse length 4, and `sps=4`.
- OFDM-LFM chirp-enhanced carriers use a centered time coordinate and symmetric
  sweep around each subcarrier. Generation aborts if instantaneous frequency
  reaches Nyquist.
- Barker and Costas distribute the selected paper active length across chips by
  at most one sample and record the actual minimum/maximum chip width.

## Completion semantics

Generation starts with `generation_status=in_progress`. A successful generator
sets it to `complete` and records exactly 705,600 samples. External packaging
keeps `.INCOMPLETE` until validation, full-grid SNR checks, shortcut audit,
paper alignment, loader tests, checksums, and the release gate all pass.
