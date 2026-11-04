# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""Вивальди, «Времена года»: наборы Mutopia № 301, 336, 350, 351 (CC BY-SA 3.0) ->
score/data_vivaldi_<сезон>.py.

    python studio/importers/gen_vivaldi.py docs-external/notes-sources/vivaldi [сезон...]

Ноты и длительности - из MIDI набора (дорожки 1-5: скрипка соло, первые и
вторые скрипки, альты, виолончель с органом -> каналы 1-5). В MIDI нет
украшений и штрихов: трели, морденты, стаккато и пометки («Solo», «Canto
degli uccelli»...) берутся из партий LilyPond. Ноты партии LilyPond идут в том
же порядке, что начала нот дорожки MIDI (залигованные - одна нота), поэтому
k-я нота партии - это k-е начало в дорожке; высотные классы сверяются.

Трель - инструмент «<роль>_t1/_t2» (верхняя соседняя по ладу на 1 или 2
полутона), мордент - «_m1/_m2» (нижняя), тремоло («des2:32») - «_r32».
Стаккато - нота вдвое короче. Где у партии два голоса, сопоставление -
выравниванием (match).
"""
import os
import re
import sys

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, YP)
import midi2mml as M  # noqa: E402

# Сезон: файл MIDI части, префикс партий LilyPond, строк на долю, номер Mutopia
MOVEMENTS = {
    "spring": ("spring-score.mid", "spring1", 24, 301, "Весна (ор. 8 № 1, RV 269), I. Allegro"),
    "summer": ("summer-score-2.mid", "summer3", 4, 336, "Лето (ор. 8 № 2, RV 315), III. Presto"),
    "autumn": ("autumn-score.mid", "autumn1", 24, 350, "Осень (ор. 8 № 3, RV 293), I. Allegro"),
    "winter": ("winter-score.mid", "winter1", 8, 351,
               "Зима (ор. 8 № 4, RV 297), I. Allegro non molto"),
}
PARTS = ["", "a", "b", "c", "d"]            # суффиксы файлов партий -> дорожки 1-5
ROLES = ["solo", "vln1", "vln2", "viola", "basso"]

PC = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
ALT = {"": 0, "is": 1, "es": -1, "s": -1, "isis": 2, "eses": -2}
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]

TOK = re.compile(r'''
 (?P<str>[_^-]?"(?:[^"\\]|\\.)*")
|(?P<cmd>\\[a-zA-Z]+)
|(?P<sim><<|>>)
|(?P<chord><[^<>]*>(?:\d+\.*)?)
|(?P<note>(?<![A-Za-z])[a-g](?:isis|eses|is|es|s)?[',]*[!?]?(?:\d+\.*)?(?:\*\d+(?:/\d+)?)?(?![A-Za-z]))
|(?P<rest>(?<![A-Za-z])[rRs](?:\d+\.*)?(?:\*\d+(?:/\d+)?)?(?![A-Za-z]))
|(?P<tie>~)
|(?P<trem>:\d*)
|(?P<stacc>-[.|!])
|(?P<word>[A-Za-z]+)
|(?P<other>.)
''', re.X | re.S)
NOTE = re.compile(r"([a-g])(isis|eses|is|es|s)?")


def pclass(tok):
    m = NOTE.match(tok)
    return (PC[m.group(1)] + ALT[m.group(2) or ""]) % 12


def strip_scheme(text):
    """Убрать #(...) с вложенными скобками, #'символ, ##t"""
    out, i = [], 0
    while i < len(text):
        if text.startswith("#(", i):
            depth, j = 0, i + 1
            while j < len(text):
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
                if depth == 0:
                    break
            i = j
            continue
        out.append(text[i])
        i += 1
    text = "".join(out)
    return re.sub(r"##[tf]|#'[\w-]+", " ", text)


