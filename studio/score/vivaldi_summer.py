# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
А. Вивальди, «Времена года» (1725): концерт № 2 «Лето», ор. 8 № 2, RV 315,
III. Presto («Летняя гроза»). Переложение для ЯЗС.

Ноты - по набору Mutopia № 336 (data_vivaldi_summer.py, importers/gen_vivaldi.py),
голоса - common.baroque_strings. Сетка 4 строки на долю: шестнадцатая - строка
в 10 тиков, каждая повторная нота тремоло - новый удар (D4 = 0 на тик).
В тактах 51-54 у соло два голоса над выдержанным ре - взят верхний.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose import Song                                     # noqa: E402
import common                                                 # noqa: E402
import data_vivaldi_summer as D                               # noqa: E402

TEMPO = 150


def song():
    s = Song("ЛЕТО: III. PRESTO", "ВИВАЛЬДИ, ВРЕМЕНА ГОДА (1725)", bpm=TEMPO,
             rows_per_beat=D.RPB, beats_per_bar=D.BEATS, frame_bars=1)
    total = common.baroque_strings(s, D)

    br = s.bar_rows
    at = lambda bar: D.PICKUP + int(round(bar * br))
    s.ritard(at(D.BARS - 2), total - 1, TEMPO, 120, every=D.RPB)
    T = lambda bar, txt: s.text(at(bar), txt)
    T(0, "ЛЕТНЯЯ ГРОЗА: ТРЕМОЛО ШЕСТНАДЦАТЫХ У ВСЕХ ПЯТИ ГОЛОСОВ")
    T(4, "ПОВТОР НОТЫ - НОВЫЙ УДАР: D4 = 0 НА ОДИН ТИК")
    T(39.5, "ГРАД ПОБИВАЕТ КОЛОСЬЯ: ПАССАЖИ СКРИПКИ СОЛО")
    T(50, "СОЛО НАД ВЫДЕРЖАННЫМ РЕ")
    T(54, "ТУТТИ: ГАММЫ ВНИЗ У ВСЕХ СТРУННЫХ")
    T(96, "СОЛО: АРПЕДЖИО ПО ВСЕМ СТРУНАМ")
    T(119, "ТУТТИ: ГРОЗА ДО КОНЦА")
    return s


if __name__ == "__main__":
    s = song()
    s.build()
    print(s.stats)
    for t in s.texts:
        assert len(t) <= 64, len(t)
