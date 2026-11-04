# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""Что использует мелодия: сводка возможностей SID по снятым регистрам и поиск повтора"""

import numpy as np

from .c64 import FPS, midi, note_name


def find_loop(d, min_period=100, window=1000):
    """Повтор хвоста: (начало, период) в кадрах или None. Сравнивается грубо - полутон,
    волна и GATE голосов, - чтобы фаза вибрато и ШИМ повтор не ломали"""
    F = d.frames
    w = min(window, F // 3)
    if w < 100:
        return None
    h = np.zeros(F, np.int64)
    for v in range(3):
        semi = np.where(d.freq[v] > 0, np.round(12 * np.log2(np.maximum(d.freq[v], 1))), -1).astype(np.int64)
        h = h * 1000003 + semi * 512 + (d.ctrl[v].astype(np.int64) & 0xF1)
    best = None
    for P in range(min_period, F - w):
        if np.array_equal(h[F - w:], h[F - w - P:F - P]):
            best = P
            break
    if best is None:
        return None
    s = F - w - best
    while s > 0 and h[s - 1] == h[s - 1 + best]:
        s -= 1
    return s, best


def note_motion(p):
    """Движение высоты внутри ноты (полутона по кадрам): arp, vib, slide, static..."""
    if len(p) < 3:
        return "static"
    d = np.diff(p)
    jumps = np.abs(d) >= 0.9
    if jumps.sum() >= 2:
        return "arp"
    dev = p - p[0]
    if np.abs(dev).max() < 0.05:
        return "static"
    if np.abs(dev).max() < 1.5:
        c = dev - dev.mean()
        big = np.abs(c) > 0.02
        if big.sum() > 2 and np.sum(np.diff(np.sign(c[big])) != 0) >= 2:
            return "vib"
    if abs(dev[-1]) >= 1.0 and not jumps.any():
        return "slide"
    return "jump" if jumps.any() else "bend"


def analyze(d):
    """Сводка по голосам, фильтру, громкости, повтору"""
    F = d.frames
    out = dict(d.meta)
    out.update({"frames": F, "seconds": F / FPS, "voices": []})
    if F == 0:
        return out
    sounding_all = []
    for v in range(3):
        ctrl = d.ctrl[v].astype(np.int32)
        wave = ctrl >> 4
        snd = ((ctrl & 1) == 1) & (wave != 0) & ((ctrl & 8) == 0)
        sounding_all.append(snd)
        n = max(1, int(snd.sum()))

        def sh(mask):
            return float((mask & snd).sum()) / n
        pulse = snd & ((wave & 4) != 0)
        pwch = np.zeros(F, bool)
        pwch[1:] = d.pw[v][1:] != d.pw[v][:-1]
        pw = d.pw[v][pulse]
        notes = d.notes(v)
        motion = {}
        drums = {"noise_note": 0, "noise_attack": 0, "drop": 0}
        pitches = []
        adsr = set()
        for s, g, nxt in notes:
            end = max(g, s + 1)
            wv = wave[s:end]
            if np.any((wv[:3] & 8) != 0):
                drums["noise_attack"] += 1
            if np.mean((wv & 8) != 0) >= 0.5:
                drums["noise_note"] += 1
                continue
            p = np.array([midi(int(x)) for x, w in zip(d.freq[v][s:end], wv) if x > 0 and not w & 8])
            if len(p) == 0:
                continue
            if len(p) > 2 and (p[:8].min() - p[0]) <= -12:
                drums["drop"] += 1
            k = note_motion(p)
            motion[k] = motion.get(k, 0) + 1
            pitches.append(p[0])
            adsr.add((int(d.ad[v][s]), int(d.sr[v][s])))
        routed = ((d.route >> v) & 1).astype(bool) & snd
        out["voices"].append({
            "sounding": float(snd.sum()) / F,
            "tri": sh(wave == 1), "saw": sh(wave == 2), "pulse": sh(wave == 4), "noise": sh(wave == 8),
            "combined": sh(np.isin(wave, [3, 5, 6, 7])), "noise_mix": sh(wave > 8),
            "ring": sh(((ctrl & 4) != 0) & ((wave & 1) != 0)), "sync": sh((ctrl & 2) != 0),
            "pwm": float((pwch & pulse).sum()) / max(1, int(pulse.sum())),
            "pw_range": [int(pw.min()), int(pw.max())] if len(pw) else None,
            "notes": len(notes), "motion": motion, "drums": drums,
            "range": [note_name(min(pitches)), note_name(max(pitches))] if pitches else None,
            "adsr": len(adsr), "filtered": float(routed.sum()) / n,
        })
    snd = np.array(sounding_all)
    poly = snd.sum(axis=0)
    out["poly"] = [float((poly == k).sum()) / F for k in range(4)]
    fsnd = ((d.route & 7) != 0) & snd.any(axis=0)
    out["filter"] = {
        "share": float(fsnd.sum()) / max(1, int(snd.any(axis=0).sum())),
        "modes": sorted(set(int(x) for x in d.mode[fsnd])),
        "fc_range": [int(d.fc[fsnd].min()), int(d.fc[fsnd].max())] if fsnd.any() else None,
        "fc_changes_s": float((np.diff(d.fc)[fsnd[1:]] != 0).sum()) / max(1e-9, fsnd.sum() / FPS),
        "res": sorted(set(int(x) for x in d.res[fsnd])),
    }
    out["volume"] = {"values": sorted(set(int(x) for x in d.vol)),
                     "changes": int((np.diff(d.vol.astype(np.int32)) != 0).sum()),
                     "multi_writes": int((d.wcount[:F, 24] > 1).sum())}
    lp = find_loop(d)
    out["loop"] = [lp[0] / FPS, lp[1] / FPS] if lp else None
    return out


MODES = {0: "нет", 1: "LP", 2: "BP", 3: "LP+BP", 4: "HP", 5: "LP+HP", 6: "BP+HP", 7: "все"}
LEGEND = """Голоса - доли звучащих кадров, %: T треугольник, S пила, P импульс, N шум, C смешанные
волны, R кольцевая, Y синхронизация, F через фильтр; ШИМ - доля кадров импульса со сменой
ширины; ноты: число, диапазон, движение высоты (a арпеджио, v вибрато, s скольжение);
уд. - ноты-шумы / с шумом в первых кадрах / с падением на октаву; ADSR - разных наборов"""


def pct(x):
    return "%d" % round(100 * x) if x >= 0.005 else "."


def report(r, tag):
    lp = r["loop"]
    print("%-24s %5.1f с (%s)%s  play %d/%d тактов%s%s" % (
        tag, r["seconds"], r["stop"], ", повтор с %.1f с через %.1f с" % tuple(lp) if lp else "",
        r["play_avg"], r["play_max"],
        ", чтения SID: " + ",".join("$%02X:%d" % (k, n) for k, n in sorted(r["sid_reads"].items()))
        if r["sid_reads"] else "",
        ", недок. команды: " + ",".join(sorted(r["undoc"])) if r["undoc"] else ""))
    for v, vd in enumerate(r["voices"]):
        mo = vd["motion"]
        print("   г%d %3s%%  T%-3s S%-3s P%-3s N%-3s C%-3s R%-3s Y%-3s F%-3s ШИМ%-3s ноты %4d %-9s "
              "a%-4d v%-4d s%-3d уд %d/%d/%d ADSR %d" % (
                  v + 1, pct(vd["sounding"]), pct(vd["tri"]), pct(vd["saw"]), pct(vd["pulse"]),
                  pct(vd["noise"]), pct(vd["combined"]), pct(vd["ring"]), pct(vd["sync"]),
                  pct(vd["filtered"]), pct(vd["pwm"]), vd["notes"],
                  "%s-%s" % tuple(vd["range"]) if vd["range"] else "-",
                  mo.get("arp", 0), mo.get("vib", 0), mo.get("slide", 0), vd["drums"]["noise_note"],
                  vd["drums"]["noise_attack"], vd["drums"]["drop"], vd["adsr"]))
    fl, vol = r["filter"], r["volume"]
    print("   сразу звучит 0/1/2/3 голоса: %s%%; фильтр: %s%% кадров%s; громкость: %s, смен %d%s" % (
        "/".join(pct(x) for x in r["poly"]), pct(fl["share"]),
        (", %s, срез %d-%d, смен %.1f/с, резонанс %s" % (
            ",".join(MODES[m] for m in fl["modes"]), fl["fc_range"][0], fl["fc_range"][1],
            fl["fc_changes_s"], fl["res"])) if fl["fc_range"] else "",
        vol["values"] if len(vol["values"]) < 6 else "%d-%d" % (vol["values"][0], vol["values"][-1]),
        vol["changes"], ", запись чаще раза в кадр: %d" % vol["multi_writes"] if vol["multi_writes"] else ""))
