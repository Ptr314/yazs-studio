# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
А. Вивальди, «Времена года» (1725): концерт № 3 «Осень», ор. 8 № 3, RV 293,
I. Allegro («Праздник урожая»). Переложение для ЯЗС.

Ноты - по набору Mutopia № 350 (data_vivaldi_autumn.py, importers/gen_vivaldi.py),
голоса - common.baroque_strings. Сетка 24 строки на долю (триоли шестнадцатых);
64-е в концах пассажей не пишутся - пассаж чуть ускорен (gen_vivaldi.min_len).
Темп по пометкам набора: Allegro, «пьяный засыпает» - Piano e Larghetto,
в конце Allegro assai.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose import Song                                     # noqa: E402
import common                                                 # noqa: E402
import data_vivaldi_autumn as D                               # noqa: E402

TEMPO, LARGHETTO, ASSAI = 112, 54, 120
SLEEP, WAKE = 88.5, 105                  # такты (от 0) пометок Larghetto и Allegro assai


def song():
    s = Song("ОСЕНЬ: I. ALLEGRO", "ВИВАЛЬДИ, ВРЕМЕНА ГОДА (1725)", bpm=TEMPO,
             rows_per_beat=D.RPB, beats_per_bar=D.BEATS, frame_bars=1)
    total = common.baroque_strings(s, D)

    br = s.bar_rows
    at = lambda bar: D.PICKUP + int(round(bar * br))
    s.ritard(at(SLEEP - 1), at(SLEEP), TEMPO, 80, every=D.RPB)
    s.set_tempo(at(SLEEP), LARGHETTO)
    s.set_tempo(at(WAKE), ASSAI)
    s.ritard(at(D.BARS - 1), total - 1, ASSAI, 92, every=D.RPB)
    T = lambda bar, txt: s.text(at(bar), txt)
    T(0, "ПРАЗДНИК УРОЖАЯ: ТАНЦЫ И ПЕСНИ КРЕСТЬЯН")
    T(13, "СОЛО: ДВОЙНЫЕ НОТЫ - ВЗЯТА ВЕРХНЯЯ")
    T(31, "ПЬЯНЫЙ: ТРЕЛИ И СПОТЫКАЮЩИЕСЯ ПАССАЖИ СОЛО")
    T(56, "ТУТТИ: ТАНЕЦ ПРОДОЛЖАЕТСЯ")
    T(66.5, "СНОВА ПЬЯНЫЙ: ТРИОЛИ ШЕСТНАДЦАТЫХ")
    T(SLEEP, "ПЬЯНЫЙ ЗАСЫПАЕТ: LARGHETTO - НОВЫЕ SPEED И TEMPO")
    T(WAKE, "ALLEGRO ASSAI: ПРАЗДНИК ДО КОНЦА")
    return s


if __name__ == "__main__":
    s = song()
    s.build()
    print(s.stats)
    for t in s.texts:
        assert len(t) <= 64, len(t)
