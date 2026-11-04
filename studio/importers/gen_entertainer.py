"""The Entertainer: entertainer.ly (Mutopia, общественное достояние) ->
score/data_entertainer.py. python studio/importers/gen_entertainer.py путь.ly [--show N]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, YP)
import ly_parse as L   # noqa: E402
import midi2mml as M   # noqa: E402

RPB, BEATS_BAR = 4, 2
BAR = RPB * BEATS_BAR
# Повторы: A, B, C (трио), D; False - один раз
REPEATS = [True, True, False, True]
NM = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]


def var(text, name):
    i = text.index(name + " =")
    j = text.index("{", i)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[j + 1:k]
    raise ValueError(name)


def pseudo(ev, keep=lambda p: True):
    return ([], [(s, l, p, 64, 0) for s, l, ps in ev for p in ps if keep(p)])


def main():
    text = open(sys.argv[1], encoding="utf-8").read()
    top = L.unfold(L.parse(var(text, "top"), (0, 60)), REPEATS)
    bot = L.unfold(L.parse(var(text, "bottom"), (0, 48)), REPEATS)
    tev, tlen = L.events(top)
    bev, blen = L.events(bot)
    print("верх %.2f долей, низ %.2f долей" % (tlen, blen))
    if "--show" in sys.argv:
        n = int(sys.argv[sys.argv.index("--show") + 1])
        for s, l, ps in tev:
            if s < n * BEATS_BAR:
                print("В %6.2f %5.2f %s" % (s, l, "+".join("%s%d" % (NM[p % 12], p // 12 - 1) for p in ps)))
        for s, l, ps in bev:
            if s < n * BEATS_BAR:
                print("Н %6.2f %5.2f %s" % (s, l, "+".join("%s%d" % (NM[p % 12], p // 12 - 1) for p in ps)))
        return
    bars = int(round(max(tlen, blen) / BEATS_BAR))
    end = bars * BEATS_BAR
    # Левая рука страйдом: бас - нижняя нота события ниже соль3, аккорд - события
    # из 2+ нот не ниже ре3
    lh_bass = [(s, l, [min(ps)]) for s, l, ps in bev if min(ps) < 55]
    lh_chord = [(s, l, ps) for s, l, ps in bev if len(ps) >= 2 and min(ps) >= 50]
    tracks = [pseudo(tev), pseudo(lh_bass), pseudo(lh_chord)]
    chans = {
        0: [(0, "top")],
        1: [(0, ("rankx", 1))],
        2: [(2, "top")],
        3: [(2, ("rankx", 1))],
        4: [(1, "bottom")],
    }
    out = ["# SPDX-License-Identifier: GPL-3.0-or-later",
           "# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio",
           '"""Сгенерировано: С. Джоплин, The Entertainer (1902, общественное достояние),',
           "по набору Mutopia-2008/12/21-263 (общественное достояние). Повторы: %r." % REPEATS,
           "Сетка - %d строки на долю, 2/4.\"\"\"" % RPB, "",
           "RPB = %d" % RPB, "BARS = %d" % bars, "CH = {}"]
    for ch, src in chans.items():
        ev = M.reduce_voice(tracks, src, 0, end, rpb=RPB)
        out.append("CH[%d] = %r" % (ch, M.to_mml(ev, RPB, BAR, 0, bars * BAR)))
        print("канал %d: %d нот" % (ch, len(ev)))
    path = os.path.join(YP, "score", "data_entertainer.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(path, bars, "тактов")


main()
