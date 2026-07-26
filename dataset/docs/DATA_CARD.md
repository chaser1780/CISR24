# CISR24 Data Card

## Summary

CISR24 is a synthetic complex-baseband IQ benchmark for unified recognition of
24 communication, sensing, and ISAC waveforms. It is intended to accompany the
DDTFNet paper and uses one shared label space across all three superclasses.

## Composition

- 10 communication classes;
- 6 intra-pulse sensing classes;
- 8 ISAC classes;
- 705,600 total examples in a balanced train/validation/test protocol;
- 1024 complex samples per record at 10 MHz;
- 21 SNR levels from -20 dB to 20 dB in 2 dB steps;
- clean AWGN with active-burst SNR calibration;
- float32 two-channel I/Q stored in HDF5.

See `classes.csv` for IDs and `DATASET_SPEC.md` for exact waveform parameters.

## Intended use

- closed-set waveform recognition across communication, sensing, and ISAC;
- SNR-wise model comparison under the paper's fixed split protocol;
- representation, fusion, and robustness studies that clearly distinguish the
  clean release from evaluation-time perturbations.

## Out-of-scope use

- claims about measured over-the-air performance;
- operational spectrum enforcement or safety-critical decisions;
- treating evaluation-time CFO/fading as part of the clean training payload;
- altering labels, split membership, or SNR calibration while reporting direct
  comparison with the paper.

## Limitations

- The benchmark is simulated and excludes hardware effects, multipath, clutter,
  delayed radar echoes, clipping, and quantization from the clean release.
- Low-dimensional shortcut audits reduce but cannot eliminate all shortcut risk.
- The regenerated CISR24 payload passed full IQ, manifest/HDF5,
  waveform-conformance, 1,512-cell effective-SNR, and shortcut
  audits. These checks establish conformance to the declared synthetic protocol;
  they do not establish over-the-air validity.

## Provenance

The release records its exact generator commit, MATLAB/toolbox versions,
configuration, paper hash, source archive, checksums, and validation output in
`audit/release_meta.json`, `files.csv`, `SHA256SUMS`, and `provenance/`.

## License and citation

CISR24 is authored by QI Maoqian. Dataset artifacts are licensed under CC BY
4.0 and source code is licensed under Apache License 2.0. Source code is hosted
at <https://github.com/chaser1780/CISR24>, and the full release is hosted at
<https://huggingface.co/datasets/okra123/CISR24>. The registered dataset version
is [DOI 10.57967/hf/9724](https://doi.org/10.57967/hf/9724).
