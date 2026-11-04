# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Мелодии на готовом диске ЯЗС-плеера (840 КБ) - без AS65 и eCat3: плеер на диске
уже есть, здесь мелодии *.YZ дописываются, заменяются, удаляются и достаются.

    python studio/yzdisk.py диск.dsk                                 каталог и меню плеера
    python studio/yzdisk.py диск.dsk --add файл.yzt [--add файл.yz]  дописать (то же имя - заменить)
    python studio/yzdisk.py диск.dsk --add файл.yz --name "МОЯ.YZ"   с другим именем на диске
    python studio/yzdisk.py диск.dsk --delete "ИМЯ.YZ"
    python studio/yzdisk.py диск.dsk --extract "ИМЯ.YZ" [-o файл.yz]

-o при --add/--delete - записать новый образ (без него правится этот), при
--extract - куда положить .yz (по умолчанию - в текущий каталог). --hfe - еще
.hfe рядом с образом (его пишет eCat3, нужен eCat3-headless).

--add берет .yz, текстовый вид .yzt (yztext.py) или имя партитуры score/.
Имя на диске - имя файла заглавными, _ -> -, с .YZ: плеер показывает только
двоичные файлы *.YZ, в порядке каталога.
"""

import argparse
import os
import struct
import sys

import compose
import mkdisk840
import tables
import yztext

HERE = os.path.dirname(os.path.abspath(__file__))
MENU_MAX = 40                   # каталог плеера ($0B00, docs/player.md)


def disk_name(src, name=None):
    """Имя файла мелодии на диске"""
    if name is None:
        stem = os.path.splitext(os.path.basename(src))[0]
        name = stem.upper().replace("_", "-")[:27]
    name = name.upper()
    if not name.endswith(".YZ"):
        name += ".YZ"
    if len(name) > 30:
        raise ValueError("имя %s длиннее 30 знаков" % name)
    tables.name_dos(name)           # знаки - из набора Агата, иначе ValueError
    return name


def song_data(src):
    """Байты .YZ: файл .yz, текстовый вид .yzt или партитура score/<имя>.py"""
    if os.path.isfile(src):
        data = yztext.load(src)
        if data[:2] != b"YZ" or data[2:3] not in (b"\x01", b"\x02"):
            sys.exit("%s - не файл .YZ версии 1 или 2" % src)
        return data
    if os.path.isfile(os.path.join(HERE, "score", src + ".py")):
        import build
        return build.load_score(src).build()
    sys.exit("нет файла %s и партитуры score/%s.py" % (src, src))


def is_song(ftype, name):
    return ftype & 0x7F == mkdisk840.T_BIN and len(name) >= 4 and name.endswith(".YZ")


def songs(disk):
    """Имена мелодий в порядке меню плеера (порядок каталога)"""
    return [n for t, n, _ in disk.listing() if is_song(t, n)]


def put_song(disk, name, data):
    """Дописать мелодию; файл с тем же именем заменяется (займет его запись
    каталога, место в меню то же). True - был заменен"""
    import build
    old = [t for t, n, _ in disk.listing() if n == name]
    if old and old[0] & mkdisk840.LOCKED:
        raise ValueError("%s на диске защищен - это не мелодия (плеер?)" % name)
    if old:
        disk.delete(name)
    disk.add(name, mkdisk840.T_BIN, build.song_body(data))
    return bool(old)


def extract(disk, name):
    """.YZ с диска: тело B-файла без 4 байт ДОС. У v2 с блоками длина в
    заголовке ДОС - только основная часть, блоки идут за ней до конца файла"""
    body = disk.read_file(name)
    n = struct.unpack_from("<H", body, 2)[0]
    data = body[4:]
    if data[:2] != b"YZ":
        raise ValueError("%s - не .YZ" % name)
    ver, main, blocks = compose.yz_info(data)
    if not blocks:
        return data[:n]
    data = data[:main + blocks * compose.BLOCK]
    # последний блок на диске добит до сектора: конец - по последнему паттерну
    yz = yztext.YZFile(data)
    return data[:max([main] + [pos + ln for blk, pos, ln in yz.patterns.values()])]


def warnings(disk):
    out = []
    locked = [n for t, n, _ in disk.listing() if t & mkdisk840.LOCKED and t & 0x7F == mkdisk840.T_BIN]
    if not locked:
        out.append("на диске нет защищенного двоичного файла - плеера (ЯЗС-ПЛЕЕР): мелодии играть нечем")
    elif len(locked) > 1:
        out.append("защищенных двоичных файлов %d (%s): «Быстропускалка» запускает файл сама, только "
                   "если он один" % (len(locked), ", ".join(locked)))
    n = len(songs(disk))
    if n > MENU_MAX:
        out.append("мелодий %d: плеер покажет первые %d" % (n, MENU_MAX))
    return out


def describe(disk):
    """Каталог: файлы, у мелодий - место в меню, версия, длительность, название"""
    menu = songs(disk)
    lines = []
    for ftype, name, nsec in disk.listing():
        info = ""
        if name in menu:
            try:
                d = extract(disk, name)
                ver, main, blocks = compose.yz_info(d)
                secs = d[64] | (d[65] << 8)
                title = "".join(c or "?" for c in tables.from_agat(d[4:34])).rstrip()
                info = "%2d. v%d%s, %d:%02d  %s" % (menu.index(name) + 1, ver,
                                                   ", блоков %d" % blocks if blocks else "",
                                                   secs // 60, secs % 60, title)
            except (ValueError, IndexError) as e:
                info = "    не .YZ: %s" % e
        lines.append("  %02X %4d  %-30s %s" % (ftype, nsec, name, info))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Мелодии *.YZ на готовом диске ЯЗС-плеера (без AS65)")
    ap.add_argument("disk", help="образ 840 КБ (.dsk) с плеером")
    ap.add_argument("--add", action="append", default=[], help="файл .yz, .yzt или имя партитуры")
    ap.add_argument("--name", help="имя на диске (только с одним --add)")
    ap.add_argument("--delete", action="append", default=[], help="удалить файл с диска")
    ap.add_argument("--extract", help="достать мелодию с диска в .yz")
    ap.add_argument("-o", "--out", help="новый образ (для --add/--delete) или файл .yz (для --extract)")
    ap.add_argument("--hfe", action="store_true", help="записать и .hfe (нужен eCat3-headless)")
    a = ap.parse_args()
    if a.name and len(a.add) != 1:
        ap.error("--name - только с одним --add")
    if a.extract and (a.add or a.delete):
        ap.error("--extract - отдельно от --add и --delete")
    with open(a.disk, "rb") as f:
        disk = mkdisk840.Disk840(f.read())

    if a.extract:
        name = a.extract.upper()
        try:
            data = extract(disk, name)
        except KeyError:
            sys.exit("на диске нет %s" % name)
        except ValueError as e:
            sys.exit(str(e))
        out = a.out or name.replace(" ", "_").replace("/", "_")
        with open(out, "wb") as f:
            f.write(data)
        print("%s: %s" % (out, yztext.summary(data)))
        return

    changed = False
    try:
        for name in a.delete:
            name = name.upper()
            if any(n == name and t & mkdisk840.LOCKED for t, n, _ in disk.listing()):
                sys.exit("%s защищен (плеер?) - не удаляю" % name)
            disk.delete(name)
            print("удален:", name)
            changed = True
        for src in a.add:
            data = song_data(src)
            name = disk_name(src, a.name)
            replaced = put_song(disk, name, data)
            print("%s: %s (%s)" % ("заменен" if replaced else "дописан", name, yztext.summary(data)))
            changed = True
    except KeyError as e:
        sys.exit("на диске нет %s" % e)
    except ValueError as e:
        sys.exit(str(e))
    out = a.out or a.disk
    if changed:
        with open(out, "wb") as f:
            f.write(bytes(disk.d))
        print("образ:", out)
    print(describe(disk))
    for w in warnings(disk):
        print("внимание:", w, file=sys.stderr)
    if a.hfe:
        import build
        print("hfe:", build.save_hfe(out, os.path.join(build.OUT, "yzdisk")))


if __name__ == "__main__":
    main()
