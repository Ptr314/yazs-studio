# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""Проверка встраиваемого плеера (yz2asm.py): все, что берет нотный поток.

song() - пьеса на два тоновых канала и оба ударных: ноты и паузы, гейт,
CUT, заглушение, лиги, длинные ноты, повторы, транспозиция в начале, смена
темпа (SPEED и TEMPO), JUMP и BREAK. boom() и blip() - звуковые эффекты: только
ударные и один тон в третьем канале с другим темпом (свой N таймера). slide() и
vib() - движение высоты внутри ноты. checks.py собирает их в разных наборах:
у каждого набора свои возможности плеера."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose import Song, CMD_CUT, CMD_FX, EFFECTS          # noqa: E402
from instruments import add_standard, KIT6, KIT7             # noqa: E402


def song():
    s = Song("ПРОВЕРКА YZ2ASM", "НОТНЫЙ ПОТОК", bpm=120, rows_per_beat=4)
    add_standard(s)
    s.voice(0, "@organ {tr 12} o3 l8 [c e g e]2 | @pluck q4 l8 c d e f g a b > c < | "
               "q8 @piano l4 c _e _g r | {cut 3} l4 c c {cut 0} c c | "
               "@organ l1 c^1 | | l8 [c e g e]2 | l8 [c e g e]2 | "
               "l2 g g | l2 e e | r1 |")
    s.voice(1, "@bass o2 l4 [c g c g]2 | | @pedal l2 c g | l4 [c g]2 | "
               "@bass_hold l1 c | c | l4 [c g c g]2 | | l2 c c | l2 c c | r1 |")
    s.put(1, s.bar(3, 0.5), (CMD_CUT,))         # заглушить бас посреди ноты
    s.drums(5, "l8 [k r s r k k s r]9 l1 r r |", KIT6)
    s.drums(6, "l8 [h h h o]18 l1 r r |", KIT7)
    s.set_tempo(s.bar(4), 100)                  # SPEED и TEMPO посреди пьесы
    s.ctrl(s.bar(8, 2), "jump", 9)              # остаток кадра 8 не играется
    s.ctrl(s.bar(9, 3), "break", 0)             # и последней доли кадра 9
    return s


def boom():
    """Эффект: только ударные"""
    s = Song("ВЗРЫВ", "", bpm=150, rows_per_beat=4)
    s.drums(5, "l4 K r k r |", KIT6)
    s.drums(6, "l4 x r H r |", KIT7)
    return s


def blip():
    """Эффект: один тон в третьем канале, свой темп"""
    s = Song("СИГНАЛ", "", bpm=90, rows_per_beat=4)
    add_standard(s)
    s.voice(2, "@pluck o5 l16 c g > c r r r r r r r r r r r r r |")
    return s


def slide():
    """Лиги и DETUNE посреди ноты (период без удара, $F7), без TEMPO и ударных"""
    s = Song("СКОЛЬЖЕНИЕ", "", bpm=120, rows_per_beat=4)
    add_standard(s)
    s.voice(0, "@organ o4 l4 c _d _e r | l2 g g |")
    for i, det in enumerate((-4, -8, -12, -16)):
        s.put(0, s.bar(1) + 1 + i, (CMD_FX + EFFECTS["det"], det & 0xFF))
    return s


def vib():
    """Инструмент с вибрато: период каждый тик ($F7); после конца вибрато идет и
    на отпускании, поэтому собирается без хвоста (--no-tail)"""
    s = Song("ВИБРАТО", "", bpm=120, rows_per_beat=4)
    add_standard(s)
    s.voice(1, "@strings o4 l2 e g |")
    return s


if __name__ == "__main__":
    data = song().build()
    out = sys.argv[1] if len(sys.argv) > 1 else "test_embed.yz"
    open(out, "wb").write(data)
