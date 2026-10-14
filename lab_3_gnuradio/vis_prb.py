import time
import zmq
import numpy as np
import matplotlib.pyplot as plt

# ---------- задаётся только это ----------
BASE_SRATE = 1.92e6    # base_srate из конфига (1.92e6 для 6 PRB, 23.04e6 для 50 PRB и т.д.)
DL_FREQ_MHZ = 2680.0   # центральная частота DL
HISTORY_MS = 20        # сколько мс показываем
DYN_RANGE_DB = 60      # динамический диапазон цветовой шкалы

# ---------- дальше всё считается ----------
SRATE = BASE_SRATE
N_FFT = round(SRATE / 15e3)
C = N_FFT // 2                                   # индекс DC после fftshift
CP_FIRST = N_FFT * 160 // 2048
CP_OTHER = N_FFT * 144 // 2048
SUBFRAME = round(SRATE / 1000)
HISTORY = 14 * HISTORY_MS

SCS_MHZ = 0.015                                  # 15 кГц
FREQS = DL_FREQ_MHZ + (np.arange(N_FFT) - C) * SCS_MHZ   # МГц, вся полоса

ctx = zmq.Context()

ue = ctx.socket(zmq.REP)
ue.bind("tcp://*:2002")

enb = ctx.socket(zmq.REQ)
enb.connect("tcp://localhost:2000")

buf = np.zeros(0, dtype=np.complex64)
grid = np.full((HISTORY, N_FFT), np.nan)         # строки = время, столбцы = все бины FFT


def subframe_to_grid(sf):
    """1 мс семплов -> 14 строк по N_FFT бинов (мощность в дБ), без обрезки."""
    rows = []
    pos = 0
    for sym in range(14):
        cp = CP_FIRST if sym % 7 == 0 else CP_OTHER
        pos += cp
        s = sf[pos:pos + N_FFT]
        pos += N_FFT
        spec = np.fft.fftshift(np.fft.fft(s))
        rows.append(10 * np.log10(np.abs(spec) ** 2 + 1e-12))
    return np.array(rows)


# ---------- оформление ----------
plt.style.use("dark_background")
plt.ion()
fig, ax = plt.subplots(figsize=(11, 7), constrained_layout=True)
fig.suptitle(f"LTE downlink {DL_FREQ_MHZ:.1f} MHz:  BW={SRATE / 1e6:.2f} MHz",
             fontsize=14)

cmap = plt.get_cmap("inferno").copy()
cmap.set_bad("#101010")

half_bin = SCS_MHZ / 2
f_lo, f_hi = FREQS[0] - half_bin, FREQS[-1] + half_bin
img = ax.imshow(grid.T, aspect="auto", origin="lower", cmap=cmap,
                interpolation="nearest",
                extent=(-HISTORY_MS, 0, f_lo, f_hi), vmin=-80, vmax=0)

# ось времени (X)
ax.set_xlabel("Время, мс (0 = сейчас)")
ax.set_xticks(range(-HISTORY_MS, 1, max(1, HISTORY_MS // 10)))
ax.set_xticks(range(-HISTORY_MS, 1), minor=True)          # границы подкадров
ax.grid(True, which="minor", axis="x", color="white", alpha=0.08, linewidth=0.5)

# ось частот (Y): абсолютные МГц, ~12 подписей на всю полосу
tick_sc = 12 * max(1, round(N_FFT / 12 / 12))
k = np.arange(-(C // tick_sc) * tick_sc, N_FFT - C, tick_sc)
ax.set_yticks(DL_FREQ_MHZ + k * SCS_MHZ)
ax.ticklabel_format(axis="y", useOffset=False)
ax.yaxis.set_major_formatter(plt.FormatStrFormatter("%.3f"))
ax.set_ylabel("Частота, МГц (шаг бина 15 кГц)")
ax.grid(True, which="major", axis="y", color="white", alpha=0.2, linewidth=0.6)
if N_FFT <= 256:                                          # каждый бин
    ax.set_yticks(FREQS - half_bin, minor=True)
    ax.grid(True, which="minor", axis="y", color="white", alpha=0.06, linewidth=0.4)

fig.colorbar(img, ax=ax, label="Мощность, дБ", pad=0.01)

last = 0

while True:
    req = ue.recv()
    enb.send(req)
    data = enb.recv()
    ue.send(data)          # сначала пересылаем, потом рисуем

    buf = np.concatenate([buf, np.frombuffer(data, dtype=np.complex64)])

    while len(buf) >= SUBFRAME:
        rows = subframe_to_grid(buf[:SUBFRAME])
        buf = buf[SUBFRAME:]
        grid = np.vstack([grid[14:], rows])

    if time.time() - last > 0.1 and not np.all(np.isnan(grid)):
        last = time.time()

        vmax = np.nanpercentile(grid, 99.5)
        img.set_data(grid.T)
        img.set_clim(vmax - DYN_RANGE_DB, vmax)

        fig.canvas.flush_events()
        plt.pause(0.001)