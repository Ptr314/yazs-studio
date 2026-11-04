"""Фразы тоновых каналов каждой части: такты, инструменты, медиана и диапазон высот (MIDI)"""
import os
import sys

import numpy as np

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio"))
sys.path.insert(0, YP)
import build  # noqa: E402
from compose import CMD_INSTR, CMD_LEGATO  # noqa: E402


def phrases(song, ch, gap_bars=2):
    rows = song.rows[ch]
    out = []
    cur = None
    instr = None
    last = None
    for r in sorted(rows):
        for c in rows[r]:
            if c[0] == CMD_INSTR:
                if instr != c[1] and cur:
                    out.append(cur)
                    cur = None
                instr = c[1]
            elif c[0] < 0x60 or c[0] == CMD_LEGATO:
                note = c[-1] if c[0] == CMD_LEGATO else c[0]
                if cur and last is not None and r - last > gap_bars * song.bar_rows:
                    out.append(cur)
                    cur = None
                if cur is None:
                    cur = {"r0": r, "notes": [], "ins": instr}
                cur["notes"].append(note + 12)
                cur["r1"] = r
                last = r
    if cur:
        out.append(cur)
    return out


for mod in sys.argv[1:]:
    s = build.load_score(mod)
    names = {i: ins.name for i, ins in enumerate(s.instruments)}
    print("==", mod, "тактов", s.end_row // s.bar_rows)
    for ch in range(5):
        for p in phrases(s, ch):
            n = np.array(p["notes"])
            print("  к%d т%3d-%3d %-10s n=%3d мед %3.0f мин %3d макс %3d" % (
                ch, p["r0"] // s.bar_rows, p["r1"] // s.bar_rows, names.get(p["ins"], "?"),
                len(n), np.median(n), n.min(), n.max()))
