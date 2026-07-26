function cfg = generate_cisr24_matrix_smoke_test()
%GENERATE_CISR24_MATRIX_SMOKE_TEST Cover every split, class, and SNR extreme.

cfg = cisr24_default_config();
cfg.output_root = fullfile(cfg.dataset_root, 'matrix_smoke_v1');
cfg.manifest_root = fullfile(cfg.output_root, 'manifests');
cfg.hdf5_root = fullfile(cfg.output_root, 'hdf5');
cfg.audit_root = fullfile(cfg.output_root, 'audit');
cfg.release_name = 'CISR24';
cfg.counts_per_snr = struct('train', 1, 'val', 1, 'test', 1);
cfg.force_overwrite = true;
cfg.verbose = true;
cfg = generate_cisr24_dataset(cfg);
end
