function cfg = generate_cisr24_dataset(cfg)
%GENERATE_CISR24_DATASET Generate the paper-aligned CISR24 dataset.
%
%   CFG = GENERATE_CISR24_DATASET() generates the native 24-class
%   clean dataset using the default configuration from CISR24_DEFAULT_CONFIG.
%
%   CFG = GENERATE_CISR24_DATASET(CFG) uses the provided configuration
%   struct. The function returns the normalized configuration that was used.

if nargin < 1 || isempty(cfg)
    cfg = cisr24_default_config();
end

cfg = i_normalize_config(cfg);
class_specs = i_build_class_specs();
if isfield(cfg, 'target_class_names') && ~isempty(cfg.target_class_names)
    keep_mask = arrayfun(@(spec) any(strcmp(spec.class_name, cfg.target_class_names)), class_specs);
    class_specs = class_specs(keep_mask);
    if isempty(class_specs)
        error('No class_specs matched cfg.target_class_names.');
    end
end

i_prepare_output_root(cfg);
i_write_label_names(cfg, class_specs);
i_snapshot_classes_csv(cfg);
if ~cfg.smoke_test
    i_write_release_meta(cfg, class_specs);
end

manifest_fids = i_open_manifest_files(cfg);
cleanup_manifest = onCleanup(@() i_close_manifest_files(manifest_fids));
h5_writers = i_open_hdf5_writers(cfg, class_specs);

sample_counter = 0;

for split_idx = 1:numel(cfg.split_names)
    split_name = cfg.split_names{split_idx};
    split_count = cfg.counts_per_snr.(split_name);
    writer = h5_writers.(split_name);
    next_index = 1;

    if split_count <= 0
        continue;
    end

    if cfg.verbose
        fprintf('[CISR24] Generating split %s (%d per class per SNR)\n', ...
            split_name, split_count);
    end

    for class_idx = 1:numel(class_specs)
        spec = class_specs(class_idx);

        if cfg.verbose
            fprintf('  [Class %02d/%02d] %s\n', class_idx, numel(class_specs), spec.class_name);
        end

        for snr_idx = 1:numel(cfg.snr_db)
            snr_db = cfg.snr_db(snr_idx);
            block_iq = zeros(cfg.record_len, 2, split_count, 'single');
            block_class_ids = zeros(split_count, 1, 'uint16');
            block_snr = zeros(split_count, 1, 'single');
            block_global_sample_ids = zeros(split_count, 1, 'uint32');

            for local_idx = 1:split_count
                sample_counter = sample_counter + 1;
                sample_id = sprintf('sample_%09d', sample_counter);
                seed = i_compute_seed(cfg, split_idx, spec.order_idx, snr_idx, local_idx);

                [iq_record, meta] = i_generate_clean_sample(spec, cfg, snr_db, seed);
                meta.split_name = split_name;
                h5_index = next_index + local_idx - 1;

                block_iq(:, 1, local_idx) = single(real(iq_record(:)));
                block_iq(:, 2, local_idx) = single(imag(iq_record(:)));
                block_class_ids(local_idx) = uint16(spec.class_id);
                block_snr(local_idx) = single(snr_db);
                block_global_sample_ids(local_idx) = uint32(sample_counter);

                h5_rel_path = strrep(writer.rel_path, filesep, '/');
                i_write_manifest_row( ...
                    manifest_fids.(split_name), cfg, spec, sample_id, seed, meta, ...
                    h5_rel_path, h5_index);
            end

            i_write_hdf5_block(writer, next_index, block_iq, block_class_ids, block_snr, block_global_sample_ids);
            next_index = next_index + split_count;
        end
    end

    if next_index - 1 ~= writer.total_count
        error('Split %s wrote %d samples, expected %d.', split_name, next_index - 1, writer.total_count);
    end
end

if cfg.verbose
    fprintf('[CISR24] Finished generation. Total samples: %d\n', sample_counter);
end

clear cleanup_manifest;
if ~cfg.smoke_test
    i_finalize_release_meta(cfg, sample_counter);
end
end

function cfg = i_normalize_config(cfg)
defaults = cisr24_default_config();
default_fields = fieldnames(defaults);
for idx = 1:numel(default_fields)
    key = default_fields{idx};
    if ~isfield(cfg, key) || isempty(cfg.(key))
        cfg.(key) = defaults.(key);
    end
end

if cfg.smoke_test
    cfg.output_root = fullfile(cfg.dataset_root, 'smoke_v1');
    cfg.manifest_root = fullfile(cfg.output_root, 'manifests');
    cfg.hdf5_root = fullfile(cfg.output_root, 'hdf5');
    cfg.audit_root = fullfile(cfg.output_root, 'audit');
    cfg.release_name = 'CISR24';
    cfg.snr_db = 0;
    cfg.counts_per_snr = struct('train', 1, 'val', 0, 'test', 0);
    cfg.force_overwrite = true;
end

actual_spacing_hz = cfg.cpfsk_modulation_index * cfg.fs_hz / cfg.cpfsk_sps;
if abs(actual_spacing_hz - cfg.cpfsk_tone_spacing_hz) > 1e-6
    error( ...
        'CPFSK h, fs, and sps imply %.6f Hz spacing, configured %.6f Hz.', ...
        actual_spacing_hz, cfg.cpfsk_tone_spacing_hz);
end
end

function specs = i_build_class_specs()
spec_template = i_make_spec(-1, '', '', '', '', struct());
specs = repmat(spec_template, 1, 24);

