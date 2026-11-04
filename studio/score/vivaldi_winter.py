# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
А. Вивальди, «Времена года» (1725): концерт № 4 «Зима», ор. 8 № 4, RV 297,
I. Allegro non molto. Переложение для ЯЗС.

Ноты - по набору Mutopia № 351 (data_vivaldi_winter.py, importers/gen_vivaldi.py),
голоса - common.baroque_strings. Сетка 8 строк на долю: 32-я - строка.
«Дрожь» - повторные восьмые, голоса входят снизу. Тремоло 32-ми у соло
(«des2:32», «стучат зубы») - инструмент с повторным ударом в макросе регистра:
D4 = 0 на тик раз в строку.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose import Song                                     # noqa: E402
import common                                                 # noqa: E402
import data_vivaldi_winter as D                               # noqa: E402

TEMPO = 88


def song():
    s = Song("ЗИМА: I. ALLEGRO NON MOLTO", "ВИВАЛЬДИ, ВРЕМЕНА ГОДА (1725)", bpm=TEMPO,
             rows_per_beat=D.RPB, beats_per_bar=D.BEATS, frame_bars=1)
    total = common.baroque_strings(s, D, trem=s.speed * D.RPB // 8)

    br = s.bar_rows
    at = lambda bar: D.PICKUP + int(round(bar * br))
    s.ritard(at(D.BARS - 2), total - 1, TEMPO, 66, every=D.RPB)
    T = lambda bar, txt: s.text(at(bar), txt)
    T(0, "ДРОЖЬ ОТ ХОЛОДА: ПОВТОРЫ ВОСЬМЫХ, ГОЛОСА ВХОДЯТ СНИЗУ")
    T(11, "УЖАСНЫЙ ВЕТЕР: ПАССАЖИ 32-МИ У СКРИПКИ СОЛО")
    T(21.5, "БЕГАТЬ И ТОПАТЬ НОГАМИ ОТ ХОЛОДА: ТРЕЛИ")
    T(32.5, "ВЕТРЫ: ПАССАЖИ У ВИОЛОНЧЕЛИ")
    T(46, "СТУЧАТ ЗУБЫ: ТРЕМОЛО - ПОВТОРНЫЙ УДАР В МАКРОСЕ")
    T(55, "ТУТТИ: ДРОЖЬ ДО КОНЦА")
    return s


if __name__ == "__main__":
    s = song()
    s.build()
    print(s.stats)
    for t in s.texts:
        assert len(t) <= 64, len(t)
