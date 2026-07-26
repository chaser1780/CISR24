# CISR24 shortcut audit protocol

The shortcut audit is a risk disclosure, not proof that no shortcut exists. It
reports non-trivial low-dimensional predictability even when it remains
insufficient for the full 24-class task.

## Fixed protocol

- deterministic audit seed `20260722`;
- train-to-test evaluation with no test-time tuning;
- 100 records per class/SNR from train and test;
- 50,400 train and 50,400 test records over all 21 SNR levels;
- hash-ranked sampling, never the first manifest rows;
- class and superclass accuracy, balanced accuracy, and macro-F1;
- aggregate and per-SNR metrics;
- nearest centroid, multinomial logistic regression, and shallow random forest;
- normalized mutual information with 200 label permutations.

## Feature views

`record-only` uses only the complete 1024-sample I/Q record. Manifest fields are
used for labels and grouping, never as classifier inputs.

`metadata-assisted` uses true active support and `active-len`. It is explicitly
reported as a privileged-information upper bound, not a realistic model input.
Separate metadata-only lookups report `active-len` and
`[start-offset, active-len]` leakage across train and test.

## Published artifacts

The release contains compressed per-sample features, exact train/test caches,
model metrics, per-SNR metrics, confusion matrices, mutual information,
class/superclass distribution summaries, and PNG/PDF figures under
`audit/shortcut/`. Chance baselines are 1/24 for fine classes and 1/3 for
balanced superclass accuracy; raw superclass majority accuracy is 10/24.

High observable-feature accuracy is disclosed rather than hidden because
bandwidth, envelope, and spectral peaks are genuine waveform properties. The
predeclared active-support thresholds remain quality-control gates; other
shortcut metrics are reported as risk evidence and must not be summarized only
as "insufficient to solve."
