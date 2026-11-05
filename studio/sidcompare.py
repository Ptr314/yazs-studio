# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Перевод SID против эталонной записи звука SID: мелодия переводится (или берется готовый
.yz), eCat3 играет ее, как listen.py, и записи сравниваются. Зачем и что искать -
docs/SID.md, «Сверка с эталоном».

    python studio/sidcompare.py мелодия.sid [ключи]

    --wav ФАЙЛ       эталон (по умолчанию - мелодия.wav рядом с .sid)
    --song N         мелодия файла (по умолчанию - начальная)
    --seconds S      сколько сравнивать (по умолчанию - длина эталона, не больше 120 с)
    --yz ФАЙЛ        готовый .yz или .yzt вместо перевода (строка - кадр SID, как у sid2yz)
    --loud, --chorus [1,3], --release-drums   как у sid2yz
    --out КАТАЛОГ    куда писать (по умолчанию out/sidcompare)

Выход - картинка (спектрограммы эталона и перевода в одном масштабе, под ними сходство во
времени) и сходство по 5 с в тексте. Сходство - корреляция окон 93 мс через 23 мс, от -1
до 1, двух видов:
- «ноты» - хрома (12 классов высоты, октавы сложены): тембр, полосы и громкость на нее
  влияют мало, а лишние и пропавшие ноты, ударные вместо нот и сдвиг строя - сильно;
- «спектр» - спектр от 80 Гц на сетке 1/4 полутона, сглаженный на полполутона: видит и
  октавы, и тембр, ловит ложные глиссандо, которые хрома почти пропускает.
Начала записей выравниваются по первому звуку, время перевода приводится ко времени SID:
строка .YZ (тик 7980 / N, speed тиков) - кадр SID 50.125 Гц.
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import listen                     # noqa: E402
import render                     # noqa: E402
import spectro                    # noqa: E402
import tables                     # noqa: E402
import yztext                     # noqa: E402
from sid import c64, convert, psid  # noqa: E402

N, HOP = 4096, 1024               # окно и шаг при 44.1 кГц: 93 и 23 мс
SEG = 5.0                         # сходство по участкам, с
CHROMA_BAND = (55.0, 4200.0)      # A1 - C8
SPEC_LO, SPEC_SMOOTH = 80.0, 2    # спектр: от 80 Гц, сглаживание +-2 ступени сетки
QUIET_DB = 40                     # окна тише максимума на столько дБ в обеих записях не считаются
# начало звука: у эталона - от его пика; у записи eCat3 до мелодии цифровая тишина, порог
# постоянный (как listen.trim), чтобы громкость перевода не сдвигала начало
REF_START, YZ_START = 0.03, 0.002


