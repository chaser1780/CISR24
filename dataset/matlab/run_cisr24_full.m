function cfg = run_cisr24_full()
%RUN_CISR24_FULL Launch full paper-aligned CISR24 generation.

cfg = cisr24_default_config();
cfg.force_overwrite = true;
cfg.verbose = true;

cfg = generate_cisr24_dataset(cfg);
end
