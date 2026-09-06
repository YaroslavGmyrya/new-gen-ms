use crate::types::Sample;
pub struct Correlator;

impl Correlator {
    pub fn correlation(signal: Vec<Sample>, reference: Vec<Sample>) -> Vec<f32> {
        let ref_len = reference.len();
        let sig_len = signal.len();

        if ref_len == 0 || sig_len < ref_len {
            return Vec::new();
        }

        let ref_energy: f32 = reference.iter().map(|s| s.norm_sqr()).sum();
        let n_offsets = sig_len - ref_len + 1;
        let mut result = Vec::with_capacity(n_offsets);

        for offset in 0..n_offsets {
            let mut acc = Sample::new(0.0, 0.0);
            let mut sig_energy = 0.0f32;

            for k in 0..ref_len {
                let s = signal[offset + k];
                acc += s * reference[k].conj();
                sig_energy += s.norm_sqr();
            }

            let denom = (sig_energy * ref_energy).sqrt();
            let value = if denom > f32::EPSILON {
                acc.norm() / denom
            } else {
                0.0
            };

            result.push(value);
        }

        result
    }

    pub fn cp_correlation(samples: Vec<Sample>, fft_size: usize, cp_len: usize) -> Vec<f32> {
        let total_len = samples.len();
        let window = fft_size + cp_len;

        assert!(
            total_len >= window,
            "samples too short for given fft_size + cp_len"
        );

        let num_positions = total_len - window + 1;
        let mut total_corr = Vec::with_capacity(num_positions);

        for d in 0..num_positions {
            let sig_window = samples[d..d + cp_len].to_vec();
            let ref_window = samples[d + fft_size..d + fft_size + cp_len].to_vec();

            let corr = Self::correlation(sig_window, ref_window);

            total_corr.push(corr.first().copied().unwrap_or(0.0));
        }

        total_corr
    }

    pub fn find_peak(corr: Vec<f32>) -> (usize, f32) {
        corr.into_iter()
            .enumerate()
            .filter(|(_, v)| !v.is_nan())
            .fold(None, |best, (i, v)| match best {
                Some((_, bv)) if bv >= v => best,
                _ => Some((i, v)),
            })
            .unwrap_or((0, 0.0))
    }
}
