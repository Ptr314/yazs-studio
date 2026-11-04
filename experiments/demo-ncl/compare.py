"""Симфония против демонстрации НКЛ: одни и те же мерки по регистрам (шаг 5 мс) и по звуку"""
import math
import os
import sys

import numpy as np

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio"))
sys.path.insert(0, YP)
import pyplay  # noqa: E402
import render  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.join(os.path.dirname(HERE), "final")
DT = 0.005
CLOCK = 1021000.0
BUSN = {1: "ВЧ", 2: "СЧ", 3: "СЧ+ВЧ", 4: "НЧ", 5: "НЧ+ВЧ", 6: "НЧ+СЧ", 7: "все"}


def song_series(path):
    p = pyplay.Player(open(path, "rb").read())
    while p.ticks < 100 * 600 and p.step():
        pass
    by_tick = {}
    for t, a, v in p.writes:
        by_tick.setdefault(t, []).append((a, v))
    regs = [0] * 16
    cnt = [0] * 6
    hi = {}
    n = 80
    starts, R, C = [], [], []
    tm = 0.0
    addr2c = {0: 0, 1: 1, 2: 2, 4: 3, 5: 4, 6: 5}
    for t in range(p.ticks + 1):
        for a, v in by_tick.get(t, []):
            regs[a] = v
            if a in addr2c:
                k = addr2c[a]
                if hi.get(a):
                    cnt[k] = (cnt[k] & 0xFF) | (v << 8)
                    hi[a] = False
                else:
                    cnt[k] = (cnt[k] & 0xFF00) | v
                    hi[a] = True
        if cnt[5]:
            n = cnt[5]
        starts.append(tm)
        R.append(list(regs))
        C.append(list(cnt[:5]))
        tm += n / 7980.0
    starts = np.array(starts)
    grid = np.arange(0, tm, DT)
    idx = np.searchsorted(starts, grid, side="right") - 1
    return np.array(R)[idx], np.array(C)[idx]


def demo_series(path, t0, t1):
    R, C = [], []
    for ln in open(path):
        a, b = ln.split(" | ")
        R.append([int(v, 16) for v in a.split()])
        C.append([int(v, 16) for v in b.split()][:5])
    R, C = np.array(R), np.array(C)
    a, b = int(t0 / DT), int(t1 / DT)
    return R[a:b], C[a:b]


def metrics(R, C):
    T = len(R)
    m = {"dur": T * DT}
    midi = 69 + 12 * np.log2(CLOCK / np.maximum(C, 1) / 440.0)
    snd = np.zeros((T, 5), bool)
    for c in range(5):
        r = R[:, 8 + c]
        d4 = (r & 0x10) != 0
        rise = np.r_[False, d4[1:] & ~d4[:-1]]
        last = -10 ** 9
        since = np.zeros(T)
        for i in range(T):
            if rise[i]:
                last = i
            since[i] = (i - last) * DT
        snd[:, c] = ((r & 0x20) != 0) | (d4 & (since < 0.5))
        snd[:, c] &= (r & 7) != 0
    ct = snd.sum()
    m["poly"] = snd.sum(1).mean()
    m["poly_active"] = snd.sum(1)[snd.any(1)].mean() if snd.any() else 0
    # Полосы, D3, огибающие - доля канало-времени звучания
    bus = {}
    d3 = 0
    env = {"D4+D5": 0, "D5": 0, "D4": 0}
    for c in range(5):
        r = R[snd[:, c], 8 + c]
        for b in range(1, 8):
            bus[b] = bus.get(b, 0) + int(((r & 7) == b).sum())
        d3 += int(((r & 8) != 0).sum())
        e = r & 0x30
        env["D4+D5"] += int((e == 0x30).sum())
        env["D5"] += int((e == 0x20).sum())
        env["D4"] += int((e == 0x10).sum())
    m["bus"] = {BUSN[b]: bus[b] / ct for b in bus}
    m["d3"] = d3 / ct
    m["env"] = {k: v / ct for k, v in env.items()}
    # Высоты
    mm = midi[snd]
    m["pitch"] = np.percentile(mm, [5, 50, 95]) if len(mm) else [0, 0, 0]
    m["pulse"] = float((CLOCK / C[snd] < 555).mean())
    # Ноты, микродвижения высоты, смены тембра
    notes = 0
    micro = 0
    moving = 0
    tchg = 0
    for c in range(5):
        r = R[:, 8 + c]
        s = snd[:, c]
        d4 = (r & 0x10) != 0
        both = s[1:] & s[:-1]
        dm = np.abs(np.diff(midi[:, c]))
        notes += int((d4[1:] & ~d4[:-1]).sum())
        notes += int((s[1:] & ~s[:-1] & ~(d4[1:] & ~d4[:-1])).sum())
        notes += int((both & (dm >= 0.5) & ~(d4[1:] & ~d4[:-1])).sum())
        micro += int((both & (dm > 0) & (dm < 0.5)).sum())
        moving += int((both & (dm > 0) & (dm < 0.5)).sum())
        tchg += int((both & (((r[1:] ^ r[:-1]) & 0x0F) != 0)).sum())
    m["notes_s"] = notes / m["dur"]
    m["micro_s"] = micro / (ct * DT)
    m["moving"] = moving / max(1, ct)
    m["timbre_s"] = tchg / (ct * DT)
    # Удвоения: унисон с расстройкой, точный унисон, октава
    det = uni = octv = 0
    for i in range(0, T, 4):
        idx = np.nonzero(snd[i])[0]
        fl = set()
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                d = abs(midi[i, idx[a]] - midi[i, idx[b]])
                if d == 0:
                    fl.add("u")
                elif d < 0.4:
                    fl.add("d")
                elif abs(d - 12) < 0.4 or abs(d - 24) < 0.4:
                    fl.add("o")
        det += "d" in fl
        uni += "u" in fl
        octv += "o" in fl
    k = len(range(0, T, 4))
    m["det"], m["uni"], m["oct"] = det / k, uni / k, octv / k
    # Ударные
    for i, reg in ((6, 13), (7, 14)):
        r = R[:, reg]
        d4 = (r & 0x10) != 0
        rise = np.nonzero(d4[1:] & ~d4[:-1])[0] + 1
        m["dr%d" % i] = len(rise) / m["dur"] * 60
        pres = {}
        for j in rise:
            pres[r[j] & 0x0F] = pres.get(r[j] & 0x0F, 0) + 1
        m["dr%d_p" % i] = sorted(pres.items(), key=lambda x: -x[1])[:5]
    return m


