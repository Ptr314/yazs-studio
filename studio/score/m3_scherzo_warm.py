# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Скерцо-вальс (3-я часть симфонии) в «теплой» версии - для диска «Демо ЯЗС»: ниже и
темнее, ближе к звучанию демо НКЛ.

Своих нот здесь нет: партитура m3_scherzo переделывается, фактура, темп, огибающие и
эффекты высоты остаются как есть:
- мелодия и бас на октаву ниже, аккорды на две (SHIFT);
- полосы инструментов к НЧ и НЧ+СЧ: все/СЧ+ВЧ/СЧ -> НЧ+СЧ, ВЧ -> СЧ, НЧ+ВЧ -> НЧ (BUS);
  эффекты BUS в партитуре не тронуты;
- ударные без D3 (короче и тише);
- подписи на экране - под новые полосы и ударные.
Правка m3_scherzo меняет и эту версию (checks.py увидит по сумме).
"""

import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
import build  # noqa: E402
import tables  # noqa: E402
from compose import CMD_LEGATO  # noqa: E402

SHIFT = [(0, -12), (1, -12), (2, -24), (3, -24), (4, -12)]     # (канал, полутонов) на всю пьесу
BUS = {0: 0, 1: 2, 2: 6, 3: 6, 4: 4, 5: 4, 6: 6, 7: 6}          # полосы D0-D2 -> теплые
TEXTS = [("НЧ+СЧ+ВЧ", "НЧ+СЧ"), ("СЧ+ВЧ", "НЧ+СЧ"), (", D3 - ГРОМЧЕ", "")]


def song():
    s = build.load_score("m3_scherzo")
    for ch, d in SHIFT:
        for r, cmds in s.rows[ch].items():
            for i, c in enumerate(cmds):
                if c[0] == CMD_LEGATO:
                    n = c[1] + d
                    cmds[i] = (CMD_LEGATO, n)
                elif c[0] < 0x60:
                    n = c[0] + d
                    cmds[i] = (n,)
                else:
                    continue
                if not 0 <= n < 96:
                    raise ValueError("канал %d строка %d: нота %d" % (ch, r, n))
    for ins in s.instruments:
        ins.reg = [(v & ~7) | BUS[v & 7] for v in ins.reg]
        ins.rel = [(v & ~7) | BUS[v & 7] for v in ins.rel]
    for ch in (5, 6):
        for r, cmds in s.rows[ch].items():
            cmds[:] = [(c[0] & 0x07,) if c[0] < 0x60 else c for c in cmds]
    for a, b in TEXTS:
        a, b = tables.agat(a), tables.agat(b)
        s.texts = [t.replace(a, b) for t in s.texts]
    return s
