# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Сборка диска ЯЗС-плеера: таблицы и строки -> player/gen_*.a65, AS65 -> плеер,
партитуры score/*.py -> *.YZ, все на копию disk/template840.dsk (дорожка 0 с
«Быстропускалкой» и ДОС 3.3), образ - в dist/.

    python studio/build.py                     симфония (диск библиотеки eCat3) -> dist/yazs-player.dsk
    python studio/build.py --set all           симфония и все пьесы -> dist/yazs-collection.dsk
    python studio/build.py --set classics      переложения классики -> dist/yazs-classics.dsk
    python studio/build.py --set demo          «Демо ЯЗС»: симфония, тур, свои пьесы -> dist/yazs-demo.dsk
    python studio/build.py --only m2_adagio --disk x.dsk     только эти партитуры
    python studio/build.py --to-ecat3          и копия в eCat3: library/agat/yazs-player.dsk/.hfe

Ключи: --out каталог (промежуточное: player.bin, .lst, .yz), --extra модуль, --no-hfe,
--add файл.yz|файл.yzt (готовая мелодия или текстовый вид, yztext.py).
"""

import argparse
import importlib.util
import os
import subprocess
import sys

import mkdisk840
import tables

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
PLAYER = os.path.join(ROOT, "player")
AS65 = os.path.join(ROOT, "third_party", "as65", "as65.exe")
TEMPLATE = os.path.join(ROOT, "disk", "template840.dsk")
DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(ROOT, "out")
PLAYER_ADDR = 0x1800
LOADER_ADDR = 0x4000        # файл ЯЗС-ПЛЕЕР грузится сюда (player/loader.a65)
SONG_ADDR = 0x3F00

# Партитуры в порядке на диске: модуль score/<имя>.py, имя файла на диске
SONGS = [
    ("m1_toccata", "1.ТОККАТА И ФУГА.YZ"),
    ("m2_adagio", "2.АДАЖИО.YZ"),
    ("m3_scherzo", "3.СКЕРЦО-ВАЛЬС.YZ"),
    ("m4_blues", "4.БЛЮЗ 1987.YZ"),
    ("m5_synth", "5.ЭЛЕКТРИЧЕСКИЙ СОН.YZ"),
    ("m6_finale", "6.ФИНАЛ.YZ"),
    ("tour", "ТУР ПО ТЕМБРАМ.YZ"),
]

# Остальные пьесы (--set all): стили и переложения классики, docs/music.md
COLLECTION = [
    ("boogie", "ЯЗС-БУГИ.YZ"),
    ("disco", "ЯЗС-ДИСКО.YZ"),
    ("manouche", "ЯЗС-МАНУШ.YZ"),
    ("sbivka", "ЯЗС-СБИВКА.YZ"),
    ("mountainking", "ГРИГ.ГОРНЫЙ КОРОЛЬ.YZ"),
    ("solveig", "ГРИГ.ПЕСНЯ СОЛЬВЕЙГ.YZ"),
    ("anitra", "ГРИГ.ТАНЕЦ АНИТРЫ.YZ"),
    ("sugarplum", "ЧАЙКОВСКИЙ.ФЕЯ ДРАЖЕ.YZ"),
    ("bumblebee", "РИМСКИЙ-КОРСАКОВ.ШМЕЛЬ.YZ"),
    ("entertainer", "ДЖОПЛИН.ENTERTAINER.YZ"),
    ("littlebrownjug", "LITTLE BROWN JUG.YZ"),
    ("ritz", "PUTTIN ON THE RITZ.YZ"),
    ("vivaldi_spring", "ВИВАЛЬДИ.ВЕСНА.YZ"),
    ("vivaldi_summer", "ВИВАЛЬДИ.ЛЕТО.YZ"),
    ("vivaldi_autumn", "ВИВАЛЬДИ.ОСЕНЬ.YZ"),
    ("vivaldi_winter", "ВИВАЛЬДИ.ЗИМА.YZ"),
    ("flowers", "ЧАЙКОВСКИЙ.ВАЛЬС ЦВЕТОВ.YZ"),
]

# Диск классики (--set classics -> dist/yazs-classics.dsk): переложения из COLLECTION
# по времени написания
CLASSICS = ["vivaldi_spring", "vivaldi_summer", "vivaldi_autumn", "vivaldi_winter",
            "mountainking", "solveig", "anitra", "sugarplum", "flowers", "bumblebee"]

# Диск «Демо ЯЗС» (--set demo -> dist/yazs-demo.dsk): симфония (вальс - в теплой версии),
# тур по тембрам, свои пьесы, в конце - аранжировки чужих мелодий
DEMO = ["m1_toccata", "m2_adagio", "m3_scherzo_warm", "m4_blues", "m5_synth", "m6_finale", "tour",
        "boogie", "disco", "manouche", "sbivka", "entertainer", "littlebrownjug", "ritz"]
VARIANTS = {"m3_scherzo_warm": "m3_scherzo"}     # версия -> модуль, чье имя на диске

STRINGS = {
    "s_header": " ЯЗС-ПЛЕЕР     АГАТ-9 + ЯЗС 5/2 ",
    "s_choose": "ВЫБЕРИТЕ МЕЛОДИЮ:",
    "s_help1": " ВВЕРХ/ВНИЗ-ВЫБОР  ВВОД-ИГРАТЬ",
    "s_help2": " А-ВСЕ ПОДРЯД  Д-ПЕРЕЧИТАТЬ ДИСК",
    "s_help3": " ВЛЕВО/ВПРАВО-СЛОТ  РЕД-ВЫХОД",
    "s_slot": "ЯЗС В СЛОТЕ ",
    "s_slot2": "",
    "s_nofiles": "НА ДИСКЕ НЕТ ФАЙЛОВ *.YZ",
    "s_reading": "ЧТЕНИЕ КАТАЛОГА...",
    "s_diskerr": "ОШИБКА ЧТЕНИЯ ДИСКА",
    "s_loading": "ЗАГРУЗКА...",
    "s_loaderr": "ОШИБКА ЗАГРУЗКИ ФАЙЛА",
    "s_toobig": "НЕ ПОМЕЩАЕТСЯ В ПАМЯТЬ",
    "s_time": "ВРЕМЯ 00:00/00:00    КАДР",
    "s_drum6": "БАРАБАН",
    "s_drum7": "ТАРЕЛКА",
    "s_regs": "РЕГИСТРЫ КАНАЛОВ И ПЕРИОДЫ:",
    "s_playhelp": "РЕД-МЕНЮ ПРОБЕЛ-ДАЛЕЕ ВВОД-ВИД",
    "s_playhelp2": "ВЛЕВО/ВПРАВО-КАДР ВВЕРХ-НАЗАД",
    "s_rept": "R-ПОВТОР ",
    "s_on": "ВКЛ ",
    "s_off": "ВЫКЛ",
}


def db_lines(label, data, per=16):
    out = []
    for i in range(0, len(data), per):
        chunk = ",".join("$%02X" % b for b in data[i:i + per])
        out.append("%-12s db %s" % (label if i == 0 else "", chunk))
    if not data:
        out.append("%-12s" % label)
    return out


def gen_sources():
    lines = ["; Сгенерировано build.py - не править", ""]
    ptab = tables.period_table()
    lines.append("            align 256")
    lines += db_lines("vibtab", tables.vibrato_table())
    lines += db_lines("ptab_lo", [p & 255 for p in ptab])
    lines += db_lines("ptab_hi", [p >> 8 for p in ptab])
    lines += db_lines("div12", [n // 12 for n in range(96)])
    lines += db_lines("mod12", [n % 12 for n in range(96)])
    lines += db_lines("rnd_lo", [0] + [(1 << (o - 1)) & 255 for o in range(1, 8)])
    lines += db_lines("rnd_hi", [0] + [(1 << (o - 1)) >> 8 for o in range(1, 8)])
    lines += db_lines("rowlo", [(0x1000 + r * 64) & 255 for r in range(32)])
    lines += db_lines("rowhi", [(0x1000 + r * 64) >> 8 for r in range(32)])
    names = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]
    lines += db_lines("notenm", list(tables.agat("".join(names))))
    for k, v in STRINGS.items():
        if len(v) > 32:
            raise ValueError("строка %s длиннее 32: %d" % (k, len(v)))
        lines += db_lines(k, list(tables.agat(v)) + [0])
    # Заголовок колонок трекера: колонки trkx в tracker.a65
    cols = bytearray(tables.agat(" " * 64))
    for x, s in ((0, "СТР"), (5, "ТОН 1"), (14, "ТОН 2"), (23, "ТОН 3"), (32, "ТОН 4"),
                 (41, "ТОН 5"), (51, "Б6"), (56, "Т7")):
        cols[x:x + len(s)] = tables.agat(s)
    lines += db_lines("s_trkcols", list(cols.rstrip(b"\xa0")) + [0])
    with open(os.path.join(PLAYER, "gen_tables.a65"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(PLAYER, "gen_const.a65"), "w", encoding="utf-8") as f:
        f.write("; Сгенерировано build.py - не править\n")


def as65(src, out, name):
    binf = os.path.join(out, name + ".bin")
    lst = os.path.join(out, name + ".lst")
    if os.path.exists(binf):
        os.remove(binf)
    proc = subprocess.run([AS65, "-l" + lst, "-n", "-w", "-h0", "-o" + binf, src],
                          cwd=PLAYER, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = proc.stdout.decode("cp866", errors="replace")
    if proc.returncode != 0 or not os.path.exists(binf) or "rror" in text:
        sys.stderr.write(text)
        sys.exit("AS65: ошибка сборки %s" % src)
    return open(binf, "rb").read()


def assemble(out):
    """Тело плеера (с $1800) и загрузчик перед ним: (тело, файл ЯЗС-ПЛЕЕР для диска)"""
    data = as65("player.a65", out, "player")
    pages = (len(data) + 255) // 256
    # загрузчик копирует тело целыми страницами: до $3EFC (тело B-файла мелодии)
    end = PLAYER_ADDR + pages * 256
    if end > SONG_ADDR - 4:
        sys.exit("плеер %d байт (%d страниц) заходит на мелодию ($%04X)" % (len(data), pages, end))
    with open(os.path.join(PLAYER, "gen_loader.a65"), "w", encoding="utf-8") as f:
        f.write("; Сгенерировано build.py - не править\nPLPAGES     equ %d\n" % pages)
    loader = as65("loader.a65", out, "loader")
    return data, mkdisk840.b_body(LOADER_ADDR, loader + data)


def song_body(data):
    """Тело B-файла мелодии .YZ (у v2 с блоками длиной - основная часть)"""
    import compose
    return mkdisk840.b_body(SONG_ADDR, data, compose.bload_length(data))


def blank_disk(player, name="ЯЗС-ПЛЕЕР"):
    """Шаблон 840 КБ (дорожка 0 и ДОС) с плеером - первым и единственным защищенным
    файлом: его «Быстропускалка» и запускает (или BRUN из ДОС). player - assemble();
    name - имя файла плеера (brun.py берет латинское: его набирает сценарий)"""
    disk = mkdisk840.Disk840(open(TEMPLATE, "rb").read())
    if any(n == "SOUNDTEST" for _, n, _ in disk.listing()):
        disk.delete("SOUNDTEST")              # исходный soundtest.DSK вместо шаблона
    disk.set_volume("ЯЗС-ПЛЕЕР")
    disk.add(name, mkdisk840.T_BIN, player[1], locked=True)
    return disk


def player_disk(files, path, out):
    """Диск: плеер и мелодии [(имя на диске, данные .YZ)]; путь образа"""
    disk = blank_disk(assemble(out))
    for name, data in files:
        disk.add(name, mkdisk840.T_BIN, song_body(data))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(bytes(disk.d))
    return disk


def save_hfe(dsk, out):
    """.hfe рядом с образом: пишет сам эмулятор (дорожки Агата 840)"""
    import render
    hfe = os.path.splitext(dsk)[0] + ".hfe"
    if os.path.exists(hfe):
        os.remove(hfe)
    render.run(['MACHINE "agat/Agat-9-yazs.ext"',
                'COMMAND fdd0.load("%s")' % os.path.abspath(dsk).replace("\\", "/"),
                'COMMAND fdd0.save("%s")' % os.path.abspath(hfe).replace("\\", "/"),
                "EXIT"], "hfe", out)
    return hfe


def load_score(name):
    path = os.path.join(HERE, "score", name + ".py")
    spec = importlib.util.spec_from_file_location("score_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.join(HERE, "score"))
    spec.loader.exec_module(mod)
    return mod.song()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=("symphony", "all", "classics", "demo"), default="symphony",
                    help="symphony - диск библиотеки eCat3, all - и все пьесы, classics - классика, "
                         "demo - «Демо ЯЗС»")
    ap.add_argument("--out", default=os.path.join(OUT, "build"))
    ap.add_argument("--disk", help="образ (по умолчанию dist/yazs-player.dsk, yazs-collection.dsk, "
                                   "yazs-classics.dsk или yazs-demo.dsk)")
    ap.add_argument("--only", action="append", help="только эти партитуры (имя модуля)")
    ap.add_argument("--extra", action="append", default=[], help="добавить модуль score/ на диск")
    ap.add_argument("--add", action="append", default=[],
                    help="добавить на диск готовую мелодию: файл .yz или текстовый вид .yzt")
    ap.add_argument("--no-hfe", action="store_true")
    ap.add_argument("--to-ecat3", action="store_true",
                    help="скопировать диск и .hfe в eCat3: library/agat/yazs-player.*")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    disk_path = a.disk or os.path.join(DIST, {"symphony": "yazs-player.dsk", "all": "yazs-collection.dsk",
                                              "classics": "yazs-classics.dsk",
                                              "demo": "yazs-demo.dsk"}[a.set])

    gen_sources()
    player = assemble(a.out)
    print("плеер: %d байт, $%04X-$%04X; файл с загрузчиком %d байт с $%04X" % (
        len(player[0]), PLAYER_ADDR, PLAYER_ADDR + len(player[0]) - 1, len(player[1]) - 4, LOADER_ADDR))
    disk = blank_disk(player)

    if a.set in ("classics", "demo"):
        names = dict(SONGS + COLLECTION)
        songs = [(m, names[VARIANTS.get(m, m)]) for m in (CLASSICS if a.set == "classics" else DEMO)]
    else:
        songs = SONGS + (COLLECTION if a.set == "all" else [])
    songs = [s for s in songs if not a.only or s[0] in a.only]
    songs += [(m, m.upper().replace("_", "-") + ".YZ") for m in a.extra]
    total = 0
    for module, fname in songs:
        if not os.path.exists(os.path.join(HERE, "score", module + ".py")):
            print("  (нет score/%s.py - пропуск)" % module)
            continue
        song = load_score(module)
        data = song.build()
        with open(os.path.join(a.out, module + ".yz"), "wb") as f:
            f.write(data)
        disk.add(fname, mkdisk840.T_BIN, song_body(data))
        st = song.stats
        total += st["seconds"]
        print("  %-30s %5d байт, v%d, %3d кадров, %3d паттернов, %d:%02d, speed %d, N %d" % (
            fname, st["bytes"], st["version"], st["frames"], st["patterns"], st["seconds"] // 60,
            st["seconds"] % 60, st["speed"], st["n"]))
    for path in a.add:
        import yzdisk
        import yztext
        data = yzdisk.song_data(path)
        fname = yzdisk.disk_name(path)
        yzdisk.put_song(disk, fname, data)
        total += data[64] | (data[65] << 8)
        print("  %-30s %s (из %s)" % (fname, yztext.summary(data), path))
    print("всего %d:%02d" % (total // 60, total % 60))

    os.makedirs(os.path.dirname(os.path.abspath(disk_path)), exist_ok=True)
    with open(disk_path, "wb") as f:
        f.write(bytes(disk.d))
    print("диск:", disk_path)
    for ftype, name, n in mkdisk840.Disk840(bytes(disk.d)).listing():
        print("  %02X %4d  %s" % (ftype, n, name))
    hfe = None
    if not a.no_hfe:
        hfe = save_hfe(disk_path, a.out)
        print("hfe: ", hfe, os.path.getsize(hfe), "байт")
    if a.to_ecat3:
        import shutil
        import render
        lib = os.path.join(render.ECAT3, "library", "agat")
        shutil.copyfile(disk_path, os.path.join(lib, "yazs-player.dsk"))
        if hfe:
            shutil.copyfile(hfe, os.path.join(lib, "yazs-player.hfe"))
        print("в eCat3:", lib, "- перезапишите эталоны теста work-agat-9-yazs-player (docs/ecat3.md)")


if __name__ == "__main__":
    main()
