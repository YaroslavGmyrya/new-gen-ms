import numpy as np
import zmq
import matplotlib.pyplot as plt

ENB_TX = "tcp://localhost:2101"
UE_RX_BIND = "tcp://*:2102"

N_RB = 6
FFT_SIZE = 128
MAX_RB = 110

CP0 = 160 * FFT_SIZE // 2048
CP = 144 * FFT_SIZE // 2048
SLOT_LEN = FFT_SIZE * 15 // 2
SUBFRAME_LEN = 2 * SLOT_LEN
FRAME_LEN = 10 * SUBFRAME_LEN
THRESHOLD = 0.5
SSS_THRESHOLD = 0.5
RS_SYMBOLS = (0, 4)

MAX_POINTS = 300
PLOT_EVERY = 10

PATH_LOSS_ENABLED = True
NOISE_ENABLED = True
FREQ_MHZ = 900.0
BS_HEIGHT = 50.0
UE_HEIGHT = 1.5
DIST_KM = 2.0
ENVIRONMENT = "urban"
TX_POWER_DBM = 43.0
NOISE_FIGURE_DB = 7.0
SAMPLE_RATE = FFT_SIZE * 15000
UE_AGC = True

SYM_USEFUL = []
for l in range(7):
    if l == 0:
        SYM_USEFUL.append(CP0)
    else:
        SYM_USEFUL.append(FFT_SIZE + CP0 + (l - 1) * (FFT_SIZE + CP) + CP)

ROOTS = [25, 29, 34]
PSS_REFS = {}
PSS_ZC = {}
SSS_TABLE = {}
RS_CACHE = {}

state = {
    "offset": 0,
    "synced": False,
    "pci": 0,
    "next_slot": 0,
    "slot_num": 0,
    "buf": np.zeros(0, dtype=np.complex64),
    "buf_start": 0,
    "rs": {},
    "match": [],
    "power": [],
    "rssi": [],
    "sig": [],
    "noise": [],
    "frames": 0,
}

HISTORY = {"rsrp": [], "rssi": [], "rsrq": [], "sinr": []}
NAMES = [("rsrp", "RSRP, dB"), ("rssi", "RSSI, dB"), ("rsrq", "RSRQ, dB"), ("sinr", "SINR, dB")]
LINES = {}

plt.ion()
fig, axes = plt.subplots(4, 1, sharex=True)
for ax, (key, title) in zip(axes, NAMES):
    line, = ax.plot([], [])
    ax.set_ylabel(title)
    ax.grid(True)
    LINES[key] = (ax, line)
axes[-1].set_xlabel("Frame")
fig.tight_layout()


def okumura_hata(f_mhz, hb, hm, d_km, env):
    log_f = np.log10(f_mhz)
    log_hb = np.log10(hb)
    if env == "large_city":
        if f_mhz <= 300:
            a_hm = 8.29 * np.log10(1.54 * hm) ** 2 - 1.1
        else:
            a_hm = 3.2 * np.log10(11.75 * hm) ** 2 - 4.97
    else:
        a_hm = (1.1 * log_f - 0.7) * hm - (1.56 * log_f - 0.8)
    loss = 69.55 + 26.16 * log_f - 13.82 * log_hb - a_hm
    loss = loss + (44.9 - 6.55 * log_hb) * np.log10(d_km)
    if env == "suburban":
        loss = loss - 2 * np.log10(f_mhz / 28) ** 2 - 5.4
    elif env == "open":
        loss = loss - 4.78 * log_f ** 2 + 18.33 * log_f - 40.94
    return loss


PATH_LOSS_DB = okumura_hata(FREQ_MHZ, BS_HEIGHT, UE_HEIGHT, DIST_KM, ENVIRONMENT)
GAIN = 10 ** (-PATH_LOSS_DB / 20)
NOISE_DBM = -174 + 10 * np.log10(SAMPLE_RATE) + NOISE_FIGURE_DB
NOISE_REL = 10 ** ((NOISE_DBM - TX_POWER_DBM) / 10)

rng = np.random.default_rng()
tx_stat = {"sum": 0.0, "count": 0}

print(f"CHANNEL: path_loss={'on' if PATH_LOSS_ENABLED else 'off'} noise={'on' if NOISE_ENABLED else 'off'}")
if PATH_LOSS_ENABLED:
    print(f"PATH LOSS={PATH_LOSS_DB:.1f} dB")
