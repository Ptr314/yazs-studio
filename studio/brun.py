# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Проверка запуска плеера двумя путями и выхода к запустившему (docs/player.md,
«Запуск»). Нужны eCat3 и его системный диск ИКП (deploy/software/agat/
ikp1-16414.dsk: ДОС и Бейсик-А9).

Диск: плеер под латинским именем YAZS (его набирает сценарий; защищен, как на
дисках плеера), токката (v1), Вальс цветов (v2 без блоков), блюз в v2 с блоками.

1. «Быстропускалка» (загрузка с этого диска): после РЕД она перечитывает каталог
   и запускает плеер снова.
2. ДОС: ИКП -> «Бейсик», BRUN YAZS, игра v1 и v2, мелодия с блоками - «не
   помещается», РЕД - снова Бейсик. Затем:
   - ОЗУ ДОС (банки 8-9), Бейсика (языковая карта, физические $C000-$FFFF) и его
     переходники $1800-$18FF - те же, что до BRUN;
   - Бейсик работает: POKE, NEW, программа и RUN (результат - в памяти, не на
     экране); CATALOG; повторный BRUN снова запускает плеер.

    python studio/brun.py [--out каталог]      код возврата 1 - есть ошибки
"""

import argparse
import os
import re
import sys

import build
import render

IKP = os.path.join(render.DEPLOY, "software", "agat", "ikp1-16414.dsk")
NAME = "YAZS"
SONGS = 3                                   # *.YZ на диске: столько файлов в меню плеера
PLAYER_LO, PLAYER_HI = 0x1800, 0x3EFB       # тело плеера
ROM_LO = 0xF800                             # монитор: ожидание клавиши в Бейсике


def label(out, name):
    """Адрес метки db из листинга плеера"""
    for line in open(os.path.join(out, "player.lst"), encoding="cp866", errors="replace"):
        m = re.match(r"\s*([0-9a-fA-F]{4}) :.*\b%s\s+db\b" % name, line)
        if m:
            return int(m.group(1), 16)
    sys.exit("нет метки %s в листинге плеера" % name)


def make_disk(out):
    """Диск для проверки: путь"""
    build.gen_sources()
    player = build.assemble(out)
    disk = build.blank_disk(player, NAME)
    blues = build.load_score("m4_blues")
    blues.version, blues.main_limit = 2, 300            # v2 с паттернами в блоках
    for fname, data in (("1.ТОККАТА.YZ", build.load_score("m1_toccata").build()),
                        ("2.ВАЛЬС ЦВЕТОВ V2.YZ", build.load_score("flowers").build()),
                        ("3.БЛЮЗ V2 С БЛОКАМИ.YZ", blues.build())):
        disk.add(fname, build.mkdisk840.T_BIN, build.song_body(data))
    path = os.path.join(out, "brun.dsk")
    open(path, "wb").write(bytes(disk.d))
    return path


class Scenario:
    """Строки сценария и пробы: метка -> строки LOG после нее"""

    def __init__(self, machine_disk):
        self.lines = ['MACHINE "agat/Agat-9-yazs.ext"',
                      'COMMAND fdd0.load("%s")' % machine_disk.replace("\\", "/"),
                      "RESET cold", "SPEED MAX", "LOGDEFS 16,16"]

    def add(self, *lines):
        self.lines += list(lines)

    def probe(self, tag, *logs):
        self.lines.append('PRINT "@%s"' % tag)
        self.lines += ["LOG " + x for x in logs]

    def run(self, name, out):
        text = render.run(self.lines + ["EXIT"], name, out, timeout=300)
        got, cur = {}, None
        for line in text.splitlines():
            if line.startswith("@"):
                cur = line[1:].strip()
                got[cur] = []
            elif cur and line.startswith("["):
                got[cur].append(line)
        return got


def pc(lines):
    m = [re.search(r"PC=([0-9A-F]{4})", l) for l in lines if l.startswith("[cpu.registers]")]
    return int(m[0].group(1), 16) if m and m[0] else None


def byte(lines, n=0):
    """n-я строка ram.value из пробы -> первый байт"""
    vals = [l for l in lines if l.startswith("[ram.value]")]
    if len(vals) <= n:
        return None
    m = re.findall(r"\$([0-9A-Fa-f]{2,4})\b", vals[n].split(":", 1)[1])
    return int(m[0], 16) & 0xFF if m else None


class Report:
    def __init__(self):
        self.bad = 0

    def check(self, what, ok, detail=""):
        print("  %s %s%s" % ("OK    " if ok else "ОШИБКА", what, (" (%s)" % detail) if detail else ""))
        self.bad += not ok


def launcher(disk, out, r):
    """«Быстропускалка»: плеер, РЕД - она запускает его снова. Что это новый запуск, а не
    тот же плеер в меню, видно по dosmode: перед выходом в нем метка $5A, вход ставит 0"""
    dosmode = label(out, "dosmode")
    marker = os.path.join(out, "marker.bin")
    open(marker, "wb").write(b"\x5A")
    s = Scenario(disk)
    s.add("WAIT 12000")
    s.probe("menu", "cpu.registers", "ram.value($4D,$4D)")
    s.add("KEY 100,100,ret", "WAIT 3000")
    s.probe("play", "ram.value($76,$76)")
    s.add("KEY 100,100,esc", "WAIT 1000",
          'COMMAND ram.load("%s", $%04X)' % (marker.replace("\\", "/"), dosmode),
          "KEY 100,100,esc", "WAIT 8000")
    s.probe("again", "cpu.registers", "ram.value($4D,$4D)", "ram.value($76,$76)",
            "ram.value($%04X,$%04X)" % (dosmode, dosmode))
    g = s.run("brun_launcher", out)
    print("«Быстропускалка»:")
    r.check("плеер запущен, в меню %d файла" % SONGS,
            PLAYER_LO <= (pc(g["menu"]) or 0) <= PLAYER_HI and byte(g["menu"]) == SONGS,
            "PC=$%04X, файлов %s" % (pc(g["menu"]) or 0, byte(g["menu"])))
    r.check("мелодия играет", byte(g["play"]) == 1)
    r.check("после РЕД плеер вышел и запущен снова, меню",
            PLAYER_LO <= (pc(g["again"]) or 0) <= PLAYER_HI and byte(g["again"]) == SONGS
            and byte(g["again"], 1) == 0 and byte(g["again"], 2) == 0,
            "PC=$%04X, файлов %s, dosmode %s" % (pc(g["again"]) or 0, byte(g["again"]), byte(g["again"], 2)))


def dos(disk, out, r):
    """BRUN из Бейсика с ДОС и выход обратно"""
    toobig = label(out, "toobig")
    o = out.replace("\\", "/")
    s = Scenario(IKP)
    s.add("WAIT 15000", "KEY 100,100,up", "KEY 100,100,ret", "WAIT 12000",   # меню ИКП -> «Бейсик»
          'COMMAND ram.save("%s/before.bin")' % o,
          'COMMAND fdd0.load("%s")' % disk.replace("\\", "/"),
          'TYPE "BRUN %s\\n"' % NAME, "WAIT 8000")
    s.probe("menu", "cpu.registers", "ram.value($4D,$4D)")
    s.add("KEY 100,100,ret", "WAIT 4000")
    s.probe("v1", "ram.value($76,$76)")
    s.add("KEY 100,100,esc", "WAIT 1500", "KEY 100,100,down", "KEY 100,100,ret", "WAIT 5000")
    s.probe("v2", "ram.value($76,$76)")
    s.add("KEY 100,100,esc", "WAIT 1500", "KEY 100,100,down", "KEY 100,100,ret", "WAIT 5000")
    s.probe("blocks", "ram.value($76,$76)", "ram.value($%04X,$%04X)" % (toobig, toobig))
    s.add("KEY 100,100,space", "WAIT 1500", "KEY 100,100,esc", "WAIT 5000")
    s.probe("back", "cpu.registers", "port-C1xx.value(0,15)")
    s.add('COMMAND ram.save("%s/after.bin")' % o,
          'TYPE "POKE 32768,42\\n"', "WAIT 2000")
    s.probe("poke", "cpu.registers", "ram.value($8000,$8000)")
    s.add('TYPE "NEW\\n"', 'TYPE "10 POKE 32769,6*7\\n"', 'TYPE "RUN\\n"', "WAIT 3000")
    s.probe("run", "cpu.registers", "ram.value($8001,$8001)")
    s.add('TYPE "CATALOG\\n"', "WAIT 6000")
    s.probe("catalog", "cpu.registers")
    s.add('TYPE "BRUN %s\\n"' % NAME, "WAIT 8000")
    s.probe("again", "cpu.registers", "ram.value($4D,$4D)")
    s.add("COMMAND cpu.stop()", 'SCREEN "brun_again.png"')
    g = s.run("brun_dos", out)

    in_player = lambda k: PLAYER_LO <= (pc(g[k]) or 0) <= PLAYER_HI
    in_rom = lambda k: (pc(g[k]) or 0) >= ROM_LO
    print("ДОС (BRUN из Бейсика-А9):")
    r.check("BRUN запустил плеер, в меню %d файла" % SONGS, in_player("menu") and byte(g["menu"]) == SONGS,
            "PC=$%04X, файлов %s" % (pc(g["menu"]) or 0, byte(g["menu"])))
    r.check("v1 играет", byte(g["v1"]) == 1)
    r.check("v2 без блоков играет", byte(g["v2"]) == 1)
    r.check("v2 с блоками - «НЕ ПОМЕЩАЕТСЯ В ПАМЯТЬ»", byte(g["blocks"]) == 0 and byte(g["blocks"], 1) == 1,
            "playing %s, toobig %s" % (byte(g["blocks"]), byte(g["blocks"], 1)))
    seg = re.findall(r"\$([0-9A-Fa-f]{2,4})", " ".join(g["back"][1:]).split(":", 1)[-1])
    r.check("РЕД - снова Бейсик, карта памяти обычная",
            in_rom("back") and [int(x, 16) & 0xFF for x in seg[:8]] == list(range(8)),
            "PC=$%04X" % (pc(g["back"]) or 0))

    a = open(os.path.join(out, "before.bin"), "rb").read()
    b = open(os.path.join(out, "after.bin"), "rb").read()
    for what, lo, hi in (("ДОС: банки 8-9", 0x10000, 0x14000),
                         ("Бейсик: языковая карта, физические $C000-$FFFF", 0xC000, 0x10000),
                         ("Бейсик: переходники $1800-$18FF", 0x1800, 0x1900)):
        diff = sum(1 for i in range(lo, hi) if a[i] != b[i])
        r.check("%s - как до BRUN" % what, diff == 0, ("изменилось %d байт" % diff) if diff else "")
    # Сама ДОС после BRUN и теплого перезапуска пишет в свои страницы (буфер имени,
    # регистры заглушки, рабочие ячейки): это не ошибка, только для сведения
    for what, lo, hi in (("страницы ДОС $0300-$05FF", 0x300, 0x600), ("код ДОС $0600-$0FFF", 0x600, 0x1000)):
        print("  сведения: %s - изменилось %d байт (пишет сама ДОС)" % (
            what, sum(1 for i in range(lo, hi) if a[i] != b[i])))

    r.check("Бейсик: POKE", in_rom("poke") and byte(g["poke"]) == 42, "в $8000: %s" % byte(g["poke"]))
    r.check("Бейсик: NEW, строка программы, RUN", in_rom("run") and byte(g["run"]) == 42,
            "в $8001: %s" % byte(g["run"]))
    r.check("ДОС: CATALOG", in_rom("catalog"), "PC=$%04X" % (pc(g["catalog"]) or 0))
    r.check("повторный BRUN запускает плеер", in_player("again") and byte(g["again"]) == SONGS,
            "PC=$%04X, файлов %s" % (pc(g["again"]) or 0, byte(g["again"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(render.OUT, "brun"))
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    if not os.path.exists(IKP):
        sys.exit("нет системного диска ИКП: %s" % IKP)
    disk = make_disk(out)
    r = Report()
    launcher(disk, out, r)
    dos(disk, out, r)
    print("запуск и выход: %s" % ("все проверки прошли" if not r.bad else "ошибок %d" % r.bad))
    sys.exit(1 if r.bad else 0)


if __name__ == "__main__":
    main()
