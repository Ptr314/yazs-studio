# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Спектрограмма WAV (частота по логарифму, ноты по сетке) - посмотреть, что
звучит, без прослушивания.

    python studio/spectro.py файл.wav начало_с конец_с выход.png

Функции нужны и sidcompare.py: окна спектра, логарифмическая сетка, подписи нот.
"""

import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402

import render                     # noqa: E402

LO, HI = 40.0, 8000.0             # сетка частот, Гц
STEP = 4                          # ступеней сетки на полутон


def grid(lo=LO, hi=HI):
    """Логарифмическая сетка частот по 1/STEP полутона"""
    return lo * 2 ** (np.arange(0, 12 * np.log2(hi / lo) * STEP) / (12.0 * STEP))


def frames(x, rate, starts, n=4096):
    """Модули спектра окон Ханна по n отсчетов с началами starts:
    (спектр [частота, окно], частоты)"""
    win = np.hanning(n)
    spec = np.array([np.abs(np.fft.rfft(x[s:s + n] * win)) for s in starts]).T
    return spec, np.fft.rfftfreq(n, 1.0 / rate)


def logspec(spec, f, g):
    """Спектр на сетке g, дБ (без нормировки)"""
    idx = np.searchsorted(f, g).clip(1, len(f) - 1)
    return 20 * np.log10(spec[idx] + 1e-6)


def note_axis(ax, g):
    """Подписи C и A по оси высоты: ось - номера ступеней сетки g"""
    ticks, labels = [], []
    for octv in range(1, 10):
        for name, semi in (("C", 0), ("A", 9)):
            fr = 440 * 2 ** ((octv - 4) + (semi - 9) / 12.0)
            if g[0] <= fr <= g[-1]:
                ticks.append(12 * STEP * np.log2(fr / g[0]))
                labels.append("%s%d" % (name, octv))
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels)
    ax.grid(axis="y", color="white", alpha=0.2)


def main():
    wav, t0, t1, png = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    rate, x = render.load_wav(wav)
    x = x[int(t0 * rate):int(t1 * rate)]
    n, hop = 4096, 512
    spec, f = frames(x, rate, range(0, len(x) - n + 1, hop), n)
    g = grid()
    img = logspec(spec, f, g)
    img -= img.max()
    fig, ax = plt.subplots(figsize=(16, 7), dpi=80)
    ax.imshow(img, aspect="auto", origin="lower", vmin=-60, vmax=0, cmap="magma",
              extent=[t0, t1, 0, len(g)])
    note_axis(ax, g)
    ax.set_xlabel("с")
    fig.tight_layout()
    fig.savefig(png)


if __name__ == "__main__":
    main()
