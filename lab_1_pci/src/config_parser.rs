use crate::types::config::*;
use std::fs;

impl Config {
    pub fn from_file(filename: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let contents = fs::read_to_string(filename)?;
        let config: Config = toml::from_str(&contents)?;
        Ok(config)
    }

    pub fn get_samples_count(&self) -> usize {
        let duration_s = self.record_duration_ms as f32 * 1e-3;
        let fs_hz = self.fs * 1e6;
        (duration_s * fs_hz).round() as usize
    }

    pub fn get_time_step_ms(&self) -> f32 {
        1.0 / (self.fs * 1e6) * 1e3
    }

    pub fn get_timeline(&self) -> Vec<f32> {
        let dt = self.get_time_step_ms();
        let samples_count = self.get_samples_count();

        (0..samples_count).map(|i| i as f32 * dt).collect()
    }
}
