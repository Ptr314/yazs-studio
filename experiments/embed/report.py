# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Замеры вариантов встраиваемого плеера на наборе мелодий (README.md рядом).

    python experiments/embed/report.py [файлы.yz...] [--only A,D] [--quick] [--md отчет.md]

Без файлов - 11 мелодий Alice in Wonderland из out/embed/alice (их делает
studio/sid2yz.py, README.md). Для каждого варианта:
- игра со всеми мелодиями: плеер, общие данные, мелодии; каждая мелодия
  проигрывается на 6502 (run6502.py) и сверяется с моделью тик в тик;
- игра с одной мелодией - для каждой мелодии отдельно (--quick - без них).
Тексты игр, листинги и образы - в out/embed/build/.
"""

import argparse
import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run6502              # noqa: E402
import variants             # noqa: E402

ROOT = variants.ROOT
OUT = os.path.join(ROOT, "out", "embed")
ALICE = os.path.join(OUT, "alice", "Alice_In_Wonderland.*.yz")


def verify(game, refs, label):
    """Все мелодии игры на 6502 против модели: (ошибки, такты макс., ср., zp, ram, стек)"""
    errs, cmax, cavg, zp, ram, stack = [], 0, [], set(), set(), 0
    for k, ref in enumerate(refs):
        entry = game.sym["tune_%02d" % (k + 1)]
        log, z, r, st, _ = run6502.run_tune(game.binary, variants.ORG, entry)
        e, (mx, av) = run6502.compare(ref, log)
        if e:
            errs.append("%s, мелодия %d: %s" % (label, k + 1, "; ".join(e[:4])))
        cmax = max(cmax, mx)
        cavg.append(av)
        zp |= z
        ram |= r
        stack = max(stack, st)
    return errs, cmax, sum(cavg) / len(cavg), len(zp), len(ram), stack


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--only", default=",".join(variants.VARIANTS))
    ap.add_argument("--quick", action="store_true", help="без игр с одной мелодией")
    ap.add_argument("--md", help="записать таблицы в файл Markdown")
    args = ap.parse_args()
    files = args.files or sorted(glob.glob(ALICE))
    if not files:
        sys.exit("нет мелодий: python studio/sid2yz.py docs-external/sid-examples/"
                 "Alice_In_Wonderland.sid --all --out out/embed/alice")
    yzs = variants.load_set(files)
    refs = [run6502.Reference(y.d) for y in yzs]
    names = [y.name for y in yzs]
    short = [n.rsplit(".", 1)[-1] if "." in n else n for n in names]
    build = os.path.join(OUT, "build")
    res = {}
    for v in args.only.split(","):
        t0 = time.time()
        g = variants.compile_game(v, yzs, refs)
        variants.assemble(g, build, "game_" + v)
        sz = variants.sizes(g)
        errs, cmax, cavg, zp, ram, stack = verify(g, refs, v)
        single = []
        if not args.quick:
            for k in range(len(yzs)):
                g1 = variants.compile_game(v, [yzs[k]], [refs[k]])
                variants.assemble(g1, build, "one_%s_%02d" % (v, k + 1))
                s1 = variants.sizes(g1)
                e1 = verify(g1, [refs[k]], "%s отдельно" % v)[0]
                errs += e1
                single.append(s1["code"] + s1["shared"] + s1["tunes"][0])
        # первые k мелодий в игре (k = 1..N): итог и сверка
        prefix = []
        if not args.quick:
            for kk in range(1, len(yzs) + 1):
                gp = variants.compile_game(v, yzs[:kk], refs[:kk])
                variants.assemble(gp, build, "first_%s_%02d" % (v, kk))
                sp = variants.sizes(gp)
                errs += verify(gp, refs[:kk], "%s, первые %d" % (v, kk))[0]
                prefix.append(sp["code"] + sp["shared"] + sum(sp["tunes"]))
        # без хвоста: только размер
        gn = variants.compile_game(v, yzs, refs, tail=False)
        variants.assemble(gn, build, "notail_" + v)
        szn = variants.sizes(gn)
        res[v] = dict(sz=sz, errs=errs, cmax=cmax, cavg=cavg, zp=zp, ram=ram, stack=stack,
                      single=single, prefix=prefix, calc=g.calc, notail=szn, game=g)
        print("%-3s %5.1f с: код %d, общие %d, мелодии %d, %s" % (
            v, time.time() - t0, sz["code"], sz["shared"], sum(sz["tunes"]),
            "сверка: все %d совпали" % len(yzs) if not errs else "РАСХОЖДЕНИЯ: %d" % len(errs)))
        for e in errs[:10]:
            print("    " + e)
    lines = tables(res, short, yzs, refs)
    print()
    print("\n".join(lines))
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def tables(res, short, yzs, refs):
    vs = list(res)
    out = []
    out.append("Данные мелодий, байт (со входом `jsr yzplay`, 3 байта; без кода плеера и общих данных):")
    out.append("")
    out.append("| Мелодия | .YZ | " + " | ".join(vs) + " | D1 (расчет) | F (код) |")
    out.append("|---|---|" + "---|" * len(vs) + "---|---|")
    fcalc = variants.calc_F(refs)
    for k, n in enumerate(short):
        row = [n, str(len(yzs[k].d))] + [str(res[v]["sz"]["tunes"][k]) for v in vs]
        row += ["", str(fcalc[k])]
        out.append("| " + " | ".join(row) + " |")
    tot = ["**все**", str(sum(len(y.d) for y in yzs))] + \
        ["**%d**" % sum(res[v]["sz"]["tunes"]) for v in vs]
    tot += [str(res["D"]["calc"].get("D1", "")) if "D" in res else "", str(sum(fcalc))]
    out.append("| " + " | ".join(tot) + " |")
    out.append("")
    out.append("Плеер и итоги, байт:")
    out.append("")
    out.append("| | " + " | ".join(vs) + " |")
    out.append("|---|" + "---|" * len(vs))

    def row(title, f):
        out.append("| %s | %s |" % (title, " | ".join(str(f(res[v])) for v in vs)))

    row("код плеера", lambda r: r["sz"]["code"])
    row("общие данные (таблицы, словари, инструменты, общие куски)", lambda r: r["sz"]["shared"])
    row("**все 11 мелодий в игре**",
        lambda r: "**%d**" % (r["sz"]["code"] + r["sz"]["shared"] + sum(r["sz"]["tunes"])))
    row("одна мелодия в игре: меньше всего",
        lambda r: min(r["single"]) if r["single"] else "")
    row("одна мелодия в игре: больше всего",
        lambda r: max(r["single"]) if r["single"] else "")
    row("без хвоста: код + общие + мелодии",
        lambda r: r["notail"]["code"] + r["notail"]["shared"] + sum(r["notail"]["tunes"]))
    row("нулевая страница (по сборке / тронуто)", lambda r: "%d / %d" % (r["sz"]["zp"], r["zp"]))
    row("ОЗУ переменных (по сборке / тронуто)", lambda r: "%d / %d" % (r["sz"]["ram"], r["ram"]))
    row("стек, байт", lambda r: r["stack"])
    row("тактов на тик: наибольшее / среднее", lambda r: "%d / %d" % (r["cmax"], r["cavg"]))
    row("zlib данных мелодий (оценка)", lambda r: r["calc"].get("zlib_data", ""))
    row("сверка с моделью", lambda r: "совпало" if not r["errs"] else "%d ошибок" % len(r["errs"]))
    if res and all(res[v]["prefix"] for v in vs):
        out.append("")
        out.append("В игре мелодии 1..k (плеер + общие + мелодии), байт; меньшее - жирным:")
        out.append("")
        out.append("| k | " + " | ".join(vs) + " |")
        out.append("|---|" + "---|" * len(vs))
        for k in range(len(short)):
            vals = [res[v]["prefix"][k] for v in vs]
            best = min(vals)
            out.append("| %d | %s |" % (k + 1, " | ".join("**%d**" % x if x == best else str(x)
                                                         for x in vals)))
    if res:
        out.append("")
        out.append("Одна мелодия в игре (плеер + общие + мелодия), байт:")
        out.append("")
        out.append("| Мелодия | " + " | ".join(vs) + " |")
        out.append("|---|" + "---|" * len(vs))
        for k, n in enumerate(short):
            if all(res[v]["single"] for v in vs):
                out.append("| %s | %s |" % (n, " | ".join(str(res[v]["single"][k]) for v in vs)))
    return out


if __name__ == "__main__":
    main()
