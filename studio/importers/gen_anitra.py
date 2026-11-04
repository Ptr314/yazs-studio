"""Танец Анитры: MIDI набора Mutopia № 281 (общественное достояние) -> score/data_anitra.py.
    python studio/importers/gen_anitra.py anitrasdance.mid"""
import os
import sys

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, YP)
import midi2mml as M  # noqa: E402

RPB, BEATS_BAR = 16, 3
BAR = RPB * BEATS_BAR
CHANNELS = {
    0: [(1, "top")],                                  # первые скрипки (arco, с сурдиной)
    1: [(2, "top"), (3, "top")],                      # вторые скрипки, альты
    2: [(2, ("rankx", 1)), (4, "top"), (3, ("rankx", 1))],
    3: [(5, "top"), (4, "top"), (6, "top")],          # виолончели
    4: [(7, "bottom"), (6, "bottom"), (5, "bottom")],  # контрабасы
}


def main():
    div, tracks = M.parse_midi(sys.argv[1])
    last = max(n[0] + n[1] for _, ns in tracks for n in ns)
    bars = int(-(-last // BEATS_BAR))
    end = bars * BEATS_BAR
    out = ["# SPDX-License-Identifier: GPL-3.0-or-later",
           "# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio",
           '"""Сгенерировано: Э. Григ, Пер Гюнт, сюита 1, ор. 46 № 3 - Танец Анитры, по набору',
           "Mutopia № 281 (струнные и треугольник, общественное достояние). Сетка - %d строк" % RPB,
           'на долю, 3/4."""', "", "RPB = %d" % RPB, "BARS = %d" % bars, "CH = {}"]
    for ch, src in CHANNELS.items():
        ev = M.reduce_voice(tracks, src, 0, end, rpb=RPB)
        out.append("CH[%d] = %r" % (ch, M.to_mml(ev, RPB, BAR, 0, bars * BAR)))
        print("канал %d: %d нот" % (ch, len(ev)))
    # Треугольник: удары по началам нот дорожки 8
    tri = [(int(round(n[0] * RPB)), int(round((n[0] + n[1]) * RPB)), 0) for n in tracks[8][1]]
    out.append("TRIANGLE = %r" % [r for r, _, _ in tri])
    path = os.path.join(YP, "score", "data_anitra.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(path, bars, "тактов")


main()
