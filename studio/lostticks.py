# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Где плеер теряет тики: эмулятор играет мелодию и каждую секунду снимает
yazs.irqs (сколько раз ячейка взвела флаг таймера) и счетчик тиков плеера.
Разница по секундам - потерянные тики. ±1 соседних секунд - дрожание снимка;
потери в первые секунды у больших файлов - загрузка с диска (таймер уже идет).

    python studio/lostticks.py файл.yz|модуль [видов]     видов - сколько раз нажать ВВОД (смена вида)
"""

import os
import sys

import listen
import render


def main():
    src = sys.argv[1]
    views = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    out = os.path.join(render.OUT, "lost")
    os.makedirs(out, exist_ok=True)
    disk, info, stem = listen.make_disk(src, out)
    lines = ['MACHINE "agat/Agat-9-yazs.ext"', 'COMMAND fdd0.load("%s")' % disk.replace("\\", "/"),
             "RESET cold", "SPEED MAX", "WAIT 12000", "LOGDEFS 16,10", "KEY 100,100,ret", "WAIT 700"]
    lines += ["KEY 100,100,ret", "WAIT 300"] * views
    for _ in range(info["seconds"]):
        lines += ["LOG yazs.irqs", "LOG ram.value($1E,$1F)", "WAIT 1000"]
    lines.append("EXIT")
    text = render.run(lines, "lost_" + stem, out, timeout=3600)
    irq, tk = [], []
    for l in text.splitlines():
        if l.startswith("[yazs.irqs]"):
            irq.append(int(l.split()[-1]))
        elif l.startswith("[ram.value]"):
            v = [int(x) for x in l.split(":")[1].split()]
            tk.append(v[0] + 256 * v[1])
    base, full = 0, []
    for i, t in enumerate(tk):                 # счетчик плеера 16-битный
        if i and t < tk[i - 1] - 30000:
            base += 65536
        full.append(t + base)
    lost = [(irq[i + 1] - irq[i]) - (full[i + 1] - full[i]) for i in range(len(irq) - 1)]
    big = [(i, x) for i, x in enumerate(lost) if abs(x) > 1]
    print("%s: всего потеряно %d; секунды с потерями больше 1: %s" % (
        stem, sum(lost), " ".join("%d:%d" % p for p in big) or "нет"))


if __name__ == "__main__":
    main()
