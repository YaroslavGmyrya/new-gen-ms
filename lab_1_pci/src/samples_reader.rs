use crate::types::Sample;
use crate::types::config::*;
use std::fs::File;
use std::io::{BufReader, Read};

pub fn pcm_reader(file_path: &str, config: &Config) -> std::io::Result<Vec<Sample>> {
    let file = File::open(file_path)?;

    let mut reader = BufReader::new(file);

    let mut samples: Vec<Sample> = Vec::with_capacity(config.get_samples_count());
    let mut buffer: [u8; 4] = [0u8; 4];
    const SCALE: f32 = 1.0 / 32768.0;
    while reader.read_exact(&mut buffer).is_ok() {
        let re: f32 = i16::from_le_bytes(buffer[0..2].try_into().unwrap()) as f32;
        let im: f32 = i16::from_le_bytes(buffer[2..4].try_into().unwrap()) as f32;

        samples.push(Sample::new(re * SCALE, im * SCALE));
    }

    Ok(samples)
}
