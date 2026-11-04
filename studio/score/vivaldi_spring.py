# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
А. Вивальди, «Времена года» (1725): концерт № 1 «Весна», ор. 8 № 1, RV 269,
I. Allegro. Переложение для ЯЗС.

Ноты - по набору Mutopia № 301 (data_vivaldi_spring.py, importers/gen_vivaldi.py).
Пять голосов струнного концерта ложатся на пять каналов один к одному
(common.baroque_strings): скрипка соло (D3, СЧ), первые скрипки (в тутти в
унисон с соло, расстройка - хорус), вторые скрипки, альты, виолончель с органом
(D3, НЧ). Трели и морденты - макрос арпеджио, piano - эффект BUS без D3.
Сетка 24 строки на долю: тремоло 32-ми («гром») и триоли шестнадцатых («молнии»).
Затакт - отдельный голос с нулевой строки, такты идут от строки PICKUP.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose import Song                                     # noqa: E402
import common                                                 # noqa: E402
import data_vivaldi_spring as D                               # noqa: E402

TEMPO = 104


def song():
    s = Song("ВЕСНА: I. ALLEGRO", "ВИВАЛЬДИ, ВРЕМЕНА ГОДА (1725)", bpm=TEMPO,
             rows_per_beat=D.RPB, beats_per_bar=D.BEATS, frame_bars=1)
    total = common.baroque_strings(s, D)

    br = s.bar_rows
    at = lambda bar: D.PICKUP + int(round(bar * br))
    s.ritard(at(D.BARS - 2), total - 1, TEMPO, 76, every=D.RPB)
    T = lambda bar, txt: s.text(at(bar), txt)
    T(0, "РИТОРНЕЛЛО: СОЛО И ПЕРВЫЕ СКРИПКИ В УНИСОН - ХОРУС")
    T(2.875, "ЭХО: PIANO СНИМАЕТ D3 У СОЛО И БАСА (ЭФФЕКТ BUS)")
    T(12.5, "ПЕНИЕ ПТИЦ: МОРДЕНТЫ И ТРЕЛИ - МАКРОС АРПЕДЖИО")
    T(30.125, "ЖУРЧАТ РУЧЬИ: ШЕСТНАДЦАТЫЕ ЛИГАМИ ПО ДВЕ")
    T(43.0625, "ГРОМ: ТРЕМОЛО 32-МИ, 24 СТРОКИ НА ДОЛЮ")
    T(46, "МОЛНИИ: ТРИОЛИ ШЕСТНАДЦАТЫХ У СКРИПКИ СОЛО")
    T(58, "СНОВА ПОЮТ ПТИЦЫ")
    T(75, "РИТОРНЕЛЛО: ТРЕЛЬ НАЧИНАЕТСЯ С ВЕРХНЕЙ НОТЫ")
    return s


if __name__ == "__main__":
    s = song()
    s.build()
    print(s.stats)
    for t in s.texts:
        assert len(t) <= 64, len(t)
