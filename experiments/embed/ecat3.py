# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Встраиваемый плеер в eCat3 (консольная сборка, studio/render.py): «игра» из
report.py (out/embed/build/game_<вариант>.bin, с $4000) - единственный
защищенный файл на копии disk/template840.dsk, ее запускает «Быстропускалка».
Драйвер в начале образа зовет tune_01..tune_NN подряд.

Сценарий каждые 100 мс снимает yazs.irqs (сколько раз взводился флаг таймера -
номер тика), yazs.regs ($8-$E) и yazs.counters. Снимок сверяется с моделью после
тика irqs-1 или irqs-2 (снимок мог попасть внутрь тика); между мелодиями - с
тишиной. Пишет и WAV всей игры (для прослушивания).

    python experiments/embed/ecat3.py D [A ...] [--no-wav]
"""

import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run6502              # noqa: E402
import variants             # noqa: E402

import mkdisk840            # noqa: E402  (studio/ - в sys.path через variants)
import render               # noqa: E402

ROOT = variants.ROOT
OUT = os.path.join(ROOT, "out", "embed")
TEMPLATE = os.path.join(ROOT, "disk", "template840.dsk")
STEP_MS = 100


def make_disk(binary, path):
    disk = mkdisk840.Disk840(open(TEMPLATE, "rb").read())
    if any(n == "SOUNDTEST" for _, n, _ in disk.listing()):
        disk.delete("SOUNDTEST")
    disk.set_volume("ЯЗС-ИГРА")
    disk.add("ЯЗС-ИГРА", mkdisk840.T_BIN, mkdisk840.b_body(variants.ORG, binary), locked=True)
    with open(path, "wb") as f:
        f.write(bytes(disk.d))


def timeline(refs):
    """Состояние после каждого тика всей игры: (регистры 8-14, периоды 1-5);
    концы мелодий в тиках"""
    states, ends = [], []
    regs = [0] * 7
    per = [None] * 5
    phase = {a: 0 for a in variants.CNT}
    lo = {}
    for ref in refs:
        regs = [0] * 7
        for ws in ref.ticks:
            for a, v in ws:
                if 8 <= a <= 14:
                    regs[a - 8] = v
                elif a in variants.CNT:
                    if phase[a] == 0:
                        lo[a] = v
                    else:
                        per[variants.CNT.index(a)] = lo[a] | (v << 8)
                    phase[a] ^= 1
            states.append((tuple(regs), tuple(per)))
        ends.append(len(states))
    return states, ends


def script(disk, wav, seconds):
    lines = ['MACHINE "agat/Agat-9-yazs.ext"',
             'COMMAND fdd0.load("%s")' % disk.replace("\\", "/"),
             "RESET cold",
             "SPEED MAX",
             "LOGDEFS 8,16"]
    if wav:
        lines.append('COMMAND sound.record("%s")' % os.path.basename(wav))
    for _ in range(seconds * 1000 // STEP_MS):
        lines += ["WAIT %d" % STEP_MS, "LOG yazs.irqs", "LOG yazs.regs($8,$E)", "LOG yazs.counters"]
    if wav:
        lines.append("COMMAND sound.record()")
    lines.append("EXIT")
    return lines


def parse(out):
    vals = {"irqs": [], "regs": [], "counters": []}
    for line in out.splitlines():
        m = re.match(r"\[yazs\.(irqs|regs|counters)\](.*)", line)
        if m:
            text = m.group(2)
            if m.group(1) == "regs":
                text = text.split(":", 1)[1]            # "$0008: ..." - адрес первого
            vals[m.group(1)].append([int(x, 16) for x in re.findall(r"\$([0-9A-Fa-f]+)", text)])
    return list(zip(vals["irqs"], vals["regs"], vals["counters"]))


def check(samples, states, ends):
    """(совпали, внутри тика, между мелодиями, расходятся, первые расхождения).
    Совпали - весь снимок равен модели после тика irqs-1 или irqs-2. Внутри тика -
    каждый канал по отдельности равен модели после одного из этих тиков, причем
    период может отставать от регистра на тик: снимок попал между записями тика,
    или новый период в режиме 3 еще не вступил (yazs.counters - период в
    действии, он меняется в конце полупериода тона). Так же сверяет verify.py"""
    ok = bad = between = mid = 0
    first = []
    silent = (0,) * 7

    def per_ok(q, c):
        return q is None or q == c or c == 0

    for (irq,), regs, cnt in samples:
        if irq == 0:
            continue
        regs = tuple(regs[:7])
        per = tuple(cnt[:5])
        cands = [g for g in (irq - 1, irq - 2) if 0 <= g < len(states)]
        if any(states[g][0] == regs and all(per_ok(q, c) for q, c in zip(states[g][1], per))
               for g in cands):
            ok += 1
            continue
        if regs == silent and (irq in ends or irq >= len(states)):
            between += 1
            continue
        chan_ok = True
        for c in range(7):
            opts = []
            for g in cands:
                opts.append((states[g][0][c], states[g][1][c] if c < 5 else None))
                if g >= 1 and c < 5:
                    opts.append((states[g][0][c], states[g - 1][1][c]))
            if not any(r == regs[c] and (c >= 5 or per_ok(p, per[c])) for r, p in opts):
                chan_ok = False
        if chan_ok:
            mid += 1
        else:
            bad += 1
            if len(first) < 5:
                first.append("irqs %d: регистры %s периоды %s; модель %s" % (
                    irq, regs, per, [states[g] for g in cands]))
    return ok, mid, between, bad, first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--no-wav", action="store_true")
    args = ap.parse_args()
    files = sorted(glob.glob(os.path.join(OUT, "alice", "Alice_In_Wonderland.*.yz")))
    yzs = variants.load_set(files)
    refs = [run6502.Reference(y.d) for y in yzs]
    states, ends = timeline(refs)
    seconds = int(len(states) * yzs[0].n / 7980.0) + 15
    for v in args.variants:
        g = variants.compile_game(v, yzs, refs)
        binary, sym = variants.assemble(g, os.path.join(OUT, "build"), "game_" + v)
        wd = os.path.join(OUT, "ecat3_" + v)
        os.makedirs(wd, exist_ok=True)
        disk = os.path.join(wd, "game_%s.dsk" % v)
        make_disk(binary, disk)
        wav = None if args.no_wav else os.path.join(wd, "game_%s.wav" % v)
        out = render.run(script(disk, wav, seconds), "game_" + v, wd, timeout=3600)
        samples = parse(out)
        last = samples[-1][0][0] if samples else 0
        ok, mid, between, bad, first = check(samples, states, ends)
        print("%s: снимков %d, совпали %d, внутри тика %d, между мелодиями %d, расходятся %d; "
              "тиков по флагу %d, по модели %d" % (v, len(samples), ok, mid, between, bad, last,
                                                  len(states)))
        for f in first:
            print("    " + f)
        if wav:
            print("    WAV: %s" % wav)


if __name__ == "__main__":
    main()
