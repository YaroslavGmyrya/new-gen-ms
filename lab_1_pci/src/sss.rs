use crate::types::Sample;
use crate::types::Subframe;

pub struct Sss;

impl Sss {
    pub fn generate(n_id_1: u32, n_id_2: u32, subframe: Subframe) -> Vec<Sample> {
        assert!(n_id_1 <= 167, "N_ID_1 must be in 0..=167");
        assert!(n_id_2 <= 2, "N_ID_2 must be in 0..=2");

        let (m0, m1) = Self::compute_shifts(n_id_1);

        let s_tilde = Self::generate_s_tilde();
        let c_tilde = Self::generate_c_tilde();
        let z_tilde = Self::generate_z_tilde();

        let c0 = Self::cyclic_shift(&c_tilde, n_id_2);
        let c1 = Self::cyclic_shift(&c_tilde, (n_id_2 + 3) % 31);
        let z1 = Self::cyclic_shift(&z_tilde, m0 % 8);

        let (s_even, s_odd) = match subframe {
            Subframe::Zero => (
                Self::cyclic_shift(&s_tilde, m0), // s0
                Self::cyclic_shift(&s_tilde, m1), // s1
            ),
            Subframe::Five => (
                Self::cyclic_shift(&s_tilde, m1), // s1
                Self::cyclic_shift(&s_tilde, m0), // s0
            ),
        };

        let d_even: Vec<i8> = s_even.iter().zip(c0.iter()).map(|(&a, &b)| a * b).collect();

        let d_odd: Vec<i8> = s_odd
            .iter()
            .zip(c1.iter())
            .zip(z1.iter())
            .map(|((&a, &b), &c)| a * b * c)
            .collect();

        let mut d_bipolar = Vec::with_capacity(62);
        for n in 0..31 {
            d_bipolar.push(d_even[n]);
            d_bipolar.push(d_odd[n]);
        }

        Self::to_complex(&d_bipolar)
    }

    fn compute_shifts(n_id_1: u32) -> (u32, u32) {
        let q_prime = n_id_1 / 30;
        let q = (n_id_1 + q_prime * (q_prime + 1) / 2) / 30;
        let m_prime = n_id_1 + q * (q + 1) / 2;

        let m0 = m_prime % 31;
        let m1 = (m0 + m_prime / 31 + 1) % 31;

        (m0, m1)
    }

    fn generate_s_tilde() -> Vec<i8> {
        let x = Self::generate_m_sequence(2);
        Self::to_bipolar(&x)
    }

    fn generate_c_tilde() -> Vec<i8> {
        let x = Self::generate_m_sequence(3);
        Self::to_bipolar(&x)
    }

    fn generate_z_tilde() -> Vec<i8> {
        let mut x = vec![0u8; 31];
        x[4] = 1;
        for i in 0..26 {
            x[i + 5] = (x[i + 4] + x[i + 2] + x[i + 1] + x[i]) % 2;
        }
        Self::to_bipolar(&x)
    }

    fn generate_m_sequence(tap: usize) -> Vec<u8> {
        let mut x = vec![0u8; 31];
        x[4] = 1;

        for i in 0..26 {
            x[i + 5] = (x[i + tap] + x[i]) % 2;
        }

        x
    }

    fn to_bipolar(x: &[u8]) -> Vec<i8> {
        x.iter().map(|&v| 1 - 2 * v as i8).collect()
    }

    fn to_complex(x: &[i8]) -> Vec<Sample> {
        x.iter().map(|&v| Sample::new(v as f32, 0.0)).collect()
    }

    fn cyclic_shift(seq: &[i8], shift: u32) -> Vec<i8> {
        let len = seq.len();
        (0..len).map(|n| seq[(n + shift as usize) % len]).collect()
    }
}