specs(1) = i_make_spec(0, 'communication', 'BPSK', 'single-carrier-linear-modulation', 'linear_psk', struct('mod_order', 2));
specs(2) = i_make_spec(1, 'communication', 'QPSK', 'single-carrier-linear-modulation', 'linear_psk', struct('mod_order', 4));
specs(3) = i_make_spec(2, 'communication', '8PSK', 'single-carrier-linear-modulation', 'linear_psk', struct('mod_order', 8));
specs(4) = i_make_spec(3, 'communication', '16QAM', 'single-carrier-linear-modulation', 'linear_qam', struct('mod_order', 16));
specs(5) = i_make_spec(4, 'communication', '4FSK', 'continuous-phase-frequency-modulation', 'cpfsk', struct('mod_order', 4));
specs(6) = i_make_spec(5, 'communication', '8FSK', 'continuous-phase-frequency-modulation', 'cpfsk', struct('mod_order', 8));
specs(7) = i_make_spec(6, 'communication', 'GMSK', 'continuous-phase-frequency-modulation', 'gmsk', struct('mod_order', 2));
specs(8) = i_make_spec(7, 'communication', 'OFDM-BPSK', 'ofdm-communication', 'ofdm_psk', struct('mod_order', 2));
specs(9) = i_make_spec(8, 'communication', 'OFDM-QPSK', 'ofdm-communication', 'ofdm_psk', struct('mod_order', 4));
specs(10) = i_make_spec(9, 'communication', 'OFDM-16QAM', 'ofdm-communication', 'ofdm_qam', struct('mod_order', 16));

specs(11) = i_make_spec(10, 'sensing', 'Rect', 'intra-pulse-sensing', 'rect', struct());
specs(12) = i_make_spec(11, 'sensing', 'Barker', 'intra-pulse-sensing', 'barker', struct());
specs(13) = i_make_spec(12, 'sensing', 'LFM', 'intra-pulse-sensing', 'lfm', struct());
specs(14) = i_make_spec(13, 'sensing', 'Costas', 'intra-pulse-sensing', 'costas', struct());
specs(15) = i_make_spec(14, 'sensing', 'Frank', 'intra-pulse-sensing', 'frank', struct());
specs(16) = i_make_spec(15, 'sensing', 'P4', 'intra-pulse-sensing', 'p4', struct());

specs(17) = i_make_spec(16, 'isac', 'LFM-BPSK', 'lfm-psk', 'lfm_phasecoded_psk', struct('mod_order', 2));
specs(18) = i_make_spec(17, 'isac', 'LFM-QPSK', 'lfm-psk', 'lfm_phasecoded_psk', struct('mod_order', 4));
specs(19) = i_make_spec(18, 'isac', 'LFM-8PSK', 'lfm-psk', 'lfm_phasecoded_psk', struct('mod_order', 8));
specs(20) = i_make_spec(19, 'isac', 'LFM-MSK', 'lfm-cpm', 'lfm_chirp_msk', struct());
specs(21) = i_make_spec(20, 'isac', 'LFM-GMSK', 'lfm-cpm', 'lfm_chirp_gmsk', struct());
specs(22) = i_make_spec(21, 'isac', 'OFDM-LFM-BPSK', 'ofdm-lfm', 'ofdm_lfm_isac_psk', struct('mod_order', 2));
specs(23) = i_make_spec(22, 'isac', 'OFDM-LFM-QPSK', 'ofdm-lfm', 'ofdm_lfm_isac_psk', struct('mod_order', 4));
specs(24) = i_make_spec(23, 'isac', 'OFDM-LFM-16QAM', 'ofdm-lfm', 'ofdm_lfm_isac_qam', struct('mod_order', 16));
end

function spec = i_make_spec(class_id, super_class, class_name, family, generator, params)
spec = struct();
spec.class_id = class_id;
spec.order_idx = class_id + 1;
spec.super_class = super_class;
spec.class_name = class_name;
spec.family = family;
spec.generator = generator;
spec.params = params;
end

function i_prepare_output_root(cfg)
if cfg.force_overwrite
    i_cleanup_generated_outputs(cfg.output_root, cfg.manifest_root, cfg.audit_root);
end

required_dirs = { ...
    cfg.output_root, ...
    cfg.manifest_root, ...
    cfg.hdf5_root, ...
    cfg.audit_root};

for idx = 1:numel(required_dirs)
    if ~exist(required_dirs{idx}, 'dir')
        mkdir(required_dirs{idx});
    end
end
end

function i_cleanup_generated_outputs(output_root, manifest_root, audit_root)
if exist(manifest_root, 'dir')
    delete(fullfile(manifest_root, '*.csv'));
end

if exist(audit_root, 'dir')
    delete(fullfile(audit_root, '*'));
end

if exist(output_root, 'dir')
    hdf5_root = fullfile(output_root, 'hdf5');
    if exist(hdf5_root, 'dir')
        delete(fullfile(hdf5_root, '*.h5'));
    end
    delete(fullfile(output_root, 'label_names.txt'));
    delete(fullfile(output_root, 'classes.csv'));
end
end

