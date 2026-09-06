use crate::types::Sample;
use rustfft::FftPlanner;

pub struct Fft {
    planner: FftPlanner<f32>,
}

impl Fft {
    pub fn new() -> Self {
        Self {
            planner: FftPlanner::new(),
        }
    }

    fn fft_shift(data: Vec<Sample>) -> Vec<Sample> {
        let mid = data.len() / 2;
        let mut shifted_buffer = vec![Sample::default(); data.len()];

        shifted_buffer[..mid].copy_from_slice(&data[mid..]);
        shifted_buffer[mid..].copy_from_slice(&data[..mid]);

        shifted_buffer
    }

    pub fn ifft(&mut self, frequency_data: Vec<Sample>, fft_size: usize) -> Vec<Sample> {
        let n = frequency_data.len();

        let half = n / 2;

        let mut ifft_buffer = vec![Sample::new(0.0, 0.0); fft_size];

        ifft_buffer[1..=half].copy_from_slice(&frequency_data[half..]);
        ifft_buffer[fft_size - half..].copy_from_slice(&frequency_data[..half]);

        let ifft = self.planner.plan_fft_inverse(fft_size);
        ifft.process(&mut ifft_buffer);

        let scale = 1.0 / (fft_size as f32).sqrt(); // согласовано с fft()
        for sample in ifft_buffer.iter_mut() {
            *sample *= scale;
        }

        ifft_buffer
    }

    pub fn fft(&mut self, mut time_domain_data: Vec<Sample>, fft_size: usize) -> Vec<Sample> {
        let fft = self.planner.plan_fft_forward(fft_size);
        fft.process(&mut time_domain_data);

        let scale = 1.0 / (fft_size as f32).sqrt();
        time_domain_data.iter_mut().for_each(|sample| {
            sample.re *= scale;
            sample.im *= scale;
        });

        Self::fft_shift(time_domain_data)
    }
}
