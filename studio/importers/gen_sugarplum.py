"""Танец Феи Драже: партитура (MIDI полной партитуры) -> score/data_sugarplum.py.
    python studio/importers/gen_sugarplum.py путь.mid"""
import os
import sys

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, YP)
import midi2mml as M  # noqa: E402

RPB, BEATS_BAR = 48, 2
BAR = RPB * BEATS_BAR

WIND = {1: "flute", 2: "oboe", 3: "ehorn", 4: "clar", 5: "bclar", 6: "bassoon", 7: "horn"}
STR_ARCO = {9: "violin", 10: "violin", 11: "viola", 12: "cello", 13: "cbass"}
STR_PIZZ = {9: "pizz", 10: "pizz", 11: "pizz", 12: "pizz_b", 13: "pizz_b"}

# Канал: (источники по важности, транспонирование, щипковый звон)
CHANNELS = {
    0: ([(8, "top")], -24, True),
    1: ([(5, "top"), (4, "top"), (3, "top"), (1, "top"), (8, ("rank", 1), -24)], 0, False),
    2: ([(9, "top"), (2, "top"), (10, "top"), (1, ("rank", 1))], 0, False),
    3: ([(11, "top"), (10, "bottom"), (7, "top"), (6, "top")], 0, False),
    4: ([(13, "bottom"), (12, "bottom"), (6, "bottom"), (7, "bottom")], 0, False),
}


def main():
    div, tracks = M.parse_midi(sys.argv[1])
    last = max(n[0] + n[1] for _, ns in tracks for n in ns)
    bars = int(-(-last // BEATS_BAR))
    end = bars * BEATS_BAR

    def instr(ch):
        def f(ev):
            tr, beat = ev[3], ev[4]
            if tr == 8:
                return "celesta" if ch == 0 else "celesta2"
            if tr in WIND:
                return WIND[tr]
            pizz = M.program_at(tracks, tr, beat) == 45
            return (STR_PIZZ if pizz else STR_ARCO)[tr]
        return f

    out = ["# SPDX-License-Identifier: GPL-3.0-or-later",
           "# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio",
           '"""Сгенерировано из партитуры П. И. Чайковского (общественное достояние):',
           "Щелкунчик, Танец Феи Драже. Сетка - %d строк на долю, 2/4.\"\"\"" % RPB,
           "", "RPB = %d" % RPB, "BARS = %d" % bars,
           "TEMPO = %r" % [(round(b, 4), round(t, 2)) for b, t in M.tempo_map(tracks)],
           "CH = {}"]
    for ch, (src, tp, sus) in CHANNELS.items():
        ev = M.reduce_voice(tracks, src, 0, end, transpose=tp, rpb=RPB, sustain=sus, max_hold=1.0)
        text = M.to_mml(ev, RPB, BAR, 0, bars * BAR, instr=instr(ch))
        out.append("CH[%d] = %r" % (ch, text))
        print("канал %d: %d нот" % (ch, len(ev)))
    path = os.path.join(YP, "score", "data_sugarplum.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(path, bars, "тактов")


main()
