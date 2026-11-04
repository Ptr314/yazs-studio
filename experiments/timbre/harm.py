"""Гармоники тона ЯЗС по полосам и высотам, режим 2 счетчика, наложение октавы"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio")))
import render  # noqa: E402

CLOCK = 1021000
OUT = os.path.dirname(os.path.abspath(__file__))
NOTES = [("A2", 45), ("A3", 57), ("A4", 69), ("E5", 76), ("A5", 81), ("E6", 88)]
BUSES = [("НЧ", 4), ("СЧ", 2), ("ВЧ", 1), ("НЧ+СЧ", 6), ("СЧ+ВЧ", 3), ("все", 7)]
ON, OFF = 500, 150


def per(m):
    return int(round(CLOCK / (440.0 * 2 ** ((m - 69) / 12.0))))


def setn(lines, cnt, n):
    lines.append("COMMAND yazs.set($%X,$%02X)" % (cnt, n & 255))
    lines.append("COMMAND yazs.set($%X,$%02X)" % (cnt, n >> 8))


def main():
    lines = ['MACHINE "agat/Agat-9-yazs.ext"', "SPEED MAX", "WAIT 9000",
             "COMMAND yazs.set($3,$36)", "COMMAND yazs.set($3,$76)",
             "COMMAND yazs.set($8,$00)", "COMMAND yazs.set($9,$00)",
             "COMMAND yazs.set($D,$00)", "COMMAND yazs.set($E,$00)",
             'COMMAND sound.record("harm.wav")', "WAIT 500"]
    segs = []
    t = 500

    def seg(kind, label, m, regs):
        nonlocal t
        for r, v in regs:
            lines.append("COMMAND yazs.set($%X,$%02X)" % (r, v))
        lines.append("WAIT %d" % ON)
        for r, v in regs:
            if r in (8, 9):
                lines.append("COMMAND yazs.set($%X,$00)" % r)
        lines.append("WAIT %d" % OFF)
        segs.append((kind, label, m, t))
        t += ON + OFF

    for bname, b in BUSES:
        for nname, m in NOTES:
            setn(lines, 0, per(m))
            seg("bus", bname, (nname, m), [(8, 0x38 | b)])
    # Октава сверху во втором канале без D3 (-8..-10 дБ)
    for nname, m in NOTES[:5]:
        setn(lines, 0, per(m))
        setn(lines, 1, per(m + 12))
        seg("oct", "все + 8ва все", (nname, m), [(8, 0x38 | 7), (9, 0x30 | 7)])
    # Режим 2 счетчика 0
    lines.append("COMMAND yazs.set($3,$34)")
    for nname, m in NOTES:
        setn(lines, 0, per(m))
        seg("mode2", "все, режим 2", (nname, m), [(8, 0x38 | 7)])
    lines += ["WAIT 300", 'COMMAND sound.record()', "EXIT"]
    render.run(lines, "harm", OUT, timeout=900)

    rate, x = render.load_wav(os.path.join(OUT, "harm.wav"))
    for kind, label, (nname, m), t0 in segs:
        a = int((t0 + 150) * rate / 1000)
        b = int((t0 + 450) * rate / 1000)
        s = x[a:b]
        lvl = render.db(np.sqrt(np.mean(s ** 2)))
        sp = np.abs(np.fft.rfft(s * np.hanning(len(s))))
        f = np.fft.rfftfreq(len(s), 1.0 / rate)
        f0 = 440.0 * 2 ** ((m - 69) / 12.0)
        h = []
        for k in range(1, 9):
            fk = k * f0
            if fk > rate / 2 - 500:
                break
            sel = (f > fk * 0.97) & (f < fk * 1.03)
            h.append(sp[sel].max() if sel.any() else 0)
        h1 = h[0] + 1e-12
        rel = " ".join("%4.0f" % (20 * np.log10(v / h1 + 1e-9)) for v in h[1:])
        print("%-6s %-14s %-3s lvl %5.1f | 2..8: %s" % (kind, label, nname, lvl, rel))


main()
