"""Варианты «Шмеля»: откуда призвук на пассажах. Рендер и модуляционный спектр огибающей.
    python bee_variants.py [варианты...]"""
import os
import sys

import numpy as np

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio"))
sys.path.insert(0, YP)
sys.path.insert(0, os.path.join(YP, "score"))
import build    # noqa: E402
import render   # noqa: E402
from instruments import MF, LF, HF, LOUD, HIT, HOLD   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "variants")
STEADY = [HOLD | HIT | LOUD | LF | MF]


def variant(name):
    s = build._orig_load("bumblebee")
    ins = {i.name: i for i in s.instruments}
    if name in ("B", "C", "D"):                       # ровный тембр, без мигания ВЧ
        ins["bee"].reg, ins["bee"].reg_loop = list(STEADY), 0xFF
        ins["bee"].rel = [STEADY[-1] & 0x0F]
    if name in ("C", "D"):                            # тремоло струнных без повторного удара
        for r, cmds in s.rows[1].items():
            cmds[:] = [c for c in cmds if not (c[0] == 0x64 + 15)]
    if name == "D":                                   # каждая нота мелодии - новым ударом
        for r, cmds in s.rows[0].items():
            cmds[:] = [(c[1],) if c[0] == 0x63 else c for c in cmds]
    s.title = "ШМЕЛЬ " + name
    return s


def analyse(wav):
    rate, x = render.load_wav(wav)
    x = x[int(5 * rate):int(65 * rate)]
    # огибающая: модуль, сглаживание 2 мс, прорежение до 1 кГц
    k = int(rate / 1000)
    env = np.abs(x)[:len(x) // k * k].reshape(-1, k).mean(axis=1)
    env = env - np.convolve(env, np.ones(200) / 200, mode="same")     # убрать медленное (< 5 Гц)
    seg = 2048
    acc = None
    for i in range(0, len(env) - seg, seg // 2):
        p = np.abs(np.fft.rfft(env[i:i + seg] * np.hanning(seg))) ** 2
        acc = p if acc is None else acc + p
    f = np.fft.rfftfreq(seg, 1 / 1000.0)
    tot = acc[(f > 5) & (f < 400)].sum()
    bands = [(lo, hi, acc[(f >= lo) & (f < hi)].sum() / tot) for lo, hi in
             ((5, 20), (20, 40), (40, 60), (60, 150), (150, 400))]
    peak = f[(f > 20) & (f < 150)][np.argmax(acc[(f > 20) & (f < 150)])]
    rough = float(np.sqrt(acc[(f >= 20) & (f < 150)].sum()) / (np.abs(x).mean() + 1e-12))
    return bands, peak, rough


def main():
    names = sys.argv[1:] or ["A", "B", "C", "D"]
    build._orig_load = build.load_score
    build.load_score = lambda m: variant(m.split("_")[1]) if m.startswith("bee_") else build._orig_load(m)
    import listen
    for nm in names:
        mod = "bee_" + nm
        sys.argv = ["listen.py", mod, "--mp3", "--out", OUT]
        listen.main()
    print()
    for nm in names:
        bands, peak, rough = analyse(os.path.join(OUT, "bee_%s.wav" % nm))
        print("%s: шероховатость %.2f, пик модуляции %.0f Гц, доли по полосам модуляции: %s" % (
            nm, rough, peak, " ".join("%d-%d:%.0f%%" % (lo, hi, 100 * v) for lo, hi, v in bands)))


main()
