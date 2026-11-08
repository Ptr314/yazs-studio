# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Стенд опыта встраиваемого плеера: эталон и прогон плееров на 6502.

Эталон (Reference) - модель движка studio/pyplay.py плюс то, что делает плеер
Студии после конца мелодии (ui.a65, et_tail): 100 тиков ноты отпускаются, потом
тишина во всех семи каналах.

Прогон (run_tune) - эмулятор 6502 конвертера SID (studio/sid/cpu6502.py), ячейка
ЯЗС в слоте 1 ($C090): чтение +0 сразу дает взведенный флаг таймера, так что
каждое чтение +0 - начало тика. Записи между двумя такими чтениями - один тик.

Сверка (compare) - по тикам, как множества записей (регистр, значение) в
счетчики, таймер и каналы; порядок записей внутри тика не важен (плата видит их
за доли миллисекунды). Отдельно - вход (режимы счетчиков, таймер, пуск) и выход.
"""

import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
STUDIO = os.path.join(ROOT, "studio")
if STUDIO not in sys.path:
    sys.path.insert(0, STUDIO)

import pyplay                   # noqa: E402
from sid import cpu6502         # noqa: E402

CARD = 0xC090
TAIL = 100                      # тиков хвоста (ui.a65: tail >= 100)
CHECKED = set(range(0, 15)) - {3, 7}     # счетчики 0-2, 4-5, таймер 6, каналы 8-14
COUNTERS = (0, 1, 2, 4, 5, 6)


class Reference(object):
    """init - записи до первого тика; ticks[k] - записи тика k (с хвостом);
    music_ticks - тиков до конца мелодии; exit - тишина плеера Студии"""

    def __init__(self, data):
        p = pyplay.Player(data)
        n0 = len(p.writes)
        self.init = [(a, v) for _, a, v in p.writes]
        while p.step():
            pass
        self.music_ticks = p.ticks
        for _ in range(TAIL):
            for ch in range(5):
                t = p.tone[ch]
                if t.state == 1:
                    t.state, t.regpos = 2, 0
                p.tone_tick(ch, t)
            p.ticks += 1
        self.ticks = [[] for _ in range(p.ticks)]
        for t, a, v in p.writes[n0:]:
            self.ticks[t].append((a, v))
        self.n = data[66]
        self.exit = [(a, 0) for a in range(8, 15)]


class Card(cpu6502.CPU6502):
    """6502 с ячейкой ЯЗС: журнал ("poll", такт) и ("w", регистр, значение, такт)"""

    def __init__(self, mem, image=None):
        cpu6502.CPU6502.__init__(self, mem)
        self.log = []
        self.image = image or (0, 0)
        self.zp = set()
        self.ram = set()
        self.min_sp = 0xFF

    def rd(self, a):
        if 0xC000 <= a <= 0xC0FF:
            if a == CARD:
                self.log.append(("poll", self.cycles))
                return 0x80
            return 0
        return self.m[a]

    def wr(self, a, v):
        if 0xC000 <= a <= 0xC0FF:
            if CARD <= a < CARD + 16:
                self.log.append(("w", a - CARD, v, self.cycles))
            return
        if a < 0x100:
            self.zp.add(a)
        elif a >= 0x200 and not (self.image[0] <= a < self.image[1]):
            self.ram.add(a)
        self.m[a] = v

    def push(self, v):
        cpu6502.CPU6502.push(self, v)
        self.min_sp = min(self.min_sp, self.sp)


def run_tune(binary, org, entry, limit=10 ** 9):
    """JSR entry; (журнал, ячейки нулевой страницы, ОЗУ, глубина стека, такты)"""
    mem = bytearray(65536)
    mem[org:org + len(binary)] = binary
    cpu = Card(mem, (org, org + len(binary)))
    cpu.sp = 0xFF
    cycles = cpu.call(entry, limit=limit)
    # call() кладет 2 байта возврата: глубина - сверх них
    return cpu.log, cpu.zp, cpu.ram, 0xFF - 2 - cpu.min_sp, cycles


def split(log):
    """(записи входа, записи по тикам, записи выхода, такты тиков)"""
    init, ticks, cyc = [], [], []
    cur = init
    last_poll = None
    exiting = False
    exitw = []
    for e in log:
        if e[0] == "poll":
            if exiting:
                raise ValueError("опрос флага после выхода")
            if last_poll is not None:
                cyc.append(e[1] - last_poll)
            last_poll = e[1]
            cur = []
            ticks.append(cur)
        else:
            _, a, v, _c = e
            if ticks and a == 15 and v == 0xC0:
                exiting = True
            if exiting:
                exitw.append((a, v))
            else:
                cur.append((a, v))
    return init, ticks, exitw, cyc


def checked(ws):
    return collections.Counter((a, v) for a, v in ws if a in CHECKED)


def compare(ref, log):
    """Список расхождений (пустой - совпало) и такты на тик (наибольшее, среднее)"""
    init, ticks, exitw, cyc = split(log)
    errs = []
    # Вход: режим 3 всем счетчикам до первой записи в них, таймер N, пуск
    mode = {}
    for a, v in init:
        if a in (3, 7) and (v & 0x30):
            mode[(v >> 6) + (0 if a == 3 else 4)] = (v >> 1) & 7
    for c in COUNTERS:
        if mode.get(c) != 3:
            errs.append("вход: счетчик %d не в режиме 3" % c)
    t = [v for a, v in init if a == 6]
    if t != [ref.n, 0]:
        errs.append("вход: таймер %s, ждали [%d, 0]" % (t, ref.n))
    f = [v for a, v in init if a == 15]
    if not f or f[0] != 0xC0 or f[-1] != 0x40:
        errs.append("вход: +F %s, ждали $C0 ... $40" % ["$%02X" % x for x in f])
    if any(a in CHECKED and a < 8 and a != 6 for a, v in init):
        errs.append("вход: запись в счетчик тона до первого тика")
    # Тики
    if len(ticks) != len(ref.ticks):
        errs.append("тиков %d, ждали %d" % (len(ticks), len(ref.ticks)))
    for k in range(min(len(ticks), len(ref.ticks))):
        a, b = checked(ticks[k]), checked(ref.ticks[k])
        if a != b:
            errs.append("тик %d: плеер %s, модель %s" % (k, sorted((a - b).elements()),
                                                         sorted((b - a).elements())))
            if len(errs) > 8:
                break
    # Выход: стоп счета, тишина
    if checked(exitw) != checked(ref.exit) or not exitw or exitw[0] != (15, 0xC0):
        errs.append("выход: %s" % exitw)
    stat = (max(cyc) if cyc else 0, sum(cyc) / float(len(cyc)) if cyc else 0)
    return errs, stat


def main():
    """python run6502.py файл.yz - только эталон: тики и записи"""
    for path in sys.argv[1:]:
        ref = Reference(open(path, "rb").read())
        print("%s: тиков %d (+%d хвост), записей %d" % (
            os.path.basename(path), ref.music_ticks, TAIL, sum(len(t) for t in ref.ticks)))


if __name__ == "__main__":
    main()
