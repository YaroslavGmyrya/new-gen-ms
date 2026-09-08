use crate::correlator::Correlator;
use crate::fft::Fft;
use crate::ofdm_symbol::OfdmSymbol;
use crate::types::Sample;
use crate::types::config::*;
use plotly::common::Mode;
use plotly::common::Title;
use plotly::layout::{Axis, Layout, LayoutGrid};
use plotly::{Plot, Scatter};
use pss::Pss;
use sss::Sss;
mod config_parser;
mod correlator;
mod fft;
mod ofdm_symbol;
mod pss;
mod samples_reader;
mod sss;
mod types;

const CONFIG_FILE_PATH: &str = "Config.toml";
const SAMPLES_FILE_PATH: &str = "lte_pss_sss_pbch_iq_s16le.pcm";
const COUNT_OF_ZC_ROOTS: usize = 3;
const ZC_ROOTS: [u8; COUNT_OF_ZC_ROOTS] = [25, 29, 34];

const NC: usize = 1600;

pub fn generate_gold_sequence(c_init: u32, length: usize) -> Vec<u8> {
    const NC: usize = 1600;
    let total_len = length + NC;

    let mut x1 = vec![0u8; total_len];
    x1[0] = 1;

    let mut x2 = vec![0u8; total_len];
    for i in 0..31 {
        x2[i] = ((c_init >> i) & 1) as u8;
    }

    for n in 0..(total_len - 31) {
        x1[n + 31] = (x1[n + 3] + x1[n]) % 2;
        x2[n + 31] = (x2[n + 3] + x2[n + 2] + x2[n + 1] + x2[n]) % 2;
    }

    let mut c = vec![0u8; length];
    for n in 0..length {
        c[n] = (x1[n + NC] + x2[n + NC]) % 2;
    }

    c
}

fn descramble(bits: &[u8], c_init: u32) -> Vec<u8> {
    let c = generate_gold_sequence(c_init, bits.len());
    bits.iter().zip(c.iter()).map(|(&b, &c)| b ^ c).collect()
}

