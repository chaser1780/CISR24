function report = verify_cisr24_waveform_conformance(output_json)
%VERIFY_CISR24_WAVEFORM_CONFORMANCE Verify IQ-level paper parameter contracts.

if nargin < 1
    output_json = '';
end
cfg = cisr24_default_config();
report = struct();
report.status = 'pass';
cpfsk_cases = repmat(struct( ...
    'modulation_order', 0, ...
    'tones_hz', [], ...
    'adjacent_spacings_hz', []), 1, 2);

for case_index = 1:2
    mod_order = [4, 8];
    mod_order = mod_order(case_index);
    levels = -(mod_order - 1):2:(mod_order - 1);
    tones_hz = zeros(size(levels));
    for idx = 1:numel(levels)
        modulator = comm.CPFSKModulator( ...
            'BitInput', false, ...
            'ModulationOrder', mod_order, ...
            'ModulationIndex', cfg.cpfsk_modulation_index, ...
            'SamplesPerSymbol', cfg.cpfsk_sps, ...
            'OutputDataType', 'double');
        waveform = modulator(levels(idx) * ones(400, 1));
        steady = waveform(101:end);
        tones_hz(idx) = mean(diff(unwrap(angle(steady)))) / (2 * pi) * cfg.fs_hz;
    end
    spacings_hz = diff(tones_hz);
    if max(abs(spacings_hz - cfg.cpfsk_tone_spacing_hz)) > 1e-3
        error('CPFSK M=%d does not realize %.6f Hz adjacent spacing.', ...
            mod_order, cfg.cpfsk_tone_spacing_hz);
    end
    cpfsk_cases(case_index).modulation_order = mod_order;
    cpfsk_cases(case_index).tones_hz = tones_hz;
    cpfsk_cases(case_index).adjacent_spacings_hz = spacings_hz;
end
report.cpfsk = cpfsk_cases;

max_abs_frequency_hz = 0;
cases = repmat(struct( ...
    'n_active', 0, ...
    'bandwidth_hz', 0, ...
    'direction', 0, ...
    'chirp_carrier_count', 0, ...
    'max_abs_instantaneous_frequency_hz', 0), 1, 12);
case_index = 0;
for n_active = cfg.ofdm_active_choices
    center = cfg.ofdm_nfft / 2 + 1;
    half = n_active / 2;
    left_bins = center - half:center - 1;
    right_bins = center + 1:center + half;
    pilot_offsets = [half / 4, 3 * half / 4];
    pilot_bins = [left_bins(pilot_offsets), right_bins(pilot_offsets)];
    data_bins = setdiff([left_bins, right_bins], pilot_bins, 'stable');
    chirp_bins = data_bins(1:4:end);
    norm_scale = max(abs(chirp_bins - center));
    tau = ((0:cfg.ofdm_nfft - 1).' - (cfg.ofdm_nfft - 1) / 2) / cfg.fs_hz;
    duration = cfg.ofdm_nfft / cfg.fs_hz;
    for bandwidth_hz = cfg.chirp_bandwidth_choices_hz
        for direction_sign = [-1, 1]
            case_max = 0;
            for bin = chirp_bins
                carrier_hz = (bin - center) * cfg.fs_hz / cfg.ofdm_nfft;
                relative_offset = (bin - center) / norm_scale;
                chirp_rate = direction_sign * cfg.ofdm_lfm_subcarrier_chirp_strength ...
                    * relative_offset * bandwidth_hz / duration;
                instantaneous_frequency = carrier_hz + chirp_rate * tau;
                case_max = max(case_max, max(abs(instantaneous_frequency)));
            end
            if case_max >= cfg.fs_hz / 2
                error('OFDM-LFM aliases for Nactive=%d, B=%.6f Hz.', ...
                    n_active, bandwidth_hz);
            end
            max_abs_frequency_hz = max(max_abs_frequency_hz, case_max);
            case_index = case_index + 1;
            cases(case_index).n_active = n_active;
            cases(case_index).bandwidth_hz = bandwidth_hz;
            cases(case_index).direction = direction_sign;
            cases(case_index).chirp_carrier_count = numel(chirp_bins);
            cases(case_index).max_abs_instantaneous_frequency_hz = case_max;
        end
    end
end
report.ofdm_lfm = struct( ...
    'nyquist_hz', cfg.fs_hz / 2, ...
    'max_abs_instantaneous_frequency_hz', max_abs_frequency_hz, ...
    'cases', cases);
report.checked_at = char(datetime('now', 'TimeZone', 'UTC', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));

if ~isempty(output_json)
    output_dir = fileparts(output_json);
    if ~isempty(output_dir) && ~exist(output_dir, 'dir')
        mkdir(output_dir);
    end
    fid = fopen(output_json, 'w');
    if fid < 0
        error('Could not write conformance report: %s', output_json);
    end
    cleanup = onCleanup(@() fclose(fid));
    fprintf(fid, '%s\n', jsonencode(report, PrettyPrint=true));
    clear cleanup;
end
end
