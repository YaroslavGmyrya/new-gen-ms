use crate::fft::Fft;
use crate::ofdm_symbol;
use crate::types::Sample;
use crate::types::config::*;
pub struct OfdmSymbol;

const RE_PER_PRB: usize = 12;
const PBCH_SYMBOL1_MASK: [bool; 72] = [
    true, false, true, true, false, true, true, false, true, true, false, true, true, false, true,
    true, false, true, true, false, true, true, false, true, true, false, true, true, false, true,
    true, false, true, true, false, true, true, false, true, true, false, true, true, false, true,
    true, false, true, true, false, true, true, false, true, true, false, true, true, false, true,
    true, false, true, true, false, true, true, false, true, true, false, true,
];

const PBCH_SYMBOL2_MASK: [bool; 72] = PBCH_SYMBOL1_MASK;

const PBCH_SYMBOL3_MASK: [bool; 72] = [true; 72];
const PBCH_SYMBOL4_MASK: [bool; 72] = [true; 72];

const PBCH_MASKS: [[bool; 72]; 4] = [
    PBCH_SYMBOL1_MASK,
    PBCH_SYMBOL2_MASK,
    PBCH_SYMBOL3_MASK,
    PBCH_SYMBOL4_MASK,
];

#[inline]
fn demod_sample(s: Sample) -> (u8, u8) {
    let bit_i: u8 = if s.re >= 0.0 { 0 } else { 1 };
    let bit_q: u8 = if s.im >= 0.0 { 0 } else { 1 };
    (bit_i, bit_q)
}

pub fn qpsk_demod(ofdm_symbols: Vec<Vec<Sample>>) -> Vec<u8> {
    // Заранее резервируем память: 2 бита на каждый отсчёт.
    let total_samples: usize = ofdm_symbols.iter().map(|sym| sym.len()).sum();
    let mut bits = Vec::with_capacity(total_samples * 2);

    for ofdm_symbol in ofdm_symbols {
        for sample in ofdm_symbol {
            let (bit_i, bit_q) = demod_sample(sample);
            bits.push(bit_i);
            bits.push(bit_q);
        }
    }

    bits
}

impl OfdmSymbol {
    pub fn add_cyclic_prefix(
        data: Vec<Sample>,
        cyclic_prefix_type: CyclicPrefixType,
    ) -> Vec<Sample> {
        let cyclic_prefix_size = cyclic_prefix_type.size() as usize;

        let mut result: Vec<Sample> = Vec::with_capacity(data.len() + cyclic_prefix_size as usize);

        let cyclic_prefix = &data[data.len() - cyclic_prefix_size..data.len()];

        result.extend_from_slice(cyclic_prefix);
        result.extend(data);

        result
    }

    fn chunk_by_fft_size(
        samples: Vec<Sample>,
        bw: BW,
        cyclic_prefix_type: CyclicPrefixType,
    ) -> Vec<Vec<Sample>> {
        let fft_size = bw.fft_size();
        let cp_size = cyclic_prefix_type.size() as usize;
        assert!(
            samples.len() % (fft_size + cp_size) == 0,
            "Samples size must be multiple fft_size",
        );

        samples
            .chunks_exact(fft_size + cp_size)
            .map(|chunk| chunk.to_vec()) // Превращаем &[T] в Vec<T>
            .collect()
    }

    pub fn del_cyclic_prefix(
        samples: Vec<Vec<Sample>>,
        cyclic_prefix_type: CyclicPrefixType,
        bw: BW,
    ) -> Vec<Vec<Sample>> {
        let fft_size: usize = bw.fft_size();
        let cp_size: usize = cyclic_prefix_type.size() as usize;

        assert!(
            samples[0].len() % (fft_size + cyclic_prefix_type.size() as usize) == 0,
            "Samples size must be multiple fft_size"
        );

        samples
            .iter()
            .map(|symbol| symbol[cp_size..].to_vec())
            .collect()
    }

    pub fn get_central_re(samples: Vec<Vec<Sample>>, bw: BW) -> Vec<Vec<Sample>> {
        let usable_re_count = bw.prb_count() * RE_PER_PRB; // всегда чётное (RE_PER_PRB = 12)
        let fft_size = bw.fft_size();

        // Нужно usable_re_count полезных RE + 1 DC-поднесущая ровно посередине,
        // которую нужно выкинуть.
        let window = usable_re_count + 1;
        let start_slice = (fft_size - window) / 2;
        let dc_offset = window / 2; // индекс DC внутри вырезанного окна

        samples
            .iter()
            .map(|symbol| {
                let mut central = symbol[start_slice..start_slice + window].to_vec();
                central.remove(dc_offset);
                central
            })
            .collect()
    }

    pub fn samples_to_symbols(
        samples: Vec<Sample>,
        bw: BW,
        cyclic_prefix_type: CyclicPrefixType,
    ) -> (Vec<u8>, Vec<Vec<Sample>>) {
        let mut fft = Fft::new();
        let fft_size = bw.fft_size();

        // 1. Get chunks by fft size
        let mut result = Self::chunk_by_fft_size(samples, bw, cyclic_prefix_type);

        // 2. Delete cyclic_prefix
        result = Self::del_cyclic_prefix(result, cyclic_prefix_type, bw);

        // 3. FFT
        result = result
            .into_iter()
            .map(|symbol| fft.fft(symbol, fft_size))
            .collect();

        // 4. Get N central RE
        result = Self::get_central_re(result, bw);

        // 5. Filter only info RE
        result = result
            .into_iter()
            .zip(PBCH_MASKS.iter())
            .map(|(symbol, mask)| {
                assert_eq!(
                    symbol.len(),
                    mask.len(),
                    "Symbol length must match mask length (72 REs)"
                );

                symbol
                    .into_iter()
                    .zip(mask.iter())
                    .filter_map(|(re, &keep)| keep.then_some(re))
                    .collect()
            })
            .collect::<Vec<Vec<_>>>();

        println!(
            "SYMBOLS COUNT AFTER:{} {} {} {}",
            result[0].len(),
            result[1].len(),
            result[2].len(),
            result[3].len()
        );

        // 5. QPSK demodulation
        (qpsk_demod(result.clone()), result)
    }
}
