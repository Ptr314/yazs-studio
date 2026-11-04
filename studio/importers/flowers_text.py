# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""Разбор расшифровки клавира в тексте (формат - docs-external/notes-sources/flowers/FORMAT.txt):

    bar 28.1.1
    RH: 0 1 A3 C#4 E4 | 1 1 C#4 E4 A4 | 2 1 E4 A4 C#5
    LH: 0 1 A2 E3 A3 | ...

Событие: начало и длительность в четвертях от начала такта (дроби можно), высоты -
звучащие, C4 = до первой октавы. Длительность за конец такта - связка.

    read(файлы) -> [(метка такта, длина в долях, {"RH": [события], "LH": [...]}, комментарии)]
    events(такты) -> ноты [(доля начала, длительность, MIDI, рука, флаги)] от начала пьесы
"""
import re
from fractions import Fraction

PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACC = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}
PITCH = re.compile(r"^([A-G])(##|bb|#|b)?(-?\d)((?:tr|mord|arp|:\d+)*)$")


def num(s):
    return Fraction(s) if "/" in s else Fraction(s)


def pitch(tok):
    m = PITCH.match(tok)
    if not m:
        raise ValueError("высота %r" % tok)
    midi = 12 * (int(m.group(3)) + 1) + PC[m.group(1)] + ACC[m.group(2) or ""]
    flags = set(re.findall(r"tr|mord|arp|:\d+", m.group(4)))
    return midi, flags


def read(paths, beats=3):
    bars = []
    for path in paths:
        cur = None
        for ln, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                if cur is not None:
                    cur[3].append(line[1:].strip())
                continue
            if line.startswith("bar"):
                cur = [line.split()[1], Fraction(beats), {"RH": [], "LH": []}, []]
                bars.append(cur)
                continue
            m = re.match(r"(RH|LH)\s*:\s*(.*)$", line)
            if not m or cur is None:
                raise ValueError("%s:%d: не разобрать %r" % (path, ln, line))
            hand, body = m.groups()
            body = re.split(r"(?:^|\s)#", body)[0].strip()      # «#» после пробела - комментарий, C#4 - диез
            if body in ("-", ""):
                continue
            for ev in body.split("|"):
                parts = ev.split()
                if len(parts) < 3:
                    raise ValueError("%s:%d: событие %r" % (path, ln, ev))
                t0, d = num(parts[0]), num(parts[1])
                ps = [pitch(p) for p in parts[2:]]
                cur[2][hand].append((t0, d, ps))
    return bars


def events(bars, lengths=None):
    """Ноты от начала пьесы. lengths: {метка: доли} для тактов не в 3/4 (каденция)"""
    out = []
    pos = Fraction(0)
    for label, ln, hands, _ in bars:
        if lengths and label in lengths:
            ln = Fraction(lengths[label])
        for hand, evs in hands.items():
            for t0, d, ps in evs:
                for midi, flags in ps:
                    out.append((pos + t0, d, midi, hand, flags))
        pos += ln
    out.sort(key=lambda e: (e[0], e[2]))
    return out, pos


def check(bars, lengths=None):
    """Такты, где у руки нет звука на какой-то доле или события за пределами такта"""
    bad = []
    for label, ln, hands, _ in bars:
        if lengths and label in lengths:
            ln = Fraction(lengths[label])
        for hand, evs in hands.items():
            if any(t0 >= ln or t0 < 0 or d < 0 for t0, d, _ in evs):
                bad.append((label, hand, "начало вне такта"))
            cover = [False] * int(ln * 12)
            for t0, d, _ in evs:
                for k in range(int(t0 * 12), min(len(cover), int((t0 + d) * 12))):
                    cover[k] = True
            if evs and not all(cover):
                gaps = [i / 12 for i, c in enumerate(cover) if not c]
                bad.append((label, hand, "пусто на долях %s..%s" % (gaps[0], gaps[-1])))
    return bad