function i_write_label_names(cfg, class_specs)
path = fullfile(cfg.output_root, 'label_names.txt');
fid = fopen(path, 'w');
if fid < 0
    error('Could not open label names file for writing: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
for idx = 1:numel(class_specs)
    fprintf(fid, '%s\n', class_specs(idx).class_name);
end
clear cleanup;
end

function i_snapshot_classes_csv(cfg)
src = fullfile(cfg.dataset_root, 'classes.csv');
dst = fullfile(cfg.output_root, 'classes.csv');
if exist(src, 'file')
    copyfile(src, dst);
end
end

function i_write_release_meta(cfg, class_specs)
repo_root = fileparts(cfg.dataset_root);
[git_code, git_commit] = system(sprintf('git -C "%s" rev-parse HEAD', repo_root));
[dirty_code, dirty_out] = system(sprintf('git -C "%s" status --short', repo_root));
toolboxes = ver;
toolbox_struct = repmat(struct('Name', '', 'Version', '', 'Release', '', 'Date', ''), numel(toolboxes), 1);
for idx = 1:numel(toolboxes)
    toolbox_struct(idx).Name = toolboxes(idx).Name;
    toolbox_struct(idx).Version = toolboxes(idx).Version;
    toolbox_struct(idx).Release = toolboxes(idx).Release;
    toolbox_struct(idx).Date = toolboxes(idx).Date;
end
class_names = cell(1, numel(class_specs));
for idx = 1:numel(class_specs)
    class_names{idx} = class_specs(idx).class_name;
end
meta = struct();
meta.release_name = cfg.release_name;
meta.output_root = '.';
meta.generation_status = 'in_progress';
meta.generation_started_at = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
meta.matlab_version = version;
meta.toolboxes = toolbox_struct;
public_cfg = cfg;
public_cfg.dataset_root = 'dataset';
public_cfg.output_root = '.';
public_cfg.manifest_root = 'manifests';
public_cfg.hdf5_root = 'hdf5';
public_cfg.audit_root = 'audit';
meta.config = public_cfg;
meta.class_names = class_names;
meta.git_commit = '';
meta.git_probe_ok = git_code == 0 && dirty_code == 0;
if git_code == 0
    meta.git_commit = strtrim(git_commit);
end
meta.git_dirty = dirty_code ~= 0 || ~isempty(strtrim(dirty_out));

meta_path = fullfile(cfg.audit_root, 'release_meta.json');
fid = fopen(meta_path, 'w');
if fid < 0
    error('Could not open release meta for writing: %s', meta_path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(meta, PrettyPrint=true));
clear cleanup;
end

function i_finalize_release_meta(cfg, sample_count)
meta_path = fullfile(cfg.audit_root, 'release_meta.json');
meta = jsondecode(fileread(meta_path));
meta.generation_status = 'complete';
meta.generation_completed_at = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
meta.generated_sample_count = sample_count;
fid = fopen(meta_path, 'w');
if fid < 0
    error('Could not finalize release meta: %s', meta_path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(meta, PrettyPrint=true));
clear cleanup;
end

function manifest_fids = i_open_manifest_files(cfg)
manifest_fids = struct();
header = [ ...
    'sample-id,split,h5-rel-path,h5-dataset,h5-index,class-id,super-class,class-name,waveform-family,snr-db,fs-hz,' ...
    'n-samples,seed,symbol-rate-hz,sps,nfft,cp-len,n-active,chirp-bw-hz,chirp-dir,pulse-width-us,barker-len,' ...
    'costas-len,frank-order,p4-len,active-len,start-offset,channel-profile,release-name,iid-or-ood,' ...
    'rrc-beta,ofdm-num-symbols,costas-df-hz,costas-perm-id,chip-samples,chip-samples-min,chip-samples-max,' ...
    'gmsk-bt,cpfsk-modulation-index,cpfsk-tone-spacing-hz,effective-snr-basis'];

for idx = 1:numel(cfg.split_names)
    split_name = cfg.split_names{idx};
    manifest_path = fullfile(cfg.manifest_root, sprintf('%s_%s_manifest.csv', cfg.manifest_basename, split_name));
    fid = fopen(manifest_path, 'w');
    if fid < 0
        error('Could not open manifest for writing: %s', manifest_path);
    end
    manifest_fids.(split_name) = fid;
    fprintf(fid, '%s\n', header);
end
end

function h5_writers = i_open_hdf5_writers(cfg, class_specs)
h5_writers = struct();
num_classes = numel(class_specs);
num_snr = numel(cfg.snr_db);

for idx = 1:numel(cfg.split_names)
    split_name = cfg.split_names{idx};
    split_count = cfg.counts_per_snr.(split_name);
    total_count = num_classes * num_snr * split_count;
    writer = struct();
    writer.total_count = total_count;
    writer.file_path = '';
    writer.rel_path = '';

    if total_count > 0
        file_name = sprintf('%s_%s.h5', cfg.hdf5_basename, split_name);
        file_path = fullfile(cfg.hdf5_root, file_name);
        chunk_count = min(cfg.hdf5_chunk_samples, total_count);
        h5create(file_path, '/iq', [cfg.record_len, 2, total_count], ...
            'Datatype', 'single', ...
            'ChunkSize', [cfg.record_len, 2, chunk_count]);
        h5create(file_path, '/class-id', [total_count, 1], ...
            'Datatype', 'uint16', ...
            'ChunkSize', [chunk_count, 1]);
        h5create(file_path, '/snr-db', [total_count, 1], ...
            'Datatype', 'single', ...
            'ChunkSize', [chunk_count, 1]);
        h5create(file_path, '/sample-index', [total_count, 1], ...
            'Datatype', 'uint32', ...
            'ChunkSize', [chunk_count, 1]);
        h5writeatt(file_path, '/', 'release_name', cfg.release_name);
        h5writeatt(file_path, '/', 'split', split_name);
        h5writeatt(file_path, '/', 'fs_hz', cfg.fs_hz);
        h5writeatt(file_path, '/', 'record_len', cfg.record_len);
        h5writeatt(file_path, '/', 'total_count', total_count);
        h5writeatt(file_path, '/', 'effective_snr_basis', cfg.effective_snr_basis);
        writer.file_path = file_path;
        writer.rel_path = fullfile('hdf5', file_name);
    end

    h5_writers.(split_name) = writer;
end
end

function i_write_hdf5_block(writer, next_index, block_iq, block_class_ids, block_snr, block_global_sample_ids)
if writer.total_count <= 0
    return;
end

count = size(block_iq, 3);
h5write(writer.file_path, '/iq', block_iq, [1, 1, next_index], [size(block_iq, 1), size(block_iq, 2), count]);
h5write(writer.file_path, '/class-id', block_class_ids, [next_index, 1], [count, 1]);
h5write(writer.file_path, '/snr-db', block_snr, [next_index, 1], [count, 1]);
h5write(writer.file_path, '/sample-index', block_global_sample_ids, [next_index, 1], [count, 1]);
end

function i_close_manifest_files(manifest_fids)
fields = fieldnames(manifest_fids);
for idx = 1:numel(fields)
    fid = manifest_fids.(fields{idx});
    if fid > 0
        fclose(fid);
    end
end
end

function seed = i_compute_seed(cfg, split_idx, class_idx, snr_idx, sample_idx)
seed = cfg.base_seed ...
    + 30000000 * (split_idx - 1) ...
    + 1000000 * (class_idx - 1) ...
    + 10000 * (snr_idx - 1) ...
    + sample_idx;
end

function i_write_manifest_row(fid, cfg, spec, sample_id, seed, meta, h5_rel_path, h5_index)
fmt = [ ...
    '%s,%s,%s,%s,%d,%d,%s,%s,%s,%.6f,%.6f,%d,%d,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%s,' ...
    '%.6f,%.6f,%.6f,%.6f,%.6f,%d,%d,%s,%s,%s,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%s\n'];

fprintf(fid, fmt, ...
    sample_id, ...
    meta.split_name, ...
    h5_rel_path, ...
    '/iq', ...
    h5_index, ...
    spec.class_id, ...
    spec.super_class, ...
    spec.class_name, ...
    spec.family, ...
    meta.snr_db, ...
    cfg.fs_hz, ...
    cfg.record_len, ...
    seed, ...
    meta.symbol_rate_hz, ...
    meta.sps, ...
    meta.nfft, ...
    meta.cp_len, ...
    meta.n_active, ...
    meta.chirp_bw_hz, ...
    meta.chirp_dir, ...
    meta.pulse_width_us, ...
    meta.barker_len, ...
    meta.costas_len, ...
    meta.frank_order, ...
    meta.p4_len, ...
    meta.active_len, ...
    meta.start_offset, ...
    cfg.channel_profile, ...
    cfg.release_name, ...
    cfg.iid_or_ood, ...
    meta.rrc_beta, ...
    meta.ofdm_num_symbols, ...
    meta.costas_df_hz, ...
    meta.costas_perm_id, ...
    meta.chip_samples, ...
    meta.chip_samples_min, ...
    meta.chip_samples_max, ...
    meta.gmsk_bt, ...
    meta.cpfsk_modulation_index, ...
    meta.cpfsk_tone_spacing_hz, ...
    cfg.effective_snr_basis);
end

function [iq_record, meta] = i_generate_clean_sample(spec, cfg, snr_db, seed)
rng(seed, 'twister');

record_len = cfg.record_len;
meta = i_default_meta(spec, snr_db);

switch spec.generator
    case 'linear_psk'
        [burst, params] = i_generate_linear_single_carrier(cfg, spec.params.mod_order, true);
    case 'linear_qam'
        [burst, params] = i_generate_linear_single_carrier(cfg, spec.params.mod_order, false);
    case 'cpfsk'
        [burst, params] = i_generate_cpfsk_burst(cfg, spec.params.mod_order);
    case 'gmsk'
        [burst, params] = i_generate_gmsk_burst(cfg);
    case 'ofdm_psk'
        [burst, params] = i_generate_ofdm_packet(cfg, spec.params.mod_order, true);
    case 'ofdm_qam'
        [burst, params] = i_generate_ofdm_packet(cfg, spec.params.mod_order, false);
    case 'rect'
        [burst, params] = i_generate_rect_pulse(cfg);
    case 'barker'
        [burst, params] = i_generate_barker_pulse(cfg);
    case 'lfm'
        [burst, params] = i_generate_lfm_pulse(cfg);
    case 'costas'
        [burst, params] = i_generate_costas_pulse(cfg);
    case 'frank'
        [burst, params] = i_generate_frank_pulse(cfg);
    case 'p4'
        [burst, params] = i_generate_p4_pulse(cfg);
    case 'lfm_phasecoded_psk'
        [burst, params] = i_generate_lfm_phasecoded_isac(cfg, spec.params.mod_order);
    case 'lfm_chirp_msk'
        [burst, params] = i_generate_lfm_chirp_msk(cfg);
    case 'lfm_chirp_gmsk'
        [burst, params] = i_generate_lfm_chirp_gmsk(cfg);
    case 'ofdm_lfm_isac_psk'
        [burst, params] = i_generate_ofdm_lfm_packet(cfg, spec.params.mod_order, true);
    case 'ofdm_lfm_isac_qam'
        [burst, params] = i_generate_ofdm_lfm_packet(cfg, spec.params.mod_order, false);
    otherwise
        error('Unsupported generator: %s', spec.generator);
end

phi0 = 2 * pi * rand();
burst = burst(:) * exp(1j * phi0);
burst = i_normalize_unit_average_power(burst);

[iq_record, start_offset] = i_embed_burst_in_record(burst, record_len);
if cfg.add_awgn
    iq_record = i_add_complex_awgn(iq_record, snr_db, mean(abs(burst).^2));
end

meta.start_offset = start_offset;
meta.active_len = numel(burst);
meta.symbol_rate_hz = params.symbol_rate_hz;
meta.sps = params.sps;
meta.nfft = params.nfft;
meta.cp_len = params.cp_len;
meta.n_active = params.n_active;
meta.chirp_bw_hz = params.chirp_bw_hz;
meta.chirp_dir = params.chirp_dir;
meta.pulse_width_us = params.pulse_width_us;
meta.barker_len = params.barker_len;
meta.costas_len = params.costas_len;
meta.frank_order = params.frank_order;
meta.p4_len = params.p4_len;
meta.rrc_beta = params.rrc_beta;
meta.ofdm_num_symbols = params.ofdm_num_symbols;
meta.costas_df_hz = params.costas_df_hz;
meta.costas_perm_id = params.costas_perm_id;
meta.chip_samples = params.chip_samples;
meta.chip_samples_min = params.chip_samples_min;
meta.chip_samples_max = params.chip_samples_max;
meta.gmsk_bt = params.gmsk_bt;
meta.cpfsk_modulation_index = params.cpfsk_modulation_index;
meta.cpfsk_tone_spacing_hz = params.cpfsk_tone_spacing_hz;
end

function meta = i_default_meta(spec, snr_db)
meta = struct();
meta.split_name = '';
meta.snr_db = snr_db;
meta.symbol_rate_hz = NaN;
meta.sps = NaN;
meta.nfft = NaN;
meta.cp_len = NaN;
meta.n_active = NaN;
meta.chirp_bw_hz = NaN;
meta.chirp_dir = 'none';
meta.pulse_width_us = NaN;
meta.barker_len = NaN;
meta.costas_len = NaN;
meta.frank_order = NaN;
meta.p4_len = NaN;
meta.active_len = NaN;
meta.start_offset = NaN;
meta.rrc_beta = NaN;
meta.ofdm_num_symbols = NaN;
meta.costas_df_hz = NaN;
meta.costas_perm_id = NaN;
meta.chip_samples = NaN;
meta.chip_samples_min = NaN;
meta.chip_samples_max = NaN;
meta.gmsk_bt = NaN;
meta.cpfsk_modulation_index = NaN;
meta.cpfsk_tone_spacing_hz = NaN;
meta.super_class = spec.super_class;
meta.class_name = spec.class_name;
meta.family = spec.family;
end

function [record, start_offset] = i_embed_burst_in_record(burst, record_len)
active_len = numel(burst);
if active_len > record_len
    error('Burst length %d exceeds record length %d.', active_len, record_len);
end

max_offset = record_len - active_len;
start_offset = randi([0, max_offset]);
record = complex(zeros(record_len, 1));
record(start_offset + 1:start_offset + active_len) = burst;
end

function x = i_normalize_unit_average_power(x)
power_val = mean(abs(x).^2);
if power_val <= 0
    return;
end
x = x / sqrt(power_val);
end

function y = i_add_complex_awgn(x, snr_db, signal_power)
if signal_power <= 0
    y = x;
    return;
end
snr_linear = 10^(snr_db / 10);
noise_power = signal_power / snr_linear;
noise_sigma = sqrt(noise_power / 2);
noise = noise_sigma * (randn(size(x)) + 1j * randn(size(x)));
y = x + noise;
end

function [burst, params] = i_generate_linear_single_carrier(cfg, mod_order, is_psk)
sps = cfg.single_carrier_sps;
active_len = cfg.comm_active_lengths(randi(numel(cfg.comm_active_lengths)));
beta = cfg.rrc_rolloff_choices(randi(numel(cfg.rrc_rolloff_choices)));
span = cfg.rrc_span_symbols;
group_delay = (span * sps) / 2;
num_symbols = ceil((active_len + 2 * group_delay) / sps) + 4;

data = randi([0, mod_order - 1], num_symbols, 1);
if is_psk
    phase_offset = 0;
    if mod_order > 2
        phase_offset = pi / mod_order;
    end
    symbols = pskmod(data, mod_order, phase_offset, 'gray');
else
    symbols = qammod(data, mod_order, 'gray', 'UnitAveragePower', true);
end

rrc = i_cached_rrc_filter(beta, span, sps);
shaped = upfirdn(symbols, rrc, sps, 1);
start_idx = group_delay + 1;
burst = shaped(start_idx:start_idx + active_len - 1);

params = i_empty_param_struct();
params.symbol_rate_hz = cfg.fs_hz / sps;
params.sps = sps;
params.rrc_beta = beta;
end

function [burst, params] = i_generate_cpfsk_burst(cfg, mod_order)
sps = cfg.cpfsk_sps;
active_len = cfg.comm_active_lengths(randi(numel(cfg.comm_active_lengths)));
num_symbols = ceil(active_len / sps) + 4;
data = randi([0, mod_order - 1], num_symbols, 1);
cpfsk_symbols = 2 * data - (mod_order - 1);
modulator = comm.CPFSKModulator( ...
    'BitInput', false, ...
    'ModulationOrder', mod_order, ...
    'ModulationIndex', cfg.cpfsk_modulation_index, ...
    'SamplesPerSymbol', sps, ...
    'OutputDataType', 'double');
wave = modulator(cpfsk_symbols);
burst = i_crop_center(wave, active_len);

params = i_empty_param_struct();
params.symbol_rate_hz = cfg.fs_hz / sps;
params.sps = sps;
params.cpfsk_modulation_index = cfg.cpfsk_modulation_index;
params.cpfsk_tone_spacing_hz = cfg.cpfsk_tone_spacing_hz;
end

function [burst, params] = i_generate_gmsk_burst(cfg)
sps = cfg.single_carrier_sps;
active_len = cfg.comm_active_lengths(randi(numel(cfg.comm_active_lengths)));
num_bits = ceil(active_len / sps) + 8;
bits = randi([0, 1], num_bits, 1);

modulator = comm.GMSKModulator( ...
    'BitInput', true, ...
    'BandwidthTimeProduct', cfg.gmsk_bt, ...
    'PulseLength', cfg.gmsk_pulse_length, ...
    'SamplesPerSymbol', sps, ...
    'OutputDataType', 'double');
wave = modulator(bits);
burst = i_crop_center(wave, active_len);

params = i_empty_param_struct();
params.symbol_rate_hz = cfg.fs_hz / sps;
params.sps = sps;
params.gmsk_bt = cfg.gmsk_bt;
end

function [burst, params] = i_generate_ofdm_packet(cfg, mod_order, is_psk)
nfft = cfg.ofdm_nfft;
cp_len = cfg.ofdm_cp;
n_active = cfg.ofdm_active_choices(randi(numel(cfg.ofdm_active_choices)));
num_symbols = cfg.ofdm_symbol_choices(randi(numel(cfg.ofdm_symbol_choices)));
symbol_len = nfft + cp_len;
packet_len = num_symbols * symbol_len;

burst = complex(zeros(packet_len, 1));
cursor = 1;
for sym_idx = 1:num_symbols
    fd = i_make_ofdm_symbol(nfft, n_active, mod_order, is_psk);
    td = ifft(ifftshift(fd), nfft);
    with_cp = [td(end - cp_len + 1:end); td];
    burst(cursor:cursor + symbol_len - 1) = with_cp;
    cursor = cursor + symbol_len;
end

params = i_empty_param_struct();
params.nfft = nfft;
params.cp_len = cp_len;
params.n_active = n_active;
params.ofdm_num_symbols = num_symbols;
end

function fd = i_make_ofdm_symbol(nfft, n_active, mod_order, is_psk)
fd = complex(zeros(nfft, 1));
[~, pilot_bins, data_bins] = i_make_ofdm_bin_layout(nfft, n_active);
data = randi([0, mod_order - 1], numel(data_bins), 1);

if is_psk
    phase_offset = 0;
    if mod_order > 2
        phase_offset = pi / mod_order;
    end
    symbols = pskmod(data, mod_order, phase_offset, 'gray');
else
    symbols = qammod(data, mod_order, 'gray', 'UnitAveragePower', true);
end

fd(pilot_bins) = ones(numel(pilot_bins), 1);
fd(data_bins) = symbols;
end

function [active_bins, pilot_bins, data_bins] = i_make_ofdm_bin_layout(nfft, n_active)
center = nfft / 2 + 1;
half = n_active / 2;
if mod(half, 4) ~= 0
    error('n_active/2 must be divisible by 4, got n_active=%d', n_active);
end

left_bins = center - half:center - 1;
right_bins = center + 1:center + half;
pilot_offsets = [half / 4, 3 * half / 4];
pilot_bins = [left_bins(pilot_offsets), right_bins(pilot_offsets)];
active_bins = [left_bins, right_bins];
data_bins = setdiff(active_bins, pilot_bins, 'stable');
end

function [burst, params] = i_generate_rect_pulse(cfg)
active_len = cfg.radar_active_lengths(randi(numel(cfg.radar_active_lengths)));
burst = ones(active_len, 1);

params = i_empty_param_struct();
params.pulse_width_us = 1e6 * active_len / cfg.fs_hz;
end

function [burst, params] = i_generate_barker_pulse(cfg)
num_chips_choices = [7, 11, 13];
num_chips = num_chips_choices(randi(numel(num_chips_choices)));
active_len = cfg.radar_active_lengths(randi(numel(cfg.radar_active_lengths)));
code = i_barker_code(num_chips);
chip_index = min(floor((0:active_len - 1).' * num_chips / active_len) + 1, num_chips);
burst = code(chip_index);
chip_widths = accumarray(chip_index, 1, [num_chips, 1]);

params = i_empty_param_struct();
params.pulse_width_us = 1e6 * active_len / cfg.fs_hz;
params.barker_len = num_chips;
params.chip_samples_min = min(chip_widths);
params.chip_samples_max = max(chip_widths);
end

function [burst, params] = i_generate_lfm_pulse(cfg)
active_len = cfg.radar_active_lengths(randi(numel(cfg.radar_active_lengths)));
bw_hz = cfg.chirp_bandwidth_choices_hz(randi(numel(cfg.chirp_bandwidth_choices_hz)));
chirp_dir = i_random_chirp_direction();
burst = i_make_centered_chirp(active_len, cfg.fs_hz, bw_hz, chirp_dir);

params = i_empty_param_struct();
params.pulse_width_us = 1e6 * active_len / cfg.fs_hz;
params.chirp_bw_hz = bw_hz;
params.chirp_dir = chirp_dir;
end

function [burst, params] = i_generate_costas_pulse(cfg)
costas_len_choices = [7, 11, 13];
costas_len = costas_len_choices(randi(numel(costas_len_choices)));
active_len = cfg.radar_active_lengths(randi(numel(cfg.radar_active_lengths)));
pool = i_costas_permutation_pool(costas_len);
perm_id = randi(size(pool, 1));
permutation = pool(perm_id, :);
df_hz = cfg.costas_frequency_step_choices_hz(randi(numel(cfg.costas_frequency_step_choices_hz)));
freq_idx = permutation(:) - (costas_len + 1) / 2;
chip_index = min(floor((0:active_len - 1).' * costas_len / active_len) + 1, costas_len);
freqs = freq_idx(chip_index) * df_hz;
chip_widths = accumarray(chip_index, 1, [costas_len, 1]);
phase = 2 * pi * cumsum(freqs) / cfg.fs_hz;
burst = exp(1j * phase(:));

params = i_empty_param_struct();
params.pulse_width_us = 1e6 * active_len / cfg.fs_hz;
params.costas_len = costas_len;
params.costas_df_hz = df_hz;
params.costas_perm_id = perm_id;
params.chip_samples_min = min(chip_widths);
params.chip_samples_max = max(chip_widths);
end

function [burst, params] = i_generate_frank_pulse(cfg)
chip_samples = [36, 40, 44, 48, 52];
chip_samples = chip_samples(randi(numel(chip_samples)));
num_chips = 16;
active_len = chip_samples * num_chips;

waveform = phased.PhaseCodedWaveform( ...
    'SampleRate', cfg.fs_hz, ...
    'Code', 'Frank', ...
    'NumChips', num_chips, ...
    'ChipWidth', chip_samples / cfg.fs_hz, ...
    'PRF', 1e3, ...
    'OutputFormat', 'Samples', ...
    'NumSamples', active_len);

burst = waveform();

params = i_empty_param_struct();
params.pulse_width_us = 1e6 * active_len / cfg.fs_hz;
params.frank_order = 4;
params.chip_samples = chip_samples;
end

function [burst, params] = i_generate_p4_pulse(cfg)
code_lengths = [16, 32];
code_len = code_lengths(randi(numel(code_lengths)));
if code_len == 16
    chip_options = [36, 40, 44, 48, 52];
else
    chip_options = [18, 20, 22, 24, 26];
end
chip_samples = chip_options(randi(numel(chip_options)));
active_len = code_len * chip_samples;

waveform = phased.PhaseCodedWaveform( ...
    'SampleRate', cfg.fs_hz, ...
    'Code', 'P4', ...
    'NumChips', code_len, ...
    'ChipWidth', chip_samples / cfg.fs_hz, ...
    'PRF', 1e3, ...
    'OutputFormat', 'Samples', ...
    'NumSamples', active_len);

burst = waveform();

params = i_empty_param_struct();
params.pulse_width_us = 1e6 * active_len / cfg.fs_hz;
params.p4_len = code_len;
params.chip_samples = chip_samples;
end

function [burst, params] = i_generate_lfm_phasecoded_isac(cfg, mod_order)
sps = cfg.single_carrier_sps;
active_len = cfg.radar_active_lengths(randi(numel(cfg.radar_active_lengths)));
num_symbols = active_len / sps;
if mod(num_symbols, 1) ~= 0
    error('active_len must be divisible by sps for phase-coded chirp, got %d', active_len);
end

bw_hz = cfg.chirp_bandwidth_choices_hz(randi(numel(cfg.chirp_bandwidth_choices_hz)));
chirp_dir = i_random_chirp_direction();
chirp = i_make_centered_chirp(active_len, cfg.fs_hz, bw_hz, chirp_dir);
data = randi([0, mod_order - 1], num_symbols, 1);
phase_offset = 0;
if mod_order > 2
    phase_offset = pi / mod_order;
end
symbols = pskmod(data, mod_order, phase_offset, 'gray');
phase_code = repelem(symbols(:), sps);
burst = chirp(:) .* phase_code(:);

params = i_empty_param_struct();
params.symbol_rate_hz = cfg.fs_hz / sps;
params.sps = sps;
params.chirp_bw_hz = bw_hz;
params.chirp_dir = chirp_dir;
end

function [burst, params] = i_generate_lfm_chirp_msk(cfg)
sps = cfg.single_carrier_sps;
active_len = cfg.radar_active_lengths(randi(numel(cfg.radar_active_lengths)));
num_symbols = ceil(active_len / sps) + 4;
data = randi([0, 1], num_symbols, 1);
cpfsk_symbols = 2 * data - 1;
modulator = comm.CPFSKModulator( ...
    'BitInput', false, ...
    'ModulationOrder', 2, ...
    'ModulationIndex', 0.5, ...
    'SamplesPerSymbol', sps, ...
    'OutputDataType', 'double');
wave = modulator(cpfsk_symbols);
wave = i_crop_center(wave, active_len);

bw_hz = cfg.chirp_bandwidth_choices_hz(randi(numel(cfg.chirp_bandwidth_choices_hz)));
chirp_dir = i_random_chirp_direction();
chirp = i_make_centered_chirp(numel(wave), cfg.fs_hz, bw_hz, chirp_dir);
burst = wave(:) .* chirp(:);

params = i_empty_param_struct();
params.symbol_rate_hz = cfg.fs_hz / sps;
params.sps = sps;
params.chirp_bw_hz = bw_hz;
params.chirp_dir = chirp_dir;
end

function [burst, params] = i_generate_lfm_chirp_gmsk(cfg)
sps = cfg.single_carrier_sps;
active_len = cfg.radar_active_lengths(randi(numel(cfg.radar_active_lengths)));
num_bits = ceil(active_len / sps) + 8;
bits = randi([0, 1], num_bits, 1);
modulator = comm.GMSKModulator( ...
    'BitInput', true, ...
    'BandwidthTimeProduct', cfg.gmsk_bt, ...
    'PulseLength', cfg.gmsk_pulse_length, ...
    'SamplesPerSymbol', sps, ...
    'OutputDataType', 'double');
wave = modulator(bits);
wave = i_crop_center(wave, active_len);

bw_hz = cfg.chirp_bandwidth_choices_hz(randi(numel(cfg.chirp_bandwidth_choices_hz)));
chirp_dir = i_random_chirp_direction();
chirp = i_make_centered_chirp(numel(wave), cfg.fs_hz, bw_hz, chirp_dir);
burst = wave(:) .* chirp(:);

params = i_empty_param_struct();
params.symbol_rate_hz = cfg.fs_hz / sps;
params.sps = sps;
params.chirp_bw_hz = bw_hz;
params.chirp_dir = chirp_dir;
params.gmsk_bt = cfg.gmsk_bt;
end

function [burst, params] = i_generate_ofdm_lfm_packet(cfg, mod_order, is_psk)
nfft = cfg.ofdm_nfft;
cp_len = cfg.ofdm_cp;
n_active = cfg.ofdm_active_choices(randi(numel(cfg.ofdm_active_choices)));
num_symbols = cfg.ofdm_symbol_choices(randi(numel(cfg.ofdm_symbol_choices)));
symbol_len = nfft + cp_len;
packet_len = num_symbols * symbol_len;
fs_hz = cfg.fs_hz;

bw_hz = cfg.chirp_bandwidth_choices_hz(randi(numel(cfg.chirp_bandwidth_choices_hz)));
chirp_dir = i_random_chirp_direction();
[active_bins, pilot_bins, data_bins] = i_make_ofdm_bin_layout(nfft, n_active);
pilot_symbol = 1.0;

chirp_data_bins = i_select_ofdm_lfm_chirp_data_bins(cfg, data_bins);
regular_full_basis = i_build_regular_ofdm_basis(nfft, active_bins);
chirp_subset_basis = i_build_chirp_subcarrier_basis( ...
    nfft, fs_hz, chirp_data_bins, bw_hz, chirp_dir, cfg.ofdm_lfm_subcarrier_chirp_strength);
regular_subset_basis = i_build_regular_ofdm_basis(nfft, chirp_data_bins);
mix_alpha = cfg.ofdm_lfm_mix_alpha;

burst = complex(zeros(packet_len, 1));
cursor = 1;
for sym_idx = 1:num_symbols
    all_symbols = i_make_ofdm_symbol_data(n_active, mod_order, is_psk);
    fd = complex(zeros(nfft, 1));
    fd(pilot_bins) = pilot_symbol;
    fd(data_bins) = all_symbols;

    symbols_full = zeros(numel(active_bins), 1);
    for idx = 1:numel(active_bins)
        symbols_full(idx) = fd(active_bins(idx));
    end

    symbols_chirp = zeros(numel(chirp_data_bins), 1);
    for idx = 1:numel(chirp_data_bins)
        symbols_chirp(idx) = fd(chirp_data_bins(idx));
    end

    td_regular_full = regular_full_basis * symbols_full;
    td_regular_subset = regular_subset_basis * symbols_chirp;
    td_chirp_subset = chirp_subset_basis * symbols_chirp;
    td = td_regular_full + mix_alpha * (td_chirp_subset - td_regular_subset);
    td = td / sqrt(mean(abs(td).^2) + 1e-12);
    with_cp = [td(end - cp_len + 1:end); td];
    burst(cursor:cursor + numel(with_cp) - 1) = with_cp;
    cursor = cursor + numel(with_cp);
end

params = i_empty_param_struct();
params.nfft = nfft;
params.cp_len = cp_len;
params.n_active = n_active;
params.chirp_bw_hz = bw_hz;
params.chirp_dir = chirp_dir;
params.ofdm_num_symbols = num_symbols;
end

function bins = i_select_ofdm_lfm_chirp_data_bins(cfg, data_bins)
if isempty(data_bins)
    bins = data_bins;
    return;
end

switch cfg.ofdm_lfm_chirp_layout
    case 'comb_data_every4'
        bins = data_bins(1:4:end);
    otherwise
        error('Unsupported cfg.ofdm_lfm_chirp_layout: %s', cfg.ofdm_lfm_chirp_layout);
end

if isempty(bins)
    bins = data_bins(1);
end
end

function symbols = i_make_ofdm_symbol_data(n_active, mod_order, is_psk)
num_pilots = 4;
num_data = n_active - num_pilots;
data = randi([0, mod_order - 1], num_data, 1);

if is_psk
    phase_offset = 0;
    if mod_order > 2
        phase_offset = pi / mod_order;
    end
    symbols = pskmod(data, mod_order, phase_offset, 'gray');
else
    symbols = qammod(data, mod_order, 'gray', 'UnitAveragePower', true);
end
end

function basis = i_build_regular_ofdm_basis(nfft, bins)
persistent regular_basis_cache;
if isempty(regular_basis_cache)
    regular_basis_cache = containers.Map('KeyType', 'char', 'ValueType', 'any');
end
cache_key = sprintf('nfft=%d|bins=%s', nfft, sprintf('%d,', bins));
if isKey(regular_basis_cache, cache_key)
    basis = regular_basis_cache(cache_key);
    return;
end
center = nfft / 2 + 1;
n = (0:nfft - 1).';
basis = complex(zeros(nfft, numel(bins)));
for idx = 1:numel(bins)
    k = bins(idx) - center;
    basis(:, idx) = exp(1j * 2 * pi * k * n / nfft) / sqrt(nfft);
end
regular_basis_cache(cache_key) = basis;
end

function basis = i_build_chirp_subcarrier_basis(nfft, fs_hz, active_bins, bw_hz, chirp_dir, chirp_strength)
persistent chirp_basis_cache;
if isempty(chirp_basis_cache)
    chirp_basis_cache = containers.Map('KeyType', 'char', 'ValueType', 'any');
end
cache_key = sprintf( ...
    'nfft=%d|fs=%.12g|bw=%.12g|dir=%s|strength=%.12g|bins=%s', ...
    nfft, fs_hz, bw_hz, chirp_dir, chirp_strength, sprintf('%d,', active_bins));
if isKey(chirp_basis_cache, cache_key)
    basis = chirp_basis_cache(cache_key);
    return;
end
tau = ((0:nfft - 1).' - (nfft - 1) / 2) / fs_hz;
duration = nfft / fs_hz;
base_k = bw_hz / duration;
center = nfft / 2 + 1;
norm_scale = max(abs(active_bins - center));
if norm_scale == 0
    norm_scale = 1;
end

basis = complex(zeros(nfft, numel(active_bins)));
for idx = 1:numel(active_bins)
    bin = active_bins(idx);
    freq_hz = (bin - center) * fs_hz / nfft;
    rel = (bin - center) / norm_scale;
    local_k = chirp_strength * rel * base_k;
    if strcmp(chirp_dir, 'down')
        local_k = -local_k;
    end
    instantaneous_frequency = freq_hz + local_k * tau;
    if max(abs(instantaneous_frequency)) >= fs_hz / 2
        error( ...
            'OFDM-LFM chirp aliases: bin=%d, max |f|=%.6f Hz, Nyquist=%.6f Hz.', ...
            bin, max(abs(instantaneous_frequency)), fs_hz / 2);
    end
    phase = 2 * pi * freq_hz * tau + pi * local_k * tau .^ 2;
    wave = exp(1j * phase);
    basis(:, idx) = wave / sqrt(sum(abs(wave).^2) + 1e-12);
end
chirp_basis_cache(cache_key) = basis;
end

function rrc = i_cached_rrc_filter(beta, span, sps)
persistent rrc_cache;
if isempty(rrc_cache)
    rrc_cache = containers.Map('KeyType', 'char', 'ValueType', 'any');
end
cache_key = sprintf('beta=%.12g|span=%d|sps=%d', beta, span, sps);
if isKey(rrc_cache, cache_key)
    rrc = rrc_cache(cache_key);
    return;
end
rrc = rcosdesign(beta, span, sps, 'sqrt');
rrc_cache(cache_key) = rrc;
end

function code = i_barker_code(num_chips)
switch num_chips
    case 7
        code = [1; 1; 1; -1; -1; 1; -1];
    case 11
        code = [1; 1; 1; -1; -1; -1; 1; -1; -1; 1; -1];
    case 13
        code = [1; 1; 1; 1; 1; -1; -1; 1; 1; -1; 1; -1; 1];
    otherwise
        error('Unsupported Barker length: %d', num_chips);
end
end

function pool = i_costas_permutation_pool(costas_len)
switch costas_len
    case 7
        base = [1, 2, 6, 4, 7, 3, 5];
    case 11
        base = [1, 2, 5, 9, 4, 11, 10, 7, 3, 8, 6];
    case 13
        base = [1, 2, 4, 9, 13, 6, 12, 11, 7, 5, 8, 3, 10];
    otherwise
        error('Unsupported Costas length: %d', costas_len);
end

pool = [ ...
    base; ...
    fliplr(base); ...
    (costas_len + 1) - base; ...
    fliplr((costas_len + 1) - base)];
end

function chirp_dir = i_random_chirp_direction()
if rand() < 0.5
    chirp_dir = 'up';
else
    chirp_dir = 'down';
end
end

function chirp = i_make_centered_chirp(num_samples, fs_hz, bw_hz, chirp_dir)
t = (0:num_samples - 1).' / fs_hz;
duration = num_samples / fs_hz;
k = bw_hz / duration;

if strcmp(chirp_dir, 'up')
    phase = 2 * pi * ((-bw_hz / 2) * t + 0.5 * k * t.^2);
else
    phase = 2 * pi * ((bw_hz / 2) * t - 0.5 * k * t.^2);
end

chirp = exp(1j * phase);
end

function out = i_crop_center(x, target_len)
x = x(:);
if numel(x) < target_len
    out = [x; zeros(target_len - numel(x), 1)];
    return;
end

start_idx = floor((numel(x) - target_len) / 2) + 1;
out = x(start_idx:start_idx + target_len - 1);
end

function params = i_empty_param_struct()
params = struct();
params.symbol_rate_hz = NaN;
params.sps = NaN;
params.nfft = NaN;
params.cp_len = NaN;
params.n_active = NaN;
params.chirp_bw_hz = NaN;
params.chirp_dir = 'none';
params.pulse_width_us = NaN;
params.barker_len = NaN;
params.costas_len = NaN;
params.frank_order = NaN;
params.p4_len = NaN;
params.rrc_beta = NaN;
params.ofdm_num_symbols = NaN;
params.costas_df_hz = NaN;
params.costas_perm_id = NaN;
params.chip_samples = NaN;
params.chip_samples_min = NaN;
params.chip_samples_max = NaN;
params.gmsk_bt = NaN;
params.cpfsk_modulation_index = NaN;
params.cpfsk_tone_spacing_hz = NaN;
end
