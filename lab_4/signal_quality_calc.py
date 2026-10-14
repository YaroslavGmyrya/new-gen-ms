import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from itertools import batched

def generate_zc(root):
    sequence = []

    for n in range(0, 31):
        phase = -np.pi * root * n * (n + 1) / 63
        value = np.exp(1j * phase)
        sequence.append(value)

    for n in range(31, 62):
        phase = -np.pi * root * (n + 1) * (n + 2) / 63
        value = np.exp(1j * phase)
        sequence.append(value)

    return sequence


def map_to_center(sequence, fft_size):
    if fft_size < 64:
        raise ValueError("fft_size must be at least 64")

    grid = np.zeros(int(fft_size), dtype=np.complex64)

    for i in range(31):
        negative_index = fft_size - 31 + i
        grid[negative_index] = sequence[i]

    for i in range(31):
        positive_index = 1 + i
        grid[positive_index] = sequence[31 + i]

    return grid


def get_pss_symbol_index(cp_type):
    if cp_type == "normal":
        return 6
    if cp_type == "extended":
        return 5


def get_cp_length(fft_size, cp_type, symbol_index):
    if cp_type == "extended":
        base_length = 512
    elif cp_type == "normal":
        if symbol_index % 7 == 0:
            base_length = 160
        else:
            base_length = 144

    cp_length = base_length * fft_size // 2048
    return cp_length



def run_ifft(grid, fft_size):
    return np.fft.ifft(grid, fft_size)



def add_cyclic_prefix(symbol, cp_length):
    prefix = symbol[len(symbol) - cp_length:]
    return np.concatenate((prefix, symbol))


def generate_pss(root, fft_size, cp_type):
    sequence = generate_zc(root)
    grid = map_to_center(sequence, fft_size)
    useful_symbol = run_ifft(grid, fft_size)

    symbol_index = get_pss_symbol_index(cp_type)
    cp_length = get_cp_length(fft_size, cp_type, symbol_index)
    full_symbol = add_cyclic_prefix(useful_symbol, cp_length)

    return full_symbol, useful_symbol



def normalize_samples(samples):
    samples = samples.astype(np.complex64)
    samples = samples - np.mean(samples)

    rms = np.sqrt(np.mean(np.abs(samples) ** 2))
    if rms == 0:
        raise ValueError("samples contain only zeros")

    return (samples / rms).astype(np.complex64)

def norm_corr(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    
    y_centered = y - np.mean(y)
    y_energy = np.sum(y_centered**2)
    
    corr = np.correlate(x, y_centered, mode='valid')
    
    ones = np.ones_like(y)
    x_sq_sum = np.convolve(x**2, ones, mode='valid')
    x_sum = np.convolve(x, ones, mode='valid')
    
    x_energy = x_sq_sum - (x_sum**2) / len(y)
    
    x_energy = np.maximum(x_energy, 0) 
    
    norm_factor = np.sqrt(x_energy * y_energy)
    
    return np.divide(corr, norm_factor, out=np.zeros_like(corr), where=norm_factor!=0)

def get_ofdm_symbols(frame, fft_size, cp_type='normal'):
    symbols = []
    pos = 0
    
    total_symbols = 140 if cp_type == 'normal' else 120
        
    for i in range(total_symbols):
        cp_len = get_cp_length(fft_size, cp_type, i)
            
        symbol_len = cp_len + fft_size
        
        symbol = frame[pos : pos + symbol_len]
        symbols.append(symbol)
        
        pos += symbol_len
        
    return symbols

def delete_cp(symbols, fft_size, cp_type):
    result = []
    for sym_index, sym in enumerate(symbols):
        cp_len = get_cp_length(fft_size, cp_type, sym_index)
        result.append(sym[cp_len:])

    return result

def fft(symbols, fft_size):
    result = []
    
    for symbol in symbols:
        result.append(np.fft.fftshift(np.fft.fft(symbol, fft_size)))
        
    return result

def get_useful_re(symbols, fft_size, num_rb=6):
    num_re = num_rb * 12
    half_re = num_re // 2
    center_idx = fft_size // 2

    result = []
    for symbol in symbols:
        lower = symbol[center_idx - half_re : center_idx]
        upper = symbol[center_idx + 1 : center_idx + 1 + half_re]
        result.append(np.concatenate((lower, upper)))

    return result


def extract_rs_signals(useful_re_matrix, cell_id=0, start_sym_index=0):
    v_shift = cell_id % 6
    
    useful_re_matrix = np.asarray(useful_re_matrix)
    num_symbols, num_re = useful_re_matrix.shape
    
    data_matrix = np.zeros((num_symbols, num_re), dtype=complex)
    rs_matrix = np.zeros((num_symbols, num_re), dtype=complex)
    
    for i in range(num_symbols):
        global_idx = start_sym_index + i
        idx_in_slot = global_idx % 7
        
        current_symbol = useful_re_matrix[i, :]
        
        if idx_in_slot == 0:
            rs_indices = np.arange(v_shift, num_re, 6)
        elif idx_in_slot == 4:
            v_shift_4 = (v_shift + 3) % 6
            rs_indices = np.arange(v_shift_4, num_re, 6)
        else:
            data_matrix[i, :] = current_symbol
            continue
            
        is_rs = np.zeros(num_re, dtype=bool)
        is_rs[rs_indices] = True
        
        rs_matrix[i, is_rs] = current_symbol[is_rs]
        data_matrix[i, ~is_rs] = current_symbol[~is_rs]
        
    return data_matrix, rs_matrix



PRB_TO_FFT_SIZE = {
    6: 128,
    15: 256,
    25: 512,
    50: 1024,
    75: 1536,
    100: 2048,
}

ROOTS = [25, 29, 34]
SAMPLES_COUNT = int(4e6)
PRB = 6
SAMPLE_RATE = 1.92e6

FFT_SIZE = PRB_TO_FFT_SIZE[PRB]
CP_TYPE = "normal"

FILE_PATH = "lte_pss_sss_pbch_iq_s16le.pcm"

raw_data = np.fromfile(FILE_PATH, dtype=np.int16)

iq_matrix = raw_data.reshape(-1, 2)

I = iq_matrix[:, 0]
Q = iq_matrix[:, 1]
iq_signal = I + 1j * Q

iq_signal = normalize_samples(iq_signal)

plt.figure(figsize=(12, 5))

dt = 1/SAMPLE_RATE

for root in ROOTS:
    full_symbol, _ = generate_pss(root, FFT_SIZE, CP_TYPE)

    correlation = norm_corr(iq_signal, full_symbol)
    
    plt.plot(np.arange(len(correlation)) * dt, correlation, label="root = " + str(root))
    
    peaks, properties = find_peaks(
        correlation, 
        height=0.8, 
        distance=FFT_SIZE
    )
    
plt.xlabel("time")
plt.ylabel("correlation")
plt.title("PSS correlation")
plt.legend()
plt.grid(True)
plt.show()
    
symbols = get_ofdm_symbols(iq_signal, FFT_SIZE, "normal")
symbols_wo_cp = delete_cp(symbols, FFT_SIZE, CP_TYPE)
symbols_in_spec = fft(symbols_wo_cp, FFT_SIZE)
useful_symbols = get_useful_re(symbols_in_spec, FFT_SIZE, PRB)
useful_symbols, rs = extract_rs_signals(useful_symbols, 67, 0)

print(rs[4])

plt.scatter(np.real(useful_symbols[4]), np.imag(useful_symbols[4]))
plt.show()

