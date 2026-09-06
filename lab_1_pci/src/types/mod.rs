use num_complex::Complex32;

pub mod config;

pub type Sample = Complex32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Subframe {
    Zero,
    Five,
}
