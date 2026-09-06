#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DuplexMode {
    Fdd,
    Tdd,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
#[allow(dead_code)]

pub enum Modulation {
    Bpsk,
    Qpsk,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum BW {
    Rb6 = 6,
    Rb15 = 15,
    Rb25 = 25,
    Rb50 = 50,
    Rb75 = 75,
    Rb100 = 100,
}

impl BW {
    pub fn prb_count(&self) -> usize {
        *self as usize
    }

    pub fn fft_size(&self) -> usize {
        match self {
            BW::Rb6 => 128,
            BW::Rb15 => 256,
            BW::Rb25 => 512,
            BW::Rb50 => 1024,
            BW::Rb75 => 1536,
            BW::Rb100 => 2048,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Scs {
    Khz15 = 15,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum CyclicPrefixType {
    #[default]
    Normal,
    Extended,
}

impl CyclicPrefixType {
    pub fn size(&self) -> i32 {
        match self {
            CyclicPrefixType::Normal => 9,
            CyclicPrefixType::Extended => 32,
        }
    }
}

#[derive(Debug, Clone, serde::Deserialize)]
#[allow(dead_code)]
pub struct Config {
    pub duplex_mode: DuplexMode,
    pub dl_bw: BW,
    pub scs_khz: Scs,
    pub fs: f32,
    pub cp_type: CyclicPrefixType,
    pub record_duration_ms: u32,
}

impl Config {
    pub fn ms_per_sample(&self) -> f32 {
        1.0 / (self.fs * 1e4)
    }
}
