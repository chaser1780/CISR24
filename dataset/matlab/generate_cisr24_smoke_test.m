function cfg = generate_cisr24_smoke_test()
%GENERATE_CISR24_SMOKE_TEST Generate one clean sample per class at 0 dB.

cfg = cisr24_default_config();
cfg.smoke_test = true;
cfg.verbose = true;
cfg = generate_cisr24_dataset(cfg);
end