if NOISE_ENABLED:
    loss = PATH_LOSS_DB if PATH_LOSS_ENABLED else 0.0
    print(f"NOISE={NOISE_DBM:.1f} dBm SNR={TX_POWER_DBM - loss - NOISE_DBM:.1f} dB")


def apply_channel(samples):
    if not PATH_LOSS_ENABLED and not NOISE_ENABLED:
        return samples
    out = samples
    if PATH_LOSS_ENABLED:
        out = out * GAIN
    if NOISE_ENABLED:
        tx_stat["sum"] += float(np.vdot(samples, samples).real)
        tx_stat["count"] += len(samples)
        tx_power = tx_stat["sum"] / tx_stat["count"]
        sigma = np.sqrt(tx_power * NOISE_REL / 2)
        noise = sigma * (rng.standard_normal(len(samples)) + 1j * rng.standard_normal(len(samples)))
        out = out + noise
    return out.astype(np.complex64)


def to_db(x):
    return 10 * np.log10(max(x, 1e-20))


def update_plot():
    end = state["frames"]
    for key in LINES:
        ax, line = LINES[key]
        y = HISTORY[key]
        x = list(range(end - len(y), end))
        line.set_data(x, y)
        ax.relim()
        ax.autoscale_view()
    fig.canvas.draw_idle()
    plt.pause(0.001)


def generate_zc(root):
    seq = []
    for n in range(62):
        if n < 31:
            k = n * (n + 1)
        else:
            k = (n + 1) * (n + 2)
        phase = -np.pi * root * k / 63
        seq.append(np.exp(1j * phase))
    return seq


def map_to_subcarriers(data, n_rb):
    n_sc = n_rb * 12
    grid = [0j] * n_sc
    start = n_sc // 2 - 31
    for n in range(62):
        grid[start + n] = data[n]
    return grid


def ifft(grid, fft_size):
    n_sc = len(grid)
    half = n_sc // 2
    spectrum = np.zeros(fft_size, dtype=complex)
    for i in range(half):
        spectrum[fft_size - half + i] = grid[i]
    for i in range(half):
        spectrum[1 + i] = grid[half + i]
    return np.fft.ifft(spectrum)


def fft_to_grid(td, n_rb):
    fft_size = len(td)
    spectrum = np.fft.fft(td)
    n_sc = n_rb * 12
    half = n_sc // 2
    grid = np.zeros(n_sc, dtype=complex)
    for i in range(half):
        grid[i] = spectrum[fft_size - half + i]
    for i in range(half):
        grid[half + i] = spectrum[1 + i]
    return grid


def fft_to_center(td, n_rb):
    grid = fft_to_grid(td, n_rb)
    start = n_rb * 6 - 31
    return grid[start:start + 62]


def norm_corr(samples, ref):
    m = len(ref)
    corr = np.correlate(samples, ref, mode="valid")
    power = np.abs(samples) ** 2
    csum = np.concatenate(([0.0], np.cumsum(power)))
    window_energy = csum[m:] - csum[:-m]
    ref_energy = np.sum(np.abs(ref) ** 2)
    norm = np.sqrt(window_energy * ref_energy)
    return np.abs(corr) / np.maximum(norm, 1e-12)


def gen_x(taps):
    x = [0, 0, 0, 0, 1]
    for i in range(26):
        v = 0
        for t in taps:
            v += x[i + t]
        x.append(v % 2)
    result = []
    for b in x:
        result.append(1 - 2 * b)
    return result


S_SEQ = gen_x([2, 0])
C_SEQ = gen_x([3, 0])
Z_SEQ = gen_x([4, 2, 1, 0])


