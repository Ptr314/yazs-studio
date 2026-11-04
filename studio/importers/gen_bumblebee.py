"""Полет шмеля: партия флейты (MIDI) -> score/data_bumblebee.py; гармония по долям
подбирается по нотам мелодии.
    python studio/importers/gen_bumblebee.py путь.mid [--show]"""
import os
import re
import sys

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, YP)
import midi2mml as M  # noqa: E402

RPB, BEATS_BAR = 8, 2
BAR = RPB * BEATS_BAR
CHORDS = {
    "Am": (9, 0, 4), "E7": (4, 8, 11, 2), "Dm": (2, 5, 9), "A7": (9, 1, 4, 7),
    "Bb": (10, 2, 5), "B7": (11, 3, 6, 9), "Gm": (7, 10, 2),
}
BIAS = {"Am": 0.8, "E7": 0.7, "Dm": 0.5, "A7": 0.3, "Bb": 0.2}
ROOT = {"Am": 9, "E7": 4, "Dm": 2, "A7": 9, "Bb": 10, "F": 5, "C": 0, "G7": 7, "D7": 2,
        "B7": 11, "Gm": 7, "E": 4}


def harmony(events, beats, per=2):
    """Аккорд на каждые per долей: по нотам с весом по метру, с запасом на
    удержание прошлого аккорда; -> по аккорду на долю"""
    out = []
    prev = None
    for b in range(0, beats, per):
        r0, r1 = b * RPB, (b + per) * RPB
        ws = []
        for e in events:
            if r0 <= e[0] < r1:
                pos = (e[0] - r0) % RPB
                w = 4 if pos == 0 else 2 if pos % 4 == 0 else 1 if pos % 2 == 0 else 0.5
                if e[0] == r0:
                    w = 6
                ws.append(((e[2] + 12) % 12, w))
        best = None
        for nm, pcs in CHORDS.items():
            sc = sum(w if pc in pcs else -0.6 * w for pc, w in ws) + BIAS.get(nm, 0)
            if nm == prev:
                sc += 3
            if best is None or sc > best[0]:
                best = (sc, nm)
        prev = best[1] if ws else (prev or "Am")
        out += [prev] * per
    return out[:beats]


def near(pc, ref):
    return min((n for n in range(ref - 6, ref + 7) if n % 12 == pc), key=lambda n: abs(n - ref))


def main():
    div, tracks = M.parse_midi(sys.argv[1])
    last = max(n[0] + n[1] for _, ns in tracks for n in ns)
    bars = int(-(-last // BEATS_BAR))
    beats = bars * BEATS_BAR
    mel = M.reduce_voice(tracks, [(1, "top")], 0, beats, transpose=-12, rpb=RPB)
    harm = harmony(mel, beats)
    harm[:10] = ["E7"] * 10            # вступление: нисходящий пассаж на доминанте
    if "--show" in sys.argv:
        for b in range(bars):
            print(b, harm[2 * b], harm[2 * b + 1])
    # Мелодия: лига между разными нотами (жужжание без нового удара)
    text = M.to_mml(mel, RPB, BAR, 0, bars * BAR)
    toks, octv, prev = [], None, None
    for t in text.split():
        if t[0] == "o" and t[1:].isdigit():
            octv = int(t[1:])
            toks.append(t)
            continue
        m = re.match(r"([a-g]#?)(\d+\.?)$", t)
        if m:
            pitch = (octv, m.group(1))
            toks.append(("_" if prev is not None and pitch != prev else "") + t)
            prev = pitch
            continue
        if t[0] == "r":
            prev = None
        toks.append(t)
    mel_text = " ".join(toks)

    # Аккомпанемент по долям
    def beat_notes(fn, length="8", rest="r8"):
        out = []
        for b, h in enumerate(harm):
            n = fn(b, h)
            out.append("o%d %s%s %s" % (n // 12, M.NAMES[n % 12], length, rest))
            if b % 2 == 1:
                out.append("|")
        return " ".join(out)

    third = lambda b, h: near(CHORDS[h][1], 45)           # терция около ля3
    fifth = lambda b, h: near(CHORDS[h][2], 50)           # квинта около ре4
    bass = lambda b, h: near(ROOT[h], 21) if b % 2 == 0 else near(CHORDS[h][2], 26)
    trem = lambda b, h: near(ROOT[h], 40)                 # корень около ми3
    ch1 = beat_notes(trem, "4", "")
    ch2 = beat_notes(fifth)
    ch3 = beat_notes(third)
    ch4 = beat_notes(bass)
    out = ["# SPDX-License-Identifier: GPL-3.0-or-later",
           "# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio",
           '"""Сгенерировано: Н. А. Римский-Корсаков, «Полет шмеля» (общественное',
           "достояние) - партия солиста; аккомпанемент по долям - аккорды, подобранные",
           "по мелодии (HARM). Сетка - %d строк на долю, 2/4.\"\"\"" % RPB,
           "", "RPB = %d" % RPB, "BARS = %d" % bars,
           "TEMPO = %r" % [(round(b, 4), round(t, 2)) for b, t in M.tempo_map(tracks)],
           "HARM = %r" % harm, "CH = {}",
           "CH[0] = %r" % mel_text, "CH[1] = %r" % ch1, "CH[2] = %r" % ch2,
           "CH[3] = %r" % ch3, "CH[4] = %r" % ch4]
    path = os.path.join(YP, "score", "data_bumblebee.py")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(path, bars, "тактов", len(mel), "нот")


main()