def ly_part(path):
    """Партия LilyPond -> (тональность (тоника, лад), начала нот [{pcs, flags,
    labels}]). Залигованное продолжение - не начало. В << ... >> берется первый
    голос в скобках (верхний), остальные пропускаются. Флаги: tr - трель,
    mord - мордент, st - стаккато, ("trem", n) - тремоло n-ми."""
    text = open(path, encoding="utf-8").read()
    text = re.sub(r"%\{.*?%\}", " ", text, flags=re.S)
    text = re.sub(r"%[^\n]*", " ", text)
    text = strip_scheme(text)
    text = re.sub(r"\\markup\s*\{([^{}]*)\}", r" \1 ", text)
    key = None
    m = re.search(r"\\key\s+([a-g](?:is|es|s)?)\s*\\(major|minor)", text)
    if m:
        key = (pclass(m.group(1)), m.group(2))
    onsets, pending = [], []
    last = None                  # последнее событие: dict начала или "rest"
    tied = False
    skip = 0                     # сколько следующих «слов/нот/строк» - аргументы команды
    depth = 0                    # глубина { }
    blocks = []                  # открытые << >>: [глубина, голосов закрыто]
    trem = 0
    for t in TOK.finditer(text):
        kind, val = t.lastgroup, t.group()
        if kind == "other" and val.isspace():
            continue
        if skip and kind in ("note", "word", "str", "cmd"):
            skip -= 1
            continue
        if kind == "sim":
            if val == "<<":
                blocks.append([depth, 0])
            elif blocks:
                blocks.pop()
            continue
        if kind == "other" and val in "{}":
            depth += 1 if val == "{" else -1
            if val == "}" and blocks and depth == blocks[-1][0]:
                blocks[-1][1] += 1
            continue
        if any(b[1] for b in blocks):
            continue             # второй и следующие голоса << >>
        if kind == "cmd":
            if val in ("\\key", "\\context"):
                skip = 2
            elif val in ("\\relative", "\\clef", "\\mark", "\\set", "\\bar", "\\version",
                         "\\transpose", "\\new"):
                skip = 1
            elif val in ("\\trill", "\\mordent") and isinstance(last, dict):
                last["flags"].add("tr" if val == "\\trill" else "mord")
            continue
        if kind == "trem":
            trem = int(val[1:]) if val[1:] else trem
            if isinstance(last, dict) and trem:
                last["flags"].add(("trem", trem))
            continue
        if kind == "str":
            s = val.lstrip("_^-").strip('"').strip()
            if s:
                if isinstance(last, dict):
                    last["labels"].append(s)
                else:
                    pending.append(s)
            continue
        if kind == "stacc":
            if isinstance(last, dict):
                last["flags"].add("st")
            continue
        if kind == "tie":
            tied = True
            continue
        if kind in ("note", "chord"):
            if kind == "note":
                pcs = {pclass(val)}
            else:
                pcs = {pclass(n) for n in re.findall(r"[a-g](?:isis|eses|is|es|s)?(?![a-z])",
                                                     val[1:val.index(">")])}
            if tied:
                tied = False
                continue         # продолжение лиги: начала в MIDI нет
            last = {"pcs": pcs, "flags": set(), "labels": pending}
            pending = []
            onsets.append(last)
        elif kind == "rest":
            tied = False
            last = "rest"
    return key, onsets


def midi_onsets(notes):
    """Начала нот дорожки: [(доля, [ноты])] по времени"""
    groups = {}
    for n in notes:
        groups.setdefault(round(n[0], 4), []).append(n)
    return sorted(groups.items())


