# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Скерцо-вальс (3-я часть симфонии) в «теплой» версии - для диска «Демо ЯЗС».

Ноты, фактура и темп - те же, что в m3_scherzo. Переделка - experiments/warm/warm.py:
мелодия и бас на октаву ниже, аккорды на две; полосы к НЧ и НЧ+СЧ; ударные без
D3. Своих нот здесь нет: правка m3_scherzo или warm.py меняет и эту версию
(checks.py увидит по сумме).
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "experiments", "warm"))

import warm  # noqa: E402


def song():
    return warm.load_warm("m3_scherzo")
