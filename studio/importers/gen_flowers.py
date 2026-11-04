# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""Вальс цветов (Чайковский, «Щелкунчик»): клавир -> score/data_flowers.py.

    python studio/importers/gen_flowers.py каталог_расшифровки
    python studio/importers/gen_flowers.py каталог_расшифровки --show такт_от такт_до
    python studio/importers/gen_flowers.py каталог_расшифровки --compare nut7wltz.mid

Ноты - фортепианное переложение Jurgenson 1892 (IMSLP #57454, общественное достояние),
расшифровка сканов страниц 28-37 в тексте (flowers_text.py, формат - FORMAT.txt в
каталоге расшифровки). Повтор с вольтами (с. 30-31) разворачивается (UNFOLD),
неровные такты каденции ужимаются в 3/4 (SCALE), тремоло раскладывается на ноты,
форшлаг ставится на строку раньше главной ноты.

MIDI того же переложения (R. J. Stratton, Jr.) - только для сверки (--compare):
мелодия и бас по тактам, звуковысотные классы по долям. Он местами расходится с
изданием (октавные удвоения, другая хроматика, последние аккорды октавой выше):
спорное решает скан.

Левая рука делится на бас (нижняя нота на сильной доле или ниже ре малой октавы) и
аккомпанемент. Каналы:
- 1: верхний голос правой руки - мелодия;
- 2: второй голос правой руки, иначе третий звук аккомпанемента;
- 3, 4: аккомпанемент (вальсовые «па-па» на 2-ю и 3-ю доли);
- 5: бас.
Пассажи арфы (вступление и каденция) идут по кругу на каналы 1-4 и звенят до
следующей своей ноты: так звучит резонанс арфы. Инструменты - по разделам (SECTIONS).
"""
import glob
import os
import sys
from fractions import Fraction

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, YP)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import midi2mml as M  # noqa: E402
import flowers_text as FT  # noqa: E402

RPB, BEATS = 12, 3
BAR = RPB * BEATS
TICKS = 192                       # тиков на долю (как в MIDI набора)
GRID = TICKS // RPB               # 16 тиков - строка
NM = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Повтор: такты скана от и до (включительно), 1-я вольта, 2-я вольта
UNFOLD = [("30.1.1", "31.5.2", ["31.5.3", "31.5.4"], ["31.5.5", "31.5.6"])]
# Ноты мелодии, напечатанные на нижнем нотоносце (начало темы валторн A3-D4-F#4):
# такт скана -> [(доля, высота)] - из левой руки в правую
HAND_MOVES = {"30.1.5": [(0, "A3"), (1, "D4")], "30.3.4": [(0, "A3"), (1, "D4")],
              "30.4.1": [(0, "A3")],
              "34.1.4": [(0, "A3")], "34.1.8": [(0, "A3"), (1, "D4")],
              "34.3.6": [(0, "A3"), (1, "D4")], "34.4.3": [(0, "A3")],
              # переход перед репризой: верхний голос левой руки - мелодия виолончелей
              "34.1.1": [(0, "C#3"), (1, "A3"), (2, "D3")],
              "34.1.2": [(0, "A3"), (1, "D#3"), (2, "A3")],
              "34.1.3": [(0, "E3"), (1, "A3"), (2, "E#3")]}
# Правки расшифровки по сверке с MIDI и сканом: (такт скана, рука, доля, высота) -> высота.
# 36.3.2: бемоль у B5 в начале такта действует и на четвертой восьмой (так и в MIDI);
# средняя нота аккорда - между линией B2 и промежутком A2, по гармонии (D/F# под A-Bb-A
# мелодии) и MIDI - A2
SCAN_FIXES = {("36.3.2", "RH", Fraction(3, 2), "B5"): "Bb5", ("36.3.2", "LH", 1, "B2"): "A2"}
# Такты не в 3/4 (каденция ad lib., опечатка набора): во сколько раз ужать
SCALE = {"29.4.2": Fraction(3) / Fraction(7, 2), "28.2.3": Fraction(3) / Fraction(11, 4)}

# Разделы (такты с 1, включительно): инструменты каналов 1-5
SECTIONS = [
    (1, 15, "intro"), (16, 33, "cadenza"), (34, 37, "vamp"),
    (38, 44, "horn"), (45, 53, "clar"), (54, 60, "horn"), (61, 69, "clar"),
    (70, 101, "strings"),
    (102, 108, "horn"), (109, 117, "clar"), (118, 124, "horn"), (125, 133, "clar"),
    (134, 165, "strings"),
    (166, 195, "flute"), (196, 226, "cello"), (227, 238, "flute"), (239, 246, "strings"),
    (247, 249, "cello"),
    (250, 256, "horn"), (257, 265, "clar"), (266, 272, "horn"), (273, 281, "clar"),
    (282, 313, "strings"), (314, 345, "coda"), (346, 389, "tutti"),
]
ORCH = {   # раздел: инструменты каналов 1-5
    "intro": ["oboe", "clar2", "bassoon", "bassoon", "bassb"],
    "cadenza": ["harp", "harp", "harp", "harp", "harpb"],
    "vamp": ["horn", "horn2", "pizz", "pizz", "pizzb"],
    "horn": ["horn", "horn2", "pizz", "pizz", "pizzb"],
    "clar": ["clar", "horn2", "pizz", "pizz", "pizzb"],
    "strings": ["violin", "violin2", "pizz", "pizz", "pizzb"],
    "flute": ["flute", "oboe2", "pizz", "pizz", "pizzb"],
    "cello": ["cello", "violin2", "pizz", "pizz", "pizzb"],
    "coda": ["violin", "violin2", "horn2", "pizz", "pizzb"],
    "tutti": ["violin", "brass", "horn2", "pizz", "bassb"],
}
# Где пассажи - арфа: короткие ноты (до 1/4 доли) во вступлении, все ноты каденции
HARP_ZONES = [(1, 15, 0.26), (16, 33, 99)]


def section(bar):
    for a, b, name in SECTIONS:
        if a <= bar <= b:
            return name
    return SECTIONS[-1][2]


# --- расшифровка скана ---

def unfold(bars):
    labels = [b[0] for b in bars]
    out = list(labels)
    for a, b, v1, v2 in UNFOLD:
        if a not in labels:
            continue                     # сверка части страниц
        i, j = labels.index(a), labels.index(b)
        body = labels[i:j + 1]
        end = labels.index(v2[-1])
        out = labels[:i] + body + v1 + body + v2 + labels[end + 1:]
        labels = out
    by = {b[0]: b for b in bars}
    return [by[l] for l in out]


def scan_notes(folder):
    """Расшифровка -> (правая, левая рука): [(тик начала, тик конца, MIDI)], метки тактов"""
    paths = sorted(glob.glob(os.path.join(folder, "p*.txt")))
    parsed = FT.read(paths)
    done = set()
    for label, _, hs, _ in parsed:
        for (lab, hand, beat, old), new in SCAN_FIXES.items():
            if lab != label:
                continue
            po, pn = FT.pitch(old)[0], FT.pitch(new)[0]
            for i, (t0, d, ps) in enumerate(hs[hand]):
                if t0 == beat and any(q == po for q, _ in ps):
                    hs[hand][i] = (t0, d, [(pn if q == po else q, f) for q, f in ps])
                    done.add((lab, hand, beat, old))
    present = {b[0] for b in parsed}
    missed = [k for k in SCAN_FIXES if k not in done and k[0] in present]
    if missed:
        raise ValueError("SCAN_FIXES не применились: %r" % missed)
    for label, _, hs, _ in parsed:
        for beat, pname in HAND_MOVES.get(label, []):
            p = FT.pitch(pname)[0]
            for i, (t0, d, ps) in enumerate(hs["LH"]):
                if t0 == beat and any(q == p for q, _ in ps):
                    hs["LH"][i] = (t0, d, [x for x in ps if x[0] != p])
                    hs["RH"].append((t0, d, [(p, set())]))
                    break
            else:
                raise ValueError("HAND_MOVES: нет %s на доле %s в %s" % (pname, beat, label))
    bars = unfold(parsed)
    hands = {"RH": [], "LH": []}
    graces = {"RH": [], "LH": []}
    for k, (label, _, hs, _) in enumerate(bars):
        base = Fraction(k * BEATS)
        sc = SCALE.get(label, 1)
        for hand, evs in hs.items():
            for t0, d, ps in evs:
                t0, d = t0 * sc, d * sc
                trem = [int(f[1:]) for _, fl in ps for f in fl if f.startswith(":")]
                if d == 0:
                    graces[hand] += [(base + t0, p) for p, _ in ps]
                elif trem and d > Fraction(1, 2):
                    step = max(Fraction(1, 6), Fraction(4, trem[0]))    # 32-е - триолями 16-х
                    n = int(d / step)
                    for i in range(n):
                        p = ps[i % len(ps)][0]
                        hands[hand].append((base + t0 + i * step, step, p))
                else:
                    hands[hand] += [(base + t0, d, p) for p, _ in ps]
    out = []
    for hand in ("RH", "LH"):
        ns = {}
        snap = lambda b: int(round(b * TICKS / GRID)) * GRID
        for t0, d, p in hands[hand]:
            a = snap(t0)
            b = max(a + GRID, snap(t0 + d))
            ns[(a, p)] = max(ns.get((a, p), 0), b)
        for t, p in graces[hand]:
            main = snap(t)
            ns[(main - GRID, p)] = main
        out.append(sorted((a, b, p) for (a, p), b in ns.items()))
    return out[0], out[1], [b[0] for b in bars]


# --- MIDI для сверки ---

def quantize(notes):
    """Ноты дорожки MIDI (доли) -> [(тик начала, тик конца, MIDI)] на сетке строк.
    - раскатанный аккорд: нота не на сетке, а ранняя нота аккорда (на сетке, не
      раньше 42 тиков) еще звучит - начало переносится на нее;
    - форшлаг: нота короче 0.1 доли, за ней не позже 25 тиков долгая нота другой
      высоты - на строку раньше долгой;
    - остальное (пассажи 32-х) - к ближайшей строке."""
    snap = lambda t: int(round(t / GRID)) * GRID
    ns = sorted((int(round(n[0] * TICKS)), int(round((n[0] + n[1]) * TICKS)), n[2]) for n in notes)
    out = {}
    for t0, t1, p in ns:
        grace = [m for m in ns if 0 < m[0] - t0 <= 25 and m[1] - m[0] >= 77 and m[2] != p]
        if t1 - t0 < 19 and grace:
            main = snap(grace[0][0])
            a, b = main - GRID, main
        elif t0 % GRID:
            roll = [s for s in ns if s[0] % GRID == 0 and 0 < t0 - s[0] <= 42 and s[1] > t0 + 8]
            a = roll[-1][0] if roll else snap(t0)
            b = max(a + GRID, snap(t1))
        else:
            a, b = t0, max(t0 + GRID, snap(t1))
        out[(a, p)] = max(out.get((a, p), 0), b)
    return sorted((a, b, p) for (a, p), b in out.items())


def name(p):
    return "%s%d" % (NM[p % 12], p // 12 - 1)


def lines(rh, lh):
    """По тактам: мелодия (верхняя нота правой руки по началам) и бас (нижняя нота
    левой руки на сильной доле)"""
    bar_t = BEATS * TICKS
    mel, bass = {}, {}
    g = {}
    for t0, _, p in rh:
        g[t0] = max(g.get(t0, 0), p)
    for t0, p in g.items():
        mel.setdefault(t0 // bar_t, []).append((t0 % bar_t, p))
    for t0, _, p in lh:
        if t0 % bar_t == 0:
            b = t0 // bar_t
            bass[b] = min(bass.get(b, 999), p)
    return {b: sorted(v) for b, v in mel.items()}, bass


def compare(scan, midi, labels, first=1):
    """first - такт MIDI, с которого идет расшифровка (сверка части страниц)"""
    ms, bs = lines(*scan)
    mm, bm = lines(*midi)
    k = first - 1
    mm = {b - k: v for b, v in mm.items() if b >= k}
    bm = {b - k: v for b, v in bm.items() if b >= k}
    nb = max(max(ms), max(mm)) + 1
    print("тактов: скан %d, MIDI %d" % (max(ms) + 1, max(mm) + 1))
    bad_m = bad_b = 0
    for b in range(nb):
        lab = labels[b] if b < len(labels) else "?"
        a, c = set(ms.get(b, [])), set(mm.get(b, []))
        if a != c:
            bad_m += 1
            print("такт %3d (скан %-7s) мелодия: только скан %s | только MIDI %s" % (
                b + 1 + k, lab, " ".join("%g:%s" % (t / TICKS, name(p)) for t, p in sorted(a - c)),
                " ".join("%g:%s" % (t / TICKS, name(p)) for t, p in sorted(c - a))))
        if bs.get(b) != bm.get(b) and (b in bs or b in bm):
            bad_b += 1
            print("такт %3d (скан %-7s) бас: скан %s, MIDI %s" % (
                b + 1 + k, lab, name(bs[b]) if b in bs else "-", name(bm[b]) if b in bm else "-"))
    print("расхождений: мелодия %d тактов, бас %d тактов из %d" % (bad_m, bad_b, nb))
    chroma(scan, midi, labels, first)


def chroma(scan, midi, labels, first=1):
    """Звуковысотные классы обеих рук по долям: доли, где у скана есть класс, которого
    нет в MIDI, а в MIDI есть соседний на полутон, - знак альтерации, отнесенный не к
    той ноте (так нашелся кластер A#-B в такте 2 вместо A-B#). Решает скан: MIDI в
    таких местах и сам ошибается"""
    def by_beat(ns, shift):
        out = {}
        for t0, _, p in ns:
            out.setdefault(t0 // TICKS - shift, set()).add(p % 12)
        return out
    s = by_beat(scan[0] + scan[1], 0)
    m = by_beat(midi[0] + midi[1], (first - 1) * BEATS)
    bad = 0
    for beat in sorted(set(s) | set(m)):
        a, c = s.get(beat, set()), m.get(beat, set())
        if any((x + 1) % 12 in c - a or (x - 1) % 12 in c - a for x in a - c):
            bad += 1
            bar = beat // BEATS
            print("такт %3d (скан %-7s) доля %d: скан %s | MIDI %s" % (
                bar + first, labels[bar] if bar < len(labels) else "?", beat % BEATS + 1,
                " ".join(NM[x] for x in sorted(a)), " ".join(NM[x] for x in sorted(c))))
    print("долей с полутоновым расхождением: %d" % bad)


# --- раскладка по каналам ---

def split_lh(lh):
    """Левая рука -> (бас, аккомпанемент): нижняя нота на сильной доле или ниже D3"""
    groups = {}
    for n in lh:
        groups.setdefault(n[0], []).append(n)
    bass, acc = [], []
    for t0, g in sorted(groups.items()):
        g.sort(key=lambda n: n[2])
        low = g[0]
        if t0 % (BEATS * TICKS) == 0 or low[2] < 50:
            bass.append(low)
            acc += g[1:]
        else:
            acc += g
    return bass, acc


def as_track(ns):
    """Для midi2mml.reduce_voice: ([], [(доля, длина, MIDI, 64, 0)])"""
    return ([], [(t0 / TICKS, (t1 - t0) / TICKS, p, 64, 0) for t0, t1, p in ns])


def harp_split(notes, zones):
    """Ноты пассажей арфы -> отдельно (по кругу на каналы 1-4), остальные"""
    harp, rest = [], []
    for n in notes:
        bar = n[0] // (BEATS * TICKS) + 1
        z = [mx for a, b, mx in zones if a <= bar <= b]
        if z and (n[1] - n[0]) <= z[0] * TICKS:
            harp.append(n)
        else:
            rest.append(n)
    return harp, rest


def harp_events(harp, total_rows):
    """Пассаж по кругу на каналы 0-3, каждая нота звенит до следующей своей
    (не дольше двух долей). -> {канал: [(r0, r1, нота compose, 0, доля)]}"""
    chans = {c: [] for c in range(4)}
    seq = sorted({(t0, p) for t0, _, p in harp})
    for k, (t0, p) in enumerate(seq):
        chans[k % 4].append([t0 // GRID, None, p - 12])
    for c, evs in chans.items():
        for i, e in enumerate(evs):
            nxt = evs[i + 1][0] if i + 1 < len(evs) else total_rows
            e[1] = min(nxt, e[0] + 2 * RPB)
        chans[c] = [(a, b, n, 0, a / RPB) for a, b, n in evs]
    return chans


def merge(base, extra):
    """События канала + арфа: где арфа - ноты арфы, остальное - как было"""
    if not extra:
        return base
    out = []
    for e in base:
        if not any(a < e[1] and e[0] < b for a, b, _, _, _ in extra):
            out.append(e)
    return sorted(out + extra)


def show(rh, lh, b0, b1, labels):
    for b in range(b0 - 1, b1):
        lo, hi = b * BEATS * TICKS, (b + 1) * BEATS * TICKS
        for hname, ns in (("RH", rh), ("LH", lh)):
            ev = {}
            for t0, t1, p in ns:
                if lo <= t0 < hi:
                    ev.setdefault((t0 - lo, t1 - t0), []).append(name(p))
            print("%3d %-7s %s: %s" % (b + 1, labels[b] if b < len(labels) else "", hname, " | ".join(
                "%g %g %s" % (k[0] / TICKS, k[1] / TICKS, " ".join(v)) for k, v in sorted(ev.items()))))


def main():
    rh, lh, labels = scan_notes(sys.argv[1])
    if "--show" in sys.argv:
        i = sys.argv.index("--show")
        show(rh, lh, int(sys.argv[i + 1]), int(sys.argv[i + 2]), labels)
        return
    if "--compare" in sys.argv:
        div, tracks = M.parse_midi(sys.argv[sys.argv.index("--compare") + 1])
        assert div == TICKS, div
        first = int(sys.argv[sys.argv.index("--first") + 1]) if "--first" in sys.argv else 1
        compare((rh, lh), (quantize(tracks[1][1]), quantize(tracks[2][1])), labels, first)
        return

    bars = len(labels)
    total = bars * BAR
    harp_r, rh2 = harp_split(rh, HARP_ZONES)
    harp_l, lh2 = harp_split(lh, HARP_ZONES)
    bass, acc = split_lh(lh2)
    keys = ["RH", "ACC", "BASS"]
    tr = [as_track(rh2), as_track(acc), as_track(bass)]
    ix = {k: i for i, k in enumerate(keys)}
    sources = {
        0: [(ix["RH"], "top")],
        1: [(ix["RH"], ("rankx", 1)), (ix["ACC"], ("rankx", 2))],
        2: [(ix["ACC"], "top"), (ix["RH"], ("rankx", 2))],
        3: [(ix["ACC"], ("rankx", 1)), (ix["RH"], ("rankx", 3))],
        4: [(ix["BASS"], "bottom")],
    }
    harp = harp_events(harp_r + harp_l, total)

    def instr(ch):
        def f(ev):
            if ev[3] == "harp":
                return "harp"
            return ORCH[section(ev[0] // BAR + 1)][ch]
        return f

    out = ["# SPDX-License-Identifier: GPL-3.0-or-later",
           "# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio",
           '"""Сгенерировано gen_flowers.py: П. И. Чайковский, «Щелкунчик», Вальс цветов',
           "(сюита ор. 71a, № 8). Ноты - фортепианное переложение Jurgenson 1892 (IMSLP #57454,",
           "общественное достояние), расшифровка сканов с. 28-37, сверена с MIDI. Сетка - %d" % RPB,
           'строк на долю, 3/4."""',
           "", "RPB = %d" % RPB, "BARS = %d" % bars,
           "# Такт пьесы -> такт скана (страница.система.такт), повтор развернут",
           "SCAN = %r" % labels,
           "SECTIONS = %r" % SECTIONS, "CH = {}"]
    for ch, src in sources.items():
        ev = M.reduce_voice(tr, src, 0, bars * BEATS, rpb=RPB)
        ev = [(r0, r1, n, "x", b) for r0, r1, n, _, b in ev]
        if ch < 4:
            ev = merge(ev, [(a, b, n, "harp", bt) for a, b, n, _, bt in harp[ch]])
        text = M.to_mml(ev, RPB, BAR, 0, total, instr=instr(ch))
        out.append("CH[%d] = %r" % (ch, text))
        print("канал %d: %d нот" % (ch + 1, len(ev)))
    path = os.path.join(YP, "score", "data_flowers.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(path, bars, "тактов")


main()
