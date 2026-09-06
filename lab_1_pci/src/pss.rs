use crate::types::config::BW;
use num_complex::Complex32;
use std::f32::consts::PI;

type Sample = Complex32;

const ZC_LEN: usize = 62;
const N_ZC: f32 = 63.0;
const N_SC_RB: usize = 12;

pub struct Pss;

impl Pss {
    pub fn generate_zc(root: u8) -> Vec<Sample> {
        let u = root as f32;
        let mut seq = Vec::with_capacity(ZC_LEN);

        for n in 0..=30u32 {
            let n_f = n as f32;
            let phase = -PI * u * n_f * (n_f + 1.0) / N_ZC;
            seq.push(Sample::new(phase.cos(), phase.sin()));
        }

        for n in 31..=61u32 {
            let n_f = n as f32;
            let phase = -PI * u * (n_f + 1.0) * (n_f + 2.0) / N_ZC;
            seq.push(Sample::new(phase.cos(), phase.sin()));
        }

        seq
    }

    pub fn map_zc_to_ofdm_symbol(rb_count: BW, zc_seq: &[Sample]) -> Vec<Sample> {
        assert_eq!(
            zc_seq.len(),
            ZC_LEN,
            "Invalid ZC seq size! ZC seq must be have len=62",
        );

        let n_sc_total = rb_count.prb_count() * N_SC_RB;
        assert!(
            n_sc_total >= ZC_LEN,
            "rb_count слишком мал: не хватает поднесущих для PSS"
        );

        let mut symbol = vec![Sample::new(0.0, 0.0); n_sc_total];

        let center = n_sc_total / 2;
        let k_start = center as isize - 31;

        for (n, &d) in zc_seq.iter().enumerate() {
            let k = k_start + n as isize;
            symbol[k as usize] = d;
        }

        symbol
    }
}
