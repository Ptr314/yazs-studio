# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
П. И. Чайковский, «Щелкунчик» (1892): Вальс цветов (сюита ор. 71a, № 8).
Переложение для ЯЗС.

Ноты - фортепианное переложение Jurgenson 1892 (data_flowers.py,
importers/gen_flowers.py): правая рука - мелодия и второй голос, левая - бас на
сильную долю и вальсовые «па-па». Оркестровка своя, по партитуре Чайковского:
вступление деревянных с пассажами арфы, каденция арфы (ноты по кругу на четыре
канала - каждая звенит, пока канал не возьмет следующую), тема валторн с ответами
кларнета, тема скрипок, средняя часть флейты и гобоя, тема виолончелей, реприза,
кода тутти. D3 - только у мелодии и баса. Сетка 12 строк на долю: шестнадцатые,
их триоли и секстоли арфы.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose import Song                                     # noqa: E402
from instruments import HF, MF, LF, LOUD, HIT, HOLD           # noqa: E402
import data_flowers as D                                      # noqa: E402

TEMPO = 168
CADENZA_END = 34                         # такт «a tempo» после каденции


def song():
    s = Song("ВАЛЬС ЦВЕТОВ", "ЧАЙКОВСКИЙ, ЩЕЛКУНЧИК (1892)", bpm=TEMPO,
             rows_per_beat=D.RPB, beats_per_bar=3, frame_bars=1)
    I = s.instrument
    # Мелодия (D3). Без ВЧ: на СЧ+ВЧ центр спектра C6 ~2 кГц и 23% энергии выше
    # 3 кГц - пронзительно; одна СЧ при той же громкости - ~1.1 кГц и 1% (measure.py)
    I("oboe", "ГОБОЙ", [HOLD | HIT | LOUD | MF, HOLD | LOUD | MF], vib=(16, 5, 2), meter=(13, 12, 1))
    I("horn", "ВАЛТОРНА", [HOLD | HIT | LOUD | LF | MF, HOLD | LOUD | LF | MF], vib=(20, 4, 1), meter=(14, 12, 2))
    I("clar", "КЛАРНЕТ", [HOLD | HIT | LOUD | LF, HOLD | LOUD | LF], vib=(18, 4, 1), meter=(13, 11, 2))
    I("violin", "СКРИПКИ", [HOLD | HIT | LOUD | MF, HOLD | LOUD | MF], vib=(14, 5, 2), meter=(13, 12, 1))
    I("flute", "ФЛЕЙТА", [HOLD | HIT | LOUD | MF, HOLD | LOUD | MF], vib=(16, 5, 2), meter=(12, 11, 1))
    I("cello", "ВИОЛОНЧ.", [HOLD | HIT | LOUD | LF, HOLD | LOUD | LF], vib=(14, 5, 2), meter=(13, 12, 1))
    # Средние голоса (без D3)
    I("clar2", "КЛАРНЕТ", [HOLD | HIT | LF | MF, HOLD | LF | MF], meter=(10, 9, 1))
    I("oboe2", "ГОБОЙ", [HOLD | HIT | MF | HF, HOLD | MF | HF], vib=(16, 5, 2), meter=(10, 9, 1))
    I("bassoon", "ФАГОТ", [HOLD | HIT | LF, HOLD | LF], meter=(10, 9, 1))
    I("horn2", "ВАЛТОРНЫ", [HOLD | HIT | LF, HOLD | LF], meter=(10, 9, 1))
    I("violin2", "СКРИПКИ", [HOLD | HIT | MF, HOLD | MF], vib=(16, 5, 2), meter=(10, 9, 1))
    I("brass", "МЕДЬ", [HOLD | HIT | LF | MF | HF, HOLD | LF | MF | HF], vib=(20, 4, 1), meter=(12, 11, 2))
    I("pizz", "ПИЦЦ.", [HIT | LF | MF], meter=(10, 0, 12))
    I("harp", "АРФА", [HIT | LF | MF], meter=(12, 0, 8))
    # Бас (D3)
    I("pizzb", "ПИЦЦ.", [HIT | LOUD | LF], meter=(13, 0, 10))
    I("bassb", "КОНТРАБ.", [HOLD | HIT | LOUD | LF, HOLD | LOUD | LF], meter=(13, 11, 2))

    total = D.BARS * s.bar_rows
    for c in range(5):
        end = s.voice(c, D.CH[c], octave=4, length=4)
        assert end == total, (c, end, total)

    br = s.bar_rows
    at = lambda bar: (bar - 1) * br      # такты с 1, как в SECTIONS
    s.ritard(at(28), at(CADENZA_END) - 1, TEMPO, 120, every=D.RPB)
    s.set_tempo(at(CADENZA_END), TEMPO)
    s.ritard(at(D.BARS - 2), total - 1, TEMPO, 132, every=D.RPB)
    T = lambda bar, txt: s.text(at(bar), txt)
    T(1, "ВСТУПЛЕНИЕ: АККОРДЫ ДЕРЕВЯННЫХ, ПАССАЖИ АРФЫ")
    T(16, "КАДЕНЦИЯ АРФЫ: НОТЫ ПО КРУГУ НА 4 КАНАЛА - ЗВЕНЯТ")
    T(34, "ВАЛЬС: БАС НА РАЗ, ПИЦЦИКАТО НА ДВА-ТРИ")
    T(38, "ТЕМА ВАЛТОРН: НЧ+СЧ С D3")
    T(45, "ОТВЕЧАЕТ КЛАРНЕТ: ПОЛОСА НЧ")
    T(70, "ТЕМА СКРИПОК: СЧ+ВЧ С D3 И ВИБРАТО")
    T(102, "СНОВА ВАЛТОРНЫ И КЛАРНЕТ")
    T(166, "СРЕДНЯЯ ЧАСТЬ: ФЛЕЙТА И ГОБОЙ")
    T(196, "ТЕМА ВИОЛОНЧЕЛЕЙ: ПОЛОСА НЧ С D3")
    T(250, "РЕПРИЗА: ВАЛТОРНЫ")
    T(282, "ТЕМА СКРИПОК")
    T(314, "КОДА")
    T(346, "ТУТТИ: СКРИПКИ, МЕДЬ, ВАЛТОРНЫ")
    return s


if __name__ == "__main__":
    s = song()
    s.build()
    print(s.stats)
    for t in s.texts:
        assert len(t) <= 64, len(t)