def audio(path, t0=0, t1=None):
    rate, x = render.load_wav(path)
    x = x[int(t0 * rate):int(t1 * rate) if t1 else None]
    w = int(rate * 0.4)
    n = len(x) // w
    r = np.sqrt(np.mean(x[:n * w].reshape(n, w) ** 2, axis=1))
    db = 20 * np.log10(r + 1e-9)
    db = db[db > -50]
    w2 = int(rate * 0.1)
    n2 = len(x) // w2
    fr = x[:n2 * w2].reshape(n2, w2) * np.hanning(w2)
    sp = np.abs(np.fft.rfft(fr, axis=1)) ** 2
    f = np.fft.rfftfreq(w2, 1.0 / rate)
    loud = sp.sum(1) > 1e-6 * sp.sum(1).max()
    cen = (sp[loud] * f).sum(1) / sp[loud].sum(1)
    tot = sp[loud].sum()
    edges = [0, 150, 400, 1000, 3000, 6000, rate / 2]
    bands = [sp[loud][:, (f >= a) & (f < b)].sum() / tot for a, b in zip(edges, edges[1:])]
    return {"rms": 20 * math.log10(np.sqrt(np.mean(x ** 2)) + 1e-9), "p10": np.percentile(db, 10),
            "p50": np.percentile(db, 50), "p95": np.percentile(db, 95),
            "cen": float(np.median(cen)), "bands": bands}


def show(name, m, a):
    print("== %s  %.0f с" % (name, m["dur"]))
    print("  голосов в среднем %.2f (когда звучит %.2f); нот/с %.1f; пульс. регистр (<555 Гц) %.0f%%" % (
        m["poly"], m["poly_active"], m["notes_s"], 100 * m["pulse"]))
    print("  высота P5/P50/P95 MIDI %.0f/%.0f/%.0f" % tuple(m["pitch"]))
    print("  полосы: " + ", ".join("%s %.0f%%" % (k, 100 * v) for k, v in sorted(m["bus"].items(), key=lambda x: -x[1]) if v > 0.005)
          + "; D3 %.0f%%" % (100 * m["d3"]))
    print("  огибающие: " + ", ".join("%s %.0f%%" % (k, 100 * v) for k, v in m["env"].items()))
    print("  микродвижения высоты %.1f/с на голос, нота в движении %.0f%% времени; смены полос/D3 %.2f/с на голос" % (
        m["micro_s"], 100 * m["moving"], m["timbre_s"]))
    print("  удвоения: расстр. унисон %.0f%%, точный унисон %.0f%%, октава %.0f%%" % (
        100 * m["det"], 100 * m["uni"], 100 * m["oct"]))
    print("  ударный 6: %.0f/мин %s; ударный 7: %.0f/мин %s" % (
        m["dr6"], " ".join("$%02X:%d" % p for p in m["dr6_p"]), m["dr7"], " ".join("$%02X:%d" % p for p in m["dr7_p"])))
    if a:
        print("  звук: RMS %.1f дБ, 400 мс P10/P50/P95 %.1f/%.1f/%.1f (размах %.1f), центр спектра %.0f Гц" % (
            a["rms"], a["p10"], a["p50"], a["p95"], a["p95"] - a["p10"], a["cen"]))
        print("  энергия <150/150-400/400-1k/1-3k/3-6k/>6k: " + " ".join("%.0f%%" % (100 * b) for b in a["bands"]))


def main():
    R, C = demo_series(os.path.join(HERE, "full.txt"), 14.6, 400.5)
    show("ДЕМО НКЛ (музыка)", metrics(R, C), audio(os.path.join(HERE, "demo.wav"), 14.6 + 0.52, 400.5))
    tot = None
    for p in ["m1_toccata", "m2_adagio", "m3_scherzo", "m4_blues", "m5_synth", "m6_finale"]:
        R, C = song_series(os.path.join(FINAL, p + ".yz"))
        show(p, metrics(R, C), audio(os.path.join(FINAL, p + ".wav")))
        tot = (R, C) if tot is None else (np.r_[tot[0], R], np.r_[tot[1], C])
    show("СИМФОНИЯ целиком", metrics(*tot), audio(os.path.join(FINAL, "symphony.wav")))


if __name__ == "__main__":
    main()
