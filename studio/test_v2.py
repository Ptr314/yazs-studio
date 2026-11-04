# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Проверка версии 2 формата на модели движка: каждая партитура score/*.py
собирается в v1 и в v2 (с маленькой основной частью, чтобы паттерны ушли в
блоки), и pyplay должен дать одни и те же записи в ячейку тик за тиком.

    python studio/test_v2.py [имя_модуля ...]
"""

import glob
import os
import sys

import build
import compose
import pyplay

HERE = os.path.dirname(os.path.abspath(__file__))


def writes(data):
    p = pyplay.Player(data)
    while p.step():
        pass
    return p.writes


def check(module, main_limit=300):
    s1 = build.load_score(module)
    d1 = s1.build()
    s2 = build.load_score(module)
    s2.version = 2
    s2.main_limit = main_limit
    d2 = s2.build()
    ver, main, blocks = compose.yz_info(d2)
    w1, w2 = writes(d1), writes(d2)
    ok = w1 == w2
    print("%-16s v1 %5d байт, v2 %5d байт (основная часть %5d, блоков %d): записей %d %s" % (
        module, len(d1), len(d2), main, blocks, len(w1), "совпадают" if ok else "РАСХОДЯТСЯ"))
    return ok


def main():
    mods = sys.argv[1:] or [os.path.splitext(os.path.basename(p))[0]
                            for p in sorted(glob.glob(os.path.join(HERE, "score", "*.py")))]
    bad = 0
    for m in mods:
        if m in ("common", "instruments") or m.startswith("data_"):
            continue
        bad += not check(m)
    print("расхождений: %d" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