fn main() {
    // 0. Plot grid setting
    let layout = Layout::new()
        .grid(
            LayoutGrid::new()
                .rows(5)
                .columns(1)
                .pattern(plotly::layout::GridPattern::Independent),
        )
        .title(Title::new().text("Plots"))
        .y_axis(Axis::new().title(Title::new().text("Signal")))
        .y_axis2(Axis::new().title(Title::new().text("Zadov-Chu")))
        .y_axis3(Axis::new().title(Title::new().text("PSS correlation")))
        .y_axis4(Axis::new().title(Title::new().text("CP correlation")))
        .y_axis5(Axis::new().title(Title::new().text("PBCH Constellation")))
        .width(1600)
        .height(1500);

    let mut plots = Plot::new();
    plots.set_layout(layout);

    // 1. Read toml config
    let config: Config = match Config::from_file(CONFIG_FILE_PATH) {
        Ok(cfg) => {
            println!("Programm run with config:\n{:#?}", cfg);
            cfg
        }
        Err(err) => panic!("{}", err),
    };

    // 2. Read samples
    let samples: Vec<Sample> = match samples_reader::pcm_reader(SAMPLES_FILE_PATH, &config) {
        Ok(samples) => samples,
        Err(err) => {
            eprintln!(
                "Ошибка: Не удалось загрузить семплы из '{}'.",
                SAMPLES_FILE_PATH
            );
            eprintln!("Детали: {}", err);

            std::process::exit(1);
        }
    };

    // 3. Plot signal
    let timeline: Vec<f32> = config.get_timeline();

    // Real part
    let real_curve = Scatter::new(
        timeline.clone(),
        samples.iter().map(|sample| sample.re).collect::<Vec<_>>(),
    )
    .name("Real")
    .x_axis("x1")
    .y_axis("y1");

    // Imag part
    let image_curve = Scatter::new(
        timeline.clone(),
        samples.iter().map(|sample| sample.im).collect::<Vec<_>>(),
    )
    .name("Image")
    .x_axis("x1")
    .y_axis("y1");

    plots.add_trace(real_curve);
    plots.add_trace(image_curve);

    // 4. Generate ZC sequences
    let zc_seqs: Vec<Vec<Sample>> = ZC_ROOTS
        .iter()
        .map(|root| Pss::generate_zc(*root))
        .collect();

    // 5. Plot ZC seqs
    for (i, zc_seq) in zc_seqs.iter().enumerate() {
        let x_data: Vec<f32> = zc_seq.iter().map(|sample| sample.re).collect();

        let y_data: Vec<f32> = zc_seq.iter().map(|sample| sample.im).collect();

        let trace = Scatter::new(x_data, y_data)
            .mode(Mode::Markers)
            .name(format!("Root = {}", ZC_ROOTS[i]))
            .x_axis("x2")
            .y_axis("y2");

        plots.add_trace(trace);
    }

    // 6. Create PSS
    let mut fft: Fft = Fft::new();

    let pss_refs: Vec<Vec<Sample>> = zc_seqs
        .iter()
        .map(|zc_seq| {
            OfdmSymbol::add_cyclic_prefix(
                fft.ifft(
                    Pss::map_zc_to_ofdm_symbol(config.dl_bw, zc_seq),
                    config.dl_bw.fft_size(),
                ),
                config.cp_type,
            )
        })
        .collect();

    // 7. Calculate correlation
    let pss_correlations: Vec<Vec<f32>> = pss_refs
        .iter()
        .map(|pss_ref| Correlator::correlation(samples.clone(), pss_ref.clone()))
        .collect();

    for (i, pss_corr) in pss_correlations.iter().enumerate() {
        plots.add_trace(
            Scatter::new(timeline.clone(), pss_corr.clone())
                .name(format!("Root = {}", ZC_ROOTS[i]))
                .x_axis("x3")
                .y_axis("y3"),
        );
    }

    // 8. Find peaks
    println!("\nFirst PSS peasks:\n");

    let mut pss_id: u8 = 0;
    let mut start_pss_index: usize = 0;
    let mut tmp_value: f32 = 0.0;

    for (i, correlation) in pss_correlations.into_iter().enumerate() {
        let peak = Correlator::find_peak(correlation);

        if peak.1 > tmp_value {
            pss_id = i as u8;
            start_pss_index = peak.0;
            tmp_value = peak.1;
        }

        println!("Root: {}", ZC_ROOTS[i]);
        println!("N_ID: {}", i);
        println!("Value: {}", peak.1);
        println!("Index: {}", peak.0);
        println!("Time: {}ms\n", (peak.0 as f32 * config.ms_per_sample()));
    }

    println!("Best N_ID: {}", pss_id);

    // 9. CP correlation
    let cp_correlation: Vec<f32> = Correlator::cp_correlation(
        samples.clone(),
        config.dl_bw.fft_size(),
        (config.cp_type.size() + 1) as usize,
    );

    // 10. Plot CP correlation
    let curve = Scatter::new(
        (0..cp_correlation.len())
            .map(|num| num as f32 * config.get_time_step_ms())
            .collect(),
        cp_correlation,
    )
    .x_axis("x4")
    .y_axis("y4");

    plots.add_trace(curve);

    // 11. Find SSS
    let end_sss_index = start_pss_index;
    let start_sss_index = end_sss_index - config.dl_bw.fft_size();

    let sss_samples: Vec<Sample> = fft.fft(
        samples[start_sss_index..end_sss_index].to_vec(),
        config.dl_bw.fft_size(),
    );

    let mut sss_symbol = Vec::with_capacity(72);

    sss_symbol.extend(sss_samples[28 + 5..64].iter().cloned());
    sss_symbol.extend(sss_samples[65..101 - 5].iter().cloned());

    // 12. Generate SSS
    let mut sss_id = 0;
    let mut tmp = 0.0f32;

    for n_id_1 in 0..168u32 {
        for subframe in [types::Subframe::Zero, types::Subframe::Five] {
            let tmp_sss = Sss::generate(n_id_1, pss_id as u32, subframe);
            let sss_peak =
                Correlator::find_peak(Correlator::correlation(sss_symbol.clone(), tmp_sss.clone()));

            if sss_peak.1 > tmp {
                tmp = sss_peak.1;
                sss_id = n_id_1;
            }
        }
    }

    println!("{}, {}", sss_id, tmp);

    // 13. Find PBCH range
    let start_pbch = start_pss_index + config.cp_type.size() as usize + config.dl_bw.fft_size() + 1;
    let end_pbch: usize =
        start_pbch + 4 * (config.dl_bw.fft_size() + config.cp_type.size() as usize);

    let pbch_samples = samples[start_pbch..end_pbch].to_vec();
    println!("PBCH SAMPLES SIZE: {}", pbch_samples.len());

    let (pbch_bits, pbch_re) =
        OfdmSymbol::samples_to_symbols(pbch_samples, config.dl_bw, config.cp_type);

    println!(
        "PBCH BITS: {}",
        pbch_re.iter().flatten().collect::<Vec<_>>().len()
    );

    // 14. Plot PBCH constellation

    let pbch_constellation = Scatter::new(
        pbch_re.iter().flatten().map(|sample| sample.re).collect(),
        pbch_re.iter().flatten().map(|sample| sample.im).collect(),
    )
    .mode(Mode::Markers)
    .x_axis("x5")
    .y_axis("y5");

    plots.add_trace(pbch_constellation);

    plots.show();
}
