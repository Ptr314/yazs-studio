# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Демо-диск встраиваемого плеера на системном диске ИКП Агата-9 (docs/yz2asm.md,
«Демо-диск»): мелодии собирает yz2asm.py в образ с адреса --org (плеер сам
сохраняет свою нулевую страницу - вызов из Бейсика), на копию ИКП ложатся
образ <ИМЯ>.BIN и программа на Бейсике-А9 <ИМЯ>. Программа ставит HIMEM: на
начало образа, грузит его (BLOAD) и в меню запускает мелодии по номеру, показывая
адрес входа: CALL адрес. Любая клавиша останавливает мелодию.

    python studio/yzdemo.py [имя=]мелодия ... -o dist/demo.dsk [--name DEMO] [--title "..."]

На Агате: ИКП -> «Бейсик», RUN <ИМЯ>. Рядом с .dsk - .hfe (пишет eCat3, --no-hfe - без).
"""

import argparse
import os
import sys
import tempfile

import agatbasic
import mkdisk840
import render
import yz2asm

IKP = os.path.join(render.DEPLOY, "software", "agat", "ikp1-16414.dsk")


def music(inputs, org, slot):
    """Мелодии -> (tunes, образ, символы, текст .a65); проверка на 6502 против модели"""
    o = argparse.Namespace(card=0xC080 + 16 * slot, prefix="yz_", key=True, save_zp=True,
                           zp=0xD0, ram=0xBF00, plain=False, org=org, no_tail=False)
    tunes, names = [], set()
    for arg in inputs:
        name, data, src = yz2asm.load_input(arg)
        base, n = name, 2
        while name in names:
            name = "%s_%d" % (base, n)
            n += 1
        names.add(name)
        tunes.append(yz2asm.Tune(name, data, src))
    game = yz2asm.Game(tunes)
    text, info = yz2asm.generate(game, o)
    o.zp_bytes = info["zp"]
    work = tempfile.mkdtemp(prefix="yzdemo_")
    src = os.path.join(work, "music.a65")
    with open(src, "w", encoding="utf-8") as f:
        f.write(text)
    res = yz2asm.assemble(src, org, work)
    if res is None:
        raise SystemExit("AS65 не запускается")
    image, sym = res
    err = yz2asm.place_error(org, len(image), o.ram, info["ram"])
    if err:
        raise SystemExit(err)
    errs = yz2asm.run_check(image, org, sym, game, o)
    if errs:
        raise SystemExit("проверка на 6502 не прошла: " + "; ".join(errs[:3]))
    return tunes, image, sym, text, info


def basic(name, title, org, image, tunes, sym, slot, labels):
    """Строки программы-меню"""
    end = org + len(image) - 1
    n = len(tunes)
    lines = [
        (10, "HIMEM:%d" % org),
        (20, 'D$=CHR$(4):PRINT D$;"BLOAD %s.BIN"' % name),
        (30, "N=%d:DIM A(N),L$(N),H$(N):FOR I=1 TO N:READ A(I),L$(I),H$(I):NEXT" % n),
        (40, 'HOME:PRINT "%s"' % title),
        (50, 'PRINT "%s.BIN: $%04X-$%04X, слот %d"' % (name, org, end, slot)),
        (60, 'PRINT:PRINT " N  длит.   адрес запуска":PRINT'),
        (70, "FOR I=1 TO N:PRINT L$(I);A(I):NEXT:PRINT"),
        (80, 'INPUT "Номер (0 - выход): ";K'),
        (90, "IF K=0 THEN END"),
        (100, "IF K<1 OR K>N THEN 80"),
        (110, 'PRINT "Играет: CALL ";A(K);" (";H$(K);")"'),
        (120, 'PRINT "Любая клавиша - стоп"'),
        (130, "CALL A(K):POKE 49168,0:GOTO 40"),
    ]
    num = 1000
    for k, t in enumerate(tunes):
        addr = sym["yz_" + t.name]
        row = "%2d %5.1f с  $%04X = " % (k + 1, t.seconds(), addr)
        lines.append((num, 'DATA %d,"%s","$%04X"' % (addr, row, addr)))
        num += 10
    for ln, text in lines:
        if ln >= 40 and ln < 1000:
            for part in text.split('"')[1::2]:
                if len(part) > 31:
                    raise SystemExit("строка экрана длиннее 31 знака: %r" % part)
    return lines


def ecat3_check(dsk, name, org, image, tunes, outdir):
    """Диск в eCat3: ИКП -> «Бейсик», RUN <имя>; самая короткая мелодия - до конца
    (тиков таймера - как у модели, с секундой отзвука), самая длинная - стоп клавишей;
    выход, Бейсик жив. Снимки экрана - в outdir. Список ошибок"""
    import re
    short = min(range(len(tunes)), key=lambda k: len(tunes[k].ref))
    long_ = max(range(len(tunes)), key=lambda k: len(tunes[k].ref))
    play_ms = int(len(tunes[short].ref) * tunes[short].n / 7980.0 * 1000) + 2000
    o = outdir.replace("\\", "/")
    lines = ['MACHINE "agat/Agat-9-yazs.ext"', 'COMMAND fdd0.load("%s")' % dsk.replace("\\", "/"),
             "RESET cold", "SPEED MAX", "LOGDEFS 16,16",
             "WAIT 15000", "KEY 100,100,up", "KEY 100,100,ret", "WAIT 12000",     # меню ИКП -> «Бейсик»
             'TYPE "RUN %s\\n"' % name, "WAIT 6000", 'SCREEN "%s/menu.png"' % o,
             'PRINT "@menu"', "LOG ram.value($73,$74)", "LOG ram.value($%04X,$%04X)" % (org, org + 7),
             "LOG yazs.irqs",
             'TYPE "%d\\n"' % (short + 1), "WAIT 1000", 'SCREEN "%s/play.png"' % o,
             'PRINT "@play"', "LOG cpu.registers",
             "WAIT %d" % play_ms,
             'PRINT "@done"', "LOG cpu.registers", "LOG yazs.irqs",
             'TYPE "%d\\n"' % (long_ + 1), "WAIT 2000",
             'PRINT "@long"', "LOG cpu.registers", "LOG yazs.irqs",
             "KEY 100,100,space", "WAIT 1500",
             'PRINT "@stop"', "LOG cpu.registers", "LOG yazs.irqs", "WAIT 1500",
             'PRINT "@stop2"', "LOG yazs.irqs",
             'TYPE "0\\n"', "WAIT 1500", 'TYPE "POKE 32767,42\\n"', "WAIT 1500",
             'SCREEN "%s/end.png"' % o,
             'PRINT "@end"', "LOG cpu.registers", "LOG ram.value($7FFF,$7FFF)", "EXIT"]
    out = render.run(lines, "yzdemo", outdir, timeout=900)
    got, cur = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            cur = line[1:].strip()
            got[cur] = []
        elif cur and line.startswith("["):
            got[cur].append(line)

    def nums(tag, prefix, n=0):
        rows = [l for l in got.get(tag, []) if l.startswith(prefix)]
        if len(rows) <= n:
            return []
        return [int(x, 16) for x in re.findall(r"\$([0-9A-Fa-f]+)", rows[n].split("]", 1)[1])]

    def pc(tag):
        m = [re.search(r"PC=([0-9A-F]{4})", l) for l in got.get(tag, []) if l.startswith("[cpu.registers]")]
        return int(m[0].group(1), 16) if m and m[0] else -1

    errs = []
    himem = nums("menu", "[ram.value]")
    if himem[1:3] != [org & 255, org >> 8]:
        errs.append("HIMEM не $%04X" % org)
    if nums("menu", "[ram.value]", 1)[1:] != list(image[:8]):
        errs.append("образ не загружен с $%04X" % org)
    if not org <= pc("play") < org + len(image):
        errs.append("мелодия %d не играет (PC=$%04X)" % (short + 1, pc("play")))
    ticks = nums("done", "[yazs.irqs]")[0] - nums("menu", "[yazs.irqs]")[0]
    if ticks != len(tunes[short].ref):
        errs.append("мелодия %d: тиков %d, у модели %d" % (short + 1, ticks, len(tunes[short].ref)))
    if pc("done") < 0xF800:
        errs.append("после мелодии не в Бейсике (PC=$%04X)" % pc("done"))
    if not org <= pc("long") < org + len(image):
        errs.append("мелодия %d не играет" % (long_ + 1))
    if pc("stop") < 0xF800 or nums("stop", "[yazs.irqs]") != nums("stop2", "[yazs.irqs]"):
        errs.append("клавиша не остановила мелодию %d" % (long_ + 1))
    if pc("end") < 0xF800 or nums("end", "[ram.value]")[1:2] != [42]:
        errs.append("после выхода Бейсик не работает")
    return errs, short, long_, ticks


def main():
    ap = argparse.ArgumentParser(description="Демо-диск yz2asm на системном диске ИКП Агата-9")
    ap.add_argument("inputs", nargs="+", metavar="[имя=]мелодия")
    ap.add_argument("-o", "--out", required=True, help="образ диска .dsk (840 КБ)")
    ap.add_argument("--name", default="DEMO", help="имя программы на диске (латиницей; образ - <имя>.BIN)")
    ap.add_argument("--title", default="Мелодии yz2asm", help="заголовок меню (до 31 знака)")
    ap.add_argument("--org", default="$8000", help="адрес образа ($8000; выше - HIMEM:)")
    ap.add_argument("--slot", type=int, default=1, help="слот ЯЗС (1)")
    ap.add_argument("--ikp", default=IKP, help="системный диск ИКП (из eCat3)")
    ap.add_argument("--no-hfe", action="store_true", help="без .hfe")
    ap.add_argument("--ecat3", action="store_true",
                    help="проверить диск в eCat3: RUN, мелодия до конца, стоп клавишей, выход")
    a = ap.parse_args()
    org = yz2asm.num(a.org)
    name = a.name.upper()
    if not os.path.exists(a.ikp):
        raise SystemExit("нет системного диска ИКП: %s (docs/ecat3.md)" % a.ikp)
    tunes, image, sym, text, info = music(a.inputs, org, a.slot)
    lines = basic(name, a.title, org, image, tunes, sym, a.slot, None)
    body = agatbasic.a_file(lines)
    disk = mkdisk840.Disk840(open(a.ikp, "rb").read())
    names = [n for _, n, _ in disk.listing()]
    for fname in (name, name + ".BIN"):
        if fname in names:
            disk.delete(fname)
    disk.add(name + ".BIN", mkdisk840.T_BIN, mkdisk840.b_body(org, image))
    disk.add(name, 0x02, body)
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(bytes(disk.d))
    with open(os.path.splitext(out)[0] + ".a65", "w", encoding="utf-8") as f:
        f.write(text)
    print("%s: ИКП + %s.BIN ($%04X-$%04X, %d байт) + %s (Бейсик, %d байт)" % (
        out, name, org, org + len(image) - 1, len(image), name, len(body) - 2))
    for t in tunes:
        print("  %-24s %5.1f с  вход $%04X = %d" % ("yz_" + t.name, t.seconds(), sym["yz_" + t.name],
                                                  sym["yz_" + t.name]))
    print("  текст для ассемблера: %s" % (os.path.splitext(out)[0] + ".a65"))
    if not a.no_hfe:
        import build
        print("  %s" % build.save_hfe(out, os.path.dirname(out)))
    print("На Агате: ИКП -> «Бейсик», RUN %s" % name)
    if a.ecat3:
        shots = os.path.join(render.OUT, "yzdemo", os.path.splitext(os.path.basename(out))[0])
        os.makedirs(shots, exist_ok=True)
        hfe = os.path.splitext(out)[0] + ".hfe"
        for img in [out] + ([hfe] if os.path.exists(hfe) and not a.no_hfe else []):
            errs, short, long_, ticks = ecat3_check(img, name, org, image, tunes, shots)
            print("eCat3, %s: %s" % (os.path.basename(img), "; ".join(errs) if errs else
                  "RUN %s, мелодия %d до конца (%d тиков, как у модели), %d - стоп клавишей, "
                  "выход в Бейсик - все в порядке" % (name, short + 1, ticks, long_ + 1)))
            if errs:
                sys.exit(1)
        print("  снимки экрана: %s" % shots)


if __name__ == "__main__":
    main()
