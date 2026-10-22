import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from itertools import batched

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

def path_loss(f_mhz, d_km, hb=30.0, hm=1.5, area="small"):
    lf = np.log10(f_mhz)
    lhb = np.log10(hb)

    if area == "metro":
        if f_mhz <= 200:
            a = 8.29 * np.log10(1.54 * hm) ** 2 - 1.1
        else:
            a = 3.2 * np.log10(11.75 * hm) ** 2 - 4.97
    else:
        a = (1.1 * lf - 0.7) * hm - (1.56 * lf - 0.8)

    if area == "suburban":
        C = -2 * np.log10(f_mhz / 28) ** 2 - 5.4
    elif area == "rural":
        C = -4.78 * lf ** 2 + 18.33 * lf - 40.98
    elif area == "metro" and f_mhz > 1500:
        C = 3.0
    else:
        C = 0.0

    if f_mhz <= 1500:
        A = 69.55 + 26.16 * lf - 13.82 * lhb - a
    else:
        A = 46.3 + 33.9 * lf - 13.82 * lhb - a

    B = 44.9 - 6.55 * lhb
    
    return A + B * np.log10(d_km) + C

def add_AWGN(samples, SINR):
    p_signal = np.mean(np.abs(samples) ** 2)
    p_noise = p_signal / 10 ** (SINR / 10)
    noise = np.sqrt(p_noise / 2) * (np.random.randn(len(samples)) + 1j * np.random.randn(len(samples)))
    return samples + noise


def calc_RSRP(real_rs):
    real_rs = batched(real_rs, 12)
    
    result=[]
    
    for batch in real_rs:
        power_counter = 0
        for rs in batch:
            power_counter += np.abs(rs)
        
        avg = power_counter / len(batch)
        db = 10*np.log10(avg)
        result.append(db)
        
    return result

def calc_RSSI(samples):
    real_rs = batched(samples, 72)
    
    result=[]
    
    for i,batch in enumerate(real_rs):
        power_counter = 0
        
        if i % 7 != 0 and i % 4 != 0:
            continue
        
        for sample in batch:
            power_counter += np.abs(sample)
        
        avg = power_counter / len(batch)
        db = 10*np.log10(avg)
        result.append(db)
        
    return result
        
def add_cp(samples, fft_size, cp_type):
    new_symbols = []
    for i, symbol in enumerate(samples):
        # ИСПРАВЛЕНИЕ: гарантируем, что работаем с массивом NumPy
        symbol = np.asarray(symbol) 
        
        cp_len = get_cp_length(fft_size, cp_type, i)
        
        # Теперь срез и конкатенация выполняются средствами NumPy корректно
        cp = symbol[-cp_len:] 
        symbol_with_cp = np.concatenate((cp, symbol))
        
        new_symbols.append(symbol_with_cp)
            
    return new_symbols
            
def map_to_grid(symbols, fft_size, num_rb=6):
    half_re = num_rb * 12 // 2
    center_idx = fft_size // 2

    result = []
    for sym in symbols:
        sym = np.asarray(sym)
        grid = np.zeros(fft_size, dtype=np.complex64)
        grid[center_idx - half_re : center_idx] = sym[:half_re]            # нижняя половина
        grid[center_idx + 1 : center_idx + 1 + half_re] = sym[half_re:]    # верхняя половина (DC пропущен)
        result.append(grid)
    return result


def ifft(grids, fft_size):
    return [np.fft.ifft(np.fft.ifftshift(g), fft_size) for g in grids]


import numpy as np

# Параметры (1.4 МГц, CP normal)
N_RB      = 6
N_SC_RB   = 12
N_USED    = N_RB * N_SC_RB          # 72 полезных поднесущих
N_FFT     = 128
FS        = 1.92e6
N_SLOTS   = 20
SYM_SLOT  = 7                        # normal CP
N_SYM     = N_SLOTS * SYM_SLOT       # 140 символов на кадр
CP_FIRST  = 10                       # первый символ слота
CP_OTHER  = 9                        # остальные 6
FRAME_LEN = 19200


def load_frame(path):
    """float32, I/Q вперемешку -> complex64"""
    raw = np.fromfile(path, dtype=np.float32)
    x = raw[0::2] + 1j * raw[1::2]
    assert len(x) == FRAME_LEN, f"ожидалось {FRAME_LEN} отсчётов, получено {len(x)}"
    return x.astype(np.complex64)


def extract_useful_re(x):
    """
    x: complex, 19200 отсчётов.
    Возвращает grid[sym, sc]: shape (140, 72)
    sc = 0..71 -> частоты от самой нижней к самой верхней (DC пропущен).
    """
    grid = np.empty((N_SYM, N_USED), dtype=np.complex64)

    # индексы бинов FFT: -36..-1 -> 92..127, затем +1..+36 -> 1..36
    bins = np.r_[N_FFT - N_USED // 2 : N_FFT, 1 : N_USED // 2 + 1]

    pos = 0
    for sym in range(N_SYM):
        cp = CP_FIRST if sym % SYM_SLOT == 0 else CP_OTHER
        pos += cp                                   # пропускаем CP
        td = x[pos : pos + N_FFT]
        pos += N_FFT

        fd = np.fft.fft(td)
        grid[sym] = fd[bins]

    assert pos == FRAME_LEN 
    return grid



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

FILE_PATH = "lte_frame_time.bin"

gain_db = 1

null_pos = np.fromfile("lte_null_pos.bin", dtype=np.int32)
null_pos = np.asarray(null_pos)

rs_pos = np.fromfile("lte_rs_pos.bin", dtype=np.int32)
samples = np.fromfile("lte_frame_fc32.bin", dtype=np.complex64)
samples = samples.astype(np.complex256)
samples = samples = extract_useful_re(samples)

samples = [item for sample in samples for item in sample]
samples = np.array(samples)

print(*samples)