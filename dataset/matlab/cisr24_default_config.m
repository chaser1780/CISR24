function cfg = cisr24_default_config()
%CISR24_DEFAULT_CONFIG Paper-aligned configuration for CISR24 generation.

matlab_root = fileparts(mfilename('fullpath'));
dataset_root = fileparts(matlab_root);

cfg = struct();
cfg.dataset_root = dataset_root;
cfg.output_root = getenv('CISR24_OUTPUT_ROOT');
if isempty(cfg.output_root)
    cfg.output_root = fullfile(dataset_root, 'releases', 'CISR24');
end
cfg.manifest_root = fullfile(cfg.output_root, 'manifests');
cfg.hdf5_root = fullfile(cfg.output_root, 'hdf5');
cfg.audit_root = fullfile(cfg.output_root, 'audit');
cfg.hdf5_basename = 'cisr24';
cfg.manifest_basename = 'cisr24';
cfg.hdf5_chunk_samples = 256;
cfg.release_name = 'CISR24';
cfg.construction_variant = 'hybrid_partial_chirp_subcarrier';
cfg.iid_or_ood = 'iid';
cfg.channel_profile = 'clean_awgn';
cfg.effective_snr_basis = 'active_burst';
cfg.add_awgn = true;

cfg.fs_hz = 10e6;
cfg.record_len = 1024;
cfg.snr_db = -20:2:20;
cfg.base_seed = 20260410;

cfg.counts_per_snr = struct( ...
    'train', 1000, ...
    'val', 200, ...
    'test', 200);

cfg.force_overwrite = false;
cfg.smoke_test = false;
cfg.verbose = true;

cfg.comm_active_lengths = [576, 640, 704, 768, 832];
cfg.radar_active_lengths = [576, 640, 704, 768, 832];

cfg.ofdm_nfft = 256;
cfg.ofdm_cp = 32;
cfg.ofdm_active_choices = [96, 128];
cfg.ofdm_symbol_choices = [2, 3];
cfg.ofdm_lfm_mode = 'hybrid_partial_chirp_subcarrier';
cfg.ofdm_lfm_chirp_layout = 'comb_data_every4';
cfg.ofdm_lfm_chirp_ratio = 0.25;
cfg.ofdm_lfm_mix_alpha = 0.35;
cfg.ofdm_lfm_regular_pilots = true;
cfg.ofdm_lfm_subcarrier_chirp_profile = 'symmetric_linear_slope';
cfg.ofdm_lfm_subcarrier_chirp_strength = 1.0;
cfg.rrc_rolloff_choices = [0.25, 0.35];
cfg.rrc_span_symbols = 8;
cfg.single_carrier_sps = 4;
cfg.gmsk_bt = 0.3;
cfg.gmsk_pulse_length = 4;
cfg.cpfsk_sps = 8;
cfg.cpfsk_modulation_index = 0.5;
cfg.cpfsk_tone_spacing_hz = 0.625e6;

cfg.chirp_bandwidth_choices_hz = [2e6, 3e6, 4e6];
cfg.costas_frequency_step_choices_hz = [0.25e6, 0.5e6];
cfg.ofdm_pilot_count = 4;
cfg.release_gate = struct( ...
    'snr_mean_tol_db', 0.30, ...
    'snr_class_tol_db', 0.50, ...
    'snr_std_tol_db', 0.50, ...
    'snr_active_minus_noise_tol_db', 1.00, ...
    'active_len_class_acc_max', 0.25, ...
    'active_len_super_acc_max', 0.60, ...
    'feature_oracle_acc_max', 0.45);

cfg.split_names = {'train', 'val', 'test'};
cfg.target_class_names = {};
end