def first_sound(x, rate, level):
    """Отсчет первого звука: выше level, минус 50 мс"""
    nz = np.nonzero(np.abs(x) > level)[0]
    return max(0, int(nz[0]) - rate // 20) if len(nz) else 0


def chroma(spec, f):
    """Хрома по окнам: (12, окон), класс 0 - C; доля частоты делится между соседними
    классами, модули сжаты логарифмом от пика своего окна (громкость не важна)"""
    band = (f >= CHROMA_BAND[0]) & (f <= CHROMA_BAND[1])
    pc = (12 * np.log2(f[band] / 440.0) + 9) % 12
    lo = np.floor(pc).astype(int) % 12
    w = pc - np.floor(pc)
    m = np.zeros((12, int(band.sum())))
    cols = np.arange(len(pc))
    m[lo, cols] += 1 - w
    m[(lo + 1) % 12, cols] += w
    mag = spec[band]
    return m @ np.log1p(1000 * mag / (mag.max(axis=0) + 1e-12))


def band_db(spec, f):
    """Уровень окон в полосе хромы, дБ"""
    band = (f >= CHROMA_BAND[0]) & (f <= CHROMA_BAND[1])
    return 10 * np.log10(np.sum(spec[band] ** 2, axis=0) + 1e-12)


def correlate(ca, cb):
    """Корреляция столбцов (окон); где одна запись ровная или молчит - 0"""
    a = ca - ca.mean(axis=0)
    b = cb - cb.mean(axis=0)
    den = np.sqrt((a * a).sum(axis=0) * (b * b).sum(axis=0))
    return np.where(den > 1e-9, (a * b).sum(axis=0) / np.maximum(den, 1e-9), 0.0)


def spectrum_view(img, g):
    """Спектр для сравнения с тембром и октавами: от 80 Гц, пол -60 дБ от пика своего окна,
    сглажен на полполутона (строй и вибрато не мешают)"""
    s = img[g >= SPEC_LO]
    s = np.maximum(s, s.max(axis=0) - 60)
    ker = np.ones(2 * SPEC_SMOOTH + 1) / (2 * SPEC_SMOOTH + 1)
    return np.apply_along_axis(lambda c: np.convolve(c, ker, "same"), 0, s)


def segments(t, end, sim, active):
    """Средние по участкам SEG: [(от, до, среднее или None)]"""
    out = []
    for a in np.arange(0, end, SEG):
        sel = active & (t >= a) & (t < a + SEG)
        out.append((a, min(a + SEG, end), float(sim[sel].mean()) if sel.any() else None))
    return out


def convert_sid(sf, song, seconds, outdir, loud=False, chorus=None, release_drums=False):
    """Перевод первых seconds секунд без повтора: путь .yz"""
    d = c64.run(sf, song, seconds)
    conv = convert.Converter(d, sf, chorus=chorus, end=d.frames, loud=loud, release_drums=release_drums)
    data, _, _ = convert.build(conv.run(), d.frames)
    path = os.path.join(outdir, "%s.%02d.yz" % (os.path.splitext(os.path.basename(sf.path))[0], song))
    open(path, "wb").write(data)
    return path


def compare(ref_wav, yz_wav, row_rate, seconds):
    """Окна обеих записей на общей сетке времени SID: словарь для отчета и картинки"""
    rr, xr = render.load_wav(ref_wav)
    ry, xy = render.load_wav(yz_wav)
    k = c64.FPS / row_rate                   # секунда SID - k секунд перевода
    r0 = first_sound(xr, rr, REF_START * np.max(np.abs(xr)))
    y0 = first_sound(xy, ry, YZ_START)
    hop_s = HOP / float(rr)
    count = int(min(seconds, (len(xr) - r0 - N) / float(rr), (len(xy) - y0 - N) / (ry * k)) / hop_s)
    if count < 2:
        raise ValueError("записи короче окна сравнения")
    t = np.arange(count) * hop_s
    sr, fr = spectro.frames(xr, rr, (r0 + np.round(t * rr)).astype(int), N)
    sy, fy = spectro.frames(xy, ry, (y0 + np.round(t * k * ry)).astype(int), N)
    g = spectro.grid()
    img = (spectro.logspec(sr, fr, g), spectro.logspec(sy, fy, g))
    er, ey = band_db(sr, fr), band_db(sy, fy)
    active = (er > np.percentile(er, 95) - QUIET_DB) | (ey > np.percentile(ey, 95) - QUIET_DB)
    end = t[-1] + hop_s
    res = {"t": t, "end": end, "active": active, "lead": (r0 / float(rr), y0 / float(ry)),
           "grid": g, "img": img}
    for key, sim in (("notes", correlate(chroma(sr, fr), chroma(sy, fy))),
                     ("spec", correlate(spectrum_view(img[0], g), spectrum_view(img[1], g)))):
        res[key] = {"sim": sim, "segs": segments(t, end, sim, active),
                    "mean": float(sim[active].mean()) if active.any() else 0.0}
    return res


LABELS = {"notes": "ноты", "spec": "спектр"}
COLORS = {"notes": "#1f77b4", "spec": "#d62728"}


def plot(res, titles, png):
    t, g, end, act = res["t"], res["grid"], res["end"], res["active"]
    fig, axs = plt.subplots(3, 1, figsize=(18, 12), dpi=70, sharex=True,
                            gridspec_kw={"height_ratios": [5, 5, 2]})
    for ax, img, title in zip(axs, res["img"], titles):
        ax.imshow(img - img.max(), aspect="auto", origin="lower", vmin=-60, vmax=0, cmap="magma",
                  extent=[0, end, 0, len(g)])
        spectro.note_axis(ax, g)
        ax.set_title(title)
    ax = axs[2]
    w = np.ones(max(1, int(round(1.0 / (t[1] - t[0])))))        # среднее за 1 с
    for key in ("notes", "spec"):
        sim = np.where(act, res[key]["sim"], 0.0)
        smooth = np.convolve(sim, w, "same") / np.maximum(np.convolve(act.astype(float), w, "same"), 1e-9)
        ax.plot(t, np.where(act, smooth, np.nan), color=COLORS[key], lw=1.5,
                label="%s, в среднем %.2f" % (LABELS[key], res[key]["mean"]))
        for a, b, v in res[key]["segs"]:
            if v is not None:
                ax.hlines(v, a, b, color=COLORS[key], lw=1, linestyles="dashed")
    ax.set_ylim(-0.3, 1.05)
    ax.set_ylabel("сходство")
    ax.set_xlabel("с (время SID)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(png)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="перевод SID против эталонной записи")
    ap.add_argument("sid")
    ap.add_argument("--wav")
    ap.add_argument("--song", type=int)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--yz")
    ap.add_argument("--loud", action="store_true")
    ap.add_argument("--chorus", nargs="?", const="auto")
    ap.add_argument("--release-drums", action="store_true")
    ap.add_argument("--out", default=os.path.join(render.OUT, "sidcompare"))
    a = ap.parse_args()
    ref = a.wav or os.path.splitext(a.sid)[0] + ".wav"
    if not os.path.isfile(ref):
        sys.exit("нет эталона %s (ключ --wav)" % ref)
    sf = psid.SidFile(a.sid)
    song = a.song or sf.start_song
    rate, x = render.load_wav(ref)
    seconds = a.seconds or min(120.0, len(x) / float(rate))
    outdir = os.path.abspath(a.out)
    os.makedirs(outdir, exist_ok=True)
    if a.yz:
        yz = os.path.abspath(a.yz)
    else:
        chorus = [int(v) for v in a.chorus.split(",")] if a.chorus and a.chorus != "auto" else a.chorus
        yz = convert_sid(sf, song, seconds + 1, outdir, a.loud, chorus, a.release_drums)
    data = yztext.load(yz)
    row_rate = tables.TIMER_CLOCK / float(data[66] * data[67])
    print("%s, мелодия %d: эталон %s, перевод %s" % (sf.name, song, ref, yz))
    wav, _, _ = listen.record(yz, outdir)
    res = compare(ref, wav, row_rate, seconds)
    png = os.path.splitext(wav)[0] + ".compare.png"
    plot(res, ["эталон: %s" % os.path.basename(ref), "ЯЗС: %s" % os.path.basename(yz)], png)
    print("первый звук: эталон %.2f с, перевод %.2f с; строка .YZ %.3f Гц против кадра SID %.3f Гц" % (
        res["lead"] + (row_rate, c64.FPS)))
    print("сходство (корреляция: 1 - совпадает, 0 - не связано), по %d с и в среднем:" % SEG)
    print("         " + " ".join("%5s" % ("%d-%d" % (a_, b_)) for a_, b_, _ in res["notes"]["segs"]))
    for key in ("notes", "spec"):
        print("  %-6s " % LABELS[key] + " ".join("%5s" % ("%.2f" % v if v is not None else "-")
                                                  for _, _, v in res[key]["segs"]) +
              "   %.2f" % res[key]["mean"])
    print("картинка:", png)
    print("запись:", wav)


if __name__ == "__main__":
    main()