def align(a, b):
    """Наибольшая общая подпоследовательность: a[i] (классы LilyPond) подходит к
    b[j] (классы начала MIDI), если входит в него. -> [(i, j)]"""
    n, m = len(a), len(b)
    L = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        Li, L1, ai = L[i], L[i + 1], a[i]
        for j in range(m - 1, -1, -1):
            Li[j] = L1[j + 1] + 1 if ai <= b[j] else max(L1[j], Li[j + 1])
    out, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] <= b[j] and L[i][j] == L[i + 1][j + 1] + 1:
            out.append((i, j))
            i += 1
            j += 1
        elif L[i + 1][j] >= L[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def match(path, onsets, notes):
    """Начала LilyPond -> доли начал MIDI. Обычно они совпадают один к одному.
    Там, где у партии два голоса (в LilyPond взят верхний, а в MIDI есть оба, и
    совпадающие высоты теряются), - выравнивание по высотным классам (align)"""
    mo = midi_onsets(notes)
    a = [frozenset(o["pcs"]) for o in onsets]
    b = [frozenset(n[2] % 12 for n in g) for _, g in mo]
    if len(a) == len(b) and all(x <= y for x, y in zip(a, b)):
        pairs = list(zip(range(len(a)), range(len(b))))
    else:
        pairs = align(a, b)
    out = [(mo[j][0], onsets[i]) for i, j in pairs]
    got = {id(x) for _, x in out}
    lost = [o for o in onsets if id(o) not in got and (o["flags"] - {"st"} or o["labels"])]
    if len(out) != len(onsets):
        print("  %s: сопоставлено %d из %d начал (в MIDI %d), без места украшений и пометок: %d" % (
            os.path.basename(path), len(out), len(onsets), len(mo), len(lost)))
    if len(out) < 0.95 * len(onsets):
        raise SystemExit("%s: партия LilyPond и дорожка MIDI не сходятся" % path)
    return out


def neighbour(p, scale, up):
    """Соседняя по ладу нота сверху/снизу: 1 или 2 полутона"""
    for d in (1, 2):
        if (p + (d if up else -d)) % 12 in scale:
            return d
    return 2


def min_len(evs, n):
    """Ноты не короче n строк (меньшая длительность в MML не пишется: при 24
    строках на долю 64-е - по 1.5 строки). Короткая нота сдвигает начало раньше
    за счет предыдущих, с конца: пассаж «...d32 cis d64 e f g» чуть ускоряется."""
    evs = [list(e) for e in evs]
    for i in range(len(evs) - 1, -1, -1):
        e = evs[i]
        if e[1] - e[0] >= n:
            continue
        e[0] = max(0, e[1] - n)
        if i and evs[i - 1][1] > e[0]:
            evs[i - 1][1] = e[0]
    return [tuple(e) for e in evs if e[1] > e[0]]


def convert(src, season):
    mid, ly, rpb, mut, title = MOVEMENTS[season]
    div, tracks = M.parse_midi(os.path.join(src, season, mid))
    time = [m for meta, _ in tracks for m in meta if m[0] == "time"]
    beats_bar = time[0][2] * 4 // time[0][3]
    tempo = M.tempo_map(tracks)[0][1]
    last = max(n[0] + n[1] for _, ns in tracks for n in ns)
    pickup_beats = last % beats_bar
    bars = int(round((last - pickup_beats) / beats_bar))
    pickup = int(round(pickup_beats * rpb))
    bar_rows = rpb * beats_bar
    total = pickup + bars * bar_rows

    key = None
    marks = {}                   # (дорожка, доля) -> флаги
    labels = []                  # (строка, канал, текст)
    for ch, suf in enumerate(PARTS):
        tr = ch + 1
        path = os.path.join(src, season, "%s-lys" % season, "%s%s.ly" % (ly, suf))
        k, onsets = ly_part(path)
        key = key or k
        for beat, o in match(path, onsets, tracks[tr][1]):
            if o["flags"]:
                marks[(tr, beat)] = o["flags"]
            for s in o["labels"]:
                labels.append((int(round(beat * rpb)), ch, s))
    tonic, mode = key
    scale = {(tonic + i) % 12 for i in (MAJOR if mode == "major" else MINOR)}

    out = ["# SPDX-License-Identifier: GPL-3.0-or-later",
           "# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio",
           '"""Сгенерировано gen_vivaldi.py: А. Вивальди, «Времена года» - %s.' % title,
           "Набор Mutopia № %d (Mutopia Project, CC BY-SA 3.0; музыка - общественное" % mut,
           "достояние). Сетка - %d строк на долю, %d/4%s.\"\"\"" % (
               rpb, beats_bar, ", затакт %d строк" % pickup if pickup else ""),
           "", "RPB = %d" % rpb, "BEATS = %d" % beats_bar, "BARS = %d" % bars,
           "PICKUP = %d" % pickup, "MIDI_TEMPO = %g" % tempo,
           "KEY = %r" % ("%s %s" % (M.NAMES[tonic], mode)),
           "# Пометки набора: (строка от начала, канал, текст)",
           "LABELS = %r" % sorted(labels),
           "# Затакт и основная часть по каналам",
           "CH0 = {}", "CH = {}"]
    stats = {}
    shortest = min(M._lengths(rpb))
    for ch in range(5):
        tr = ch + 1
        ev = M.reduce_voice(tracks, [(tr, "top")], 0, last + 1, rpb=rpb)
        evs = []
        for r0, r1, n, t, beat in ev:
            fl = marks.get((t, round(beat, 4)), set())
            if "st" in fl and r1 - r0 >= 2 * shortest:
                r1 = r0 + (r1 - r0) // 2
            evs.append((r0, r1, n, t, beat))
        evs = min_len(evs, shortest)

        def instr(e, ch=ch):
            fl = marks.get((e[3], round(e[4], 4)), set())
            p = e[2] + 12                       # нота compose -> MIDI
            if "tr" in fl:
                stats["tr"] = stats.get("tr", 0) + 1
                return "%s_t%d" % (ROLES[ch], neighbour(p, scale, True))
            if "mord" in fl:
                stats["mord"] = stats.get("mord", 0) + 1
                return "%s_m%d" % (ROLES[ch], neighbour(p, scale, False))
            trem = [f[1] for f in fl if isinstance(f, tuple) and f[0] == "trem"]
            if trem:
                stats["trem"] = stats.get("trem", 0) + 1
                return "%s_r%d" % (ROLES[ch], trem[0])
            return ROLES[ch]
        head = M.to_mml(evs, rpb, bar_rows, 0, pickup, instr=instr) if pickup else ""
        body = M.to_mml(evs, rpb, bar_rows, pickup, total, instr=instr)
        if pickup and not head.startswith("@"):
            head = "@%s %s" % (ROLES[ch], head)
        if not body.startswith("@"):
            body = "@%s %s" % (ROLES[ch], body)
        out.append("CH0[%d] = %r" % (ch, head))
        out.append("CH[%d] = %r" % (ch, body))
        print("  канал %d (%s): %d нот" % (ch + 1, ROLES[ch], len(evs)))
    path = os.path.join(YP, "score", "data_vivaldi_%s.py" % season)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("%s: %d тактов %d/4, затакт %d строк, %s, трелей %d, мордентов %d, тремоло %d -> %s" % (
        season, bars, beats_bar, pickup, "%s %s" % (M.NAMES[tonic], mode), stats.get("tr", 0),
        stats.get("mord", 0), stats.get("trem", 0), path))


def main():
    src = sys.argv[1]
    for season in sys.argv[2:] or list(MOVEMENTS):
        convert(src, season)


main()