def generate_sss(n_id_1, n_id_2, subframe):
    q_prime = n_id_1 // 30
    q = (n_id_1 + q_prime * (q_prime + 1) // 2) // 30
    m_prime = n_id_1 + q * (q + 1) // 2
    m0 = m_prime % 31
    m1 = (m0 + m_prime // 31 + 1) % 31
    d = [0] * 62
    for n in range(31):
        s0 = S_SEQ[(n + m0) % 31]
        s1 = S_SEQ[(n + m1) % 31]
        c0 = C_SEQ[(n + n_id_2) % 31]
        c1 = C_SEQ[(n + n_id_2 + 3) % 31]
        z0 = Z_SEQ[(n + m0 % 8) % 31]
        z1 = Z_SEQ[(n + m1 % 8) % 31]
        if subframe == 0:
            d[2 * n] = s0 * c0
            d[2 * n + 1] = s1 * c1 * z0
        else:
            d[2 * n] = s1 * c0
            d[2 * n + 1] = s0 * c1 * z1
    return d


def gold(c_init, length):
    n_total = length + 1600
    x1 = [0] * (n_total + 31)
    x2 = [0] * (n_total + 31)
    x1[0] = 1
    for i in range(31):
        x2[i] = (c_init >> i) & 1
    for n in range(n_total):
        x1[n + 31] = (x1[n + 3] + x1[n]) % 2
        x2[n + 31] = (x2[n + 3] + x2[n + 2] + x2[n + 1] + x2[n]) % 2
    c = []
    for n in range(length):
        c.append((x1[n + 1600] + x2[n + 1600]) % 2)
    return c


def rs_sequence(ns, l, pci):
    c_init = 2 ** 10 * (7 * (ns + 1) + l + 1) * (2 * pci + 1) + 2 * pci + 1
    c = gold(c_init, 4 * MAX_RB)
    r = []
    for m in range(2 * N_RB):
        mp = m + MAX_RB - N_RB
        re = 1 - 2 * c[2 * mp]
        im = 1 - 2 * c[2 * mp + 1]
        r.append((re + 1j * im) / np.sqrt(2))
    return np.array(r)


def get_rs_ref(ns, l, pci):
    key = (pci, ns, l)
    if key not in RS_CACHE:
        RS_CACHE[key] = rs_sequence(ns, l, pci)
    return RS_CACHE[key]


def rs_positions(l, pci):
    if l == 0:
        v = 0
    else:
        v = 3
    v_shift = pci % 6
    ks = []
    for m in range(2 * N_RB):
        ks.append(6 * m + (v + v_shift) % 6)
    return ks


def detect_cell(samples, block_start):
    if len(samples) < FFT_SIZE * 2:
        return None

    best_root = None
    best_peak = 0.0
    best_pos = 0
    for root in ROOTS:
        ncorr = norm_corr(samples, PSS_REFS[root])
        pos = int(np.argmax(ncorr))
        if best_root is None or ncorr[pos] > best_peak:
            best_root = root
            best_peak = ncorr[pos]
            best_pos = pos

    if best_peak < THRESHOLD:
        return None

    p = best_pos
    s = p - CP - FFT_SIZE
    if s < 0 or p + FFT_SIZE > len(samples):
        return None

    pss_rx = fft_to_center(samples[p:p + FFT_SIZE], N_RB)
    h = pss_rx * np.conj(PSS_ZC[best_root])
    sss_rx = fft_to_center(samples[s:s + FFT_SIZE], N_RB)
    sss_eq = sss_rx * np.conj(h)

    scores = np.abs(SSS_TABLE[best_root] @ sss_eq)
    best = int(np.argmax(scores))
    confidence = scores[best] / (np.linalg.norm(sss_eq) * np.sqrt(62) + 1e-12)

    n_id_1 = best % 168
    n_id_2 = ROOTS.index(best_root)
    subframe = 0 if best < 168 else 5
    pci = 3 * n_id_1 + n_id_2

    subframe_start = block_start + p - (SLOT_LEN - FFT_SIZE)
    if subframe == 5:
        subframe_start -= 5 * SUBFRAME_LEN

    print(
        f"PSS={best_peak:.3f} root={best_root} N_ID_2={n_id_2} N_ID_1={n_id_1} "
        f"PCI={pci} subframe={subframe} SSS={confidence:.3f} frame_start={subframe_start % FRAME_LEN}"
    )

    if confidence < SSS_THRESHOLD:
        return None
    return pci, subframe_start


def finish_frame():
    if len(state["power"]) == 20 * len(RS_SYMBOLS):
        rsrp = np.mean(state["power"])
        rssi = np.mean(state["rssi"])
        rsrq = N_RB * rsrp / max(rssi, 1e-20)
        sinr = np.mean(state["sig"]) / max(np.mean(state["noise"]), 1e-20)
        match = np.mean(state["match"])

        values = {
            "rsrp": to_db(rsrp),
            "rssi": to_db(rssi),
            "rsrq": to_db(rsrq),
            "sinr": to_db(sinr),
        }
        for key in values:
            HISTORY[key].append(values[key])
            if len(HISTORY[key]) > MAX_POINTS:
                HISTORY[key].pop(0)
        state["frames"] += 1

        print(
            f"FRAME {state['frames']}: RSRP={values['rsrp']:.1f} dB RSSI={values['rssi']:.1f} dB "
            f"RSRQ={values['rsrq']:.1f} dB SINR={values['sinr']:.1f} dB match={match:.3f}"
        )
        if state["frames"] % PLOT_EVERY == 0:
            update_plot()

    for key in ("power", "rssi", "sig", "noise", "match"):
        state[key] = []


def process_slot(slot, ns):
    pci = state["pci"]
    for l in RS_SYMBOLS:
        start = SYM_USEFUL[l]
        grid = fft_to_grid(slot[start:start + FFT_SIZE], N_RB) / np.sqrt(FFT_SIZE)
        rx = grid[rs_positions(l, pci)]
        ref = get_rs_ref(ns, l, pci)
        h = rx * np.conj(ref)

        power = np.mean(np.abs(rx) ** 2)
        noise = np.mean(np.abs(h[1:] - h[:-1]) ** 2) / 2
        match = np.abs(np.vdot(ref, rx)) / (np.linalg.norm(rx) * np.linalg.norm(ref) + 1e-12)

        state["rs"][(ns, l)] = rx
        state["power"].append(power)
        state["rssi"].append(np.sum(np.abs(grid) ** 2))
        state["noise"].append(noise)
        state["sig"].append(max(power - noise, 0.0))
        state["match"].append(match)
    if ns == 19:
        finish_frame()


def extract_slots():
    buf = state["buf"]
    while True:
        rel = state["next_slot"] - state["buf_start"]
        if rel + SLOT_LEN > len(buf):
            break
        process_slot(buf[rel:rel + SLOT_LEN], state["slot_num"])
        state["next_slot"] += SLOT_LEN
        state["slot_num"] = (state["slot_num"] + 1) % 20
    cut = min(state["next_slot"] - state["buf_start"], len(buf))
    state["buf"] = buf[cut:]
    state["buf_start"] += cut


def process_dl(samples):
    block_start = state["offset"]
    state["offset"] += len(samples)

    if not state["synced"]:
        found = detect_cell(samples, block_start)
        if found is None:
            return samples
        pci, frame_start = found
        t = block_start - frame_start
        slot_idx = -((-t) // SLOT_LEN)
        state["pci"] = pci
        state["next_slot"] = frame_start + slot_idx * SLOT_LEN
        state["slot_num"] = slot_idx % 20
        state["buf"] = np.zeros(0, dtype=np.complex64)
        state["buf_start"] = block_start
        state["synced"] = True
        print(f"SYNC PCI={pci} frame_start={frame_start % FRAME_LEN}")

    state["buf"] = np.concatenate((state["buf"], samples))
    extract_slots()
    return samples


for i in range(3):
    root = ROOTS[i]
    PSS_REFS[root] = ifft(map_to_subcarriers(generate_zc(root), N_RB), FFT_SIZE)
    PSS_ZC[root] = np.array(generate_zc(root))
    rows = []
    for subframe in (0, 5):
        for n_id_1 in range(168):
            rows.append(generate_sss(n_id_1, i, subframe))
    SSS_TABLE[root] = np.array(rows)

ctx = zmq.Context()

enb = ctx.socket(zmq.REQ)
enb.connect(ENB_TX)

ue = ctx.socket(zmq.REP)
ue.bind(UE_RX_BIND)

try:
    while True:
        ue.recv()
        enb.send(b"\x00")
        raw = enb.recv()
        samples = np.frombuffer(raw, dtype=np.complex64)
        samples = apply_channel(samples)
        samples = process_dl(samples)
        out = samples
        if UE_AGC and PATH_LOSS_ENABLED:
            out = samples / GAIN
        ue.send(out.astype(np.complex64).tobytes())
except KeyboardInterrupt:
    pass
finally:
    enb.close(0)
    ue.close(0)
    ctx.term()