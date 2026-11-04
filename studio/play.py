# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Мелодия в оконном eCat3: диск с плеером вставлен, машина загружена, мелодия
играет в настоящем времени, дальше - клавиши плеера (docs/player.md,
«Управление»): ВЛЕВО/ВПРАВО - кадр назад и вперед, R - повтор, ВВОД - пульт
или трекер, ПРОБЕЛ/ВВЕРХ - следующая и предыдущая, РЕД - меню.

    python studio/play.py файл.yzt|файл.yz|партитура [--disk готовый.dsk] [--frame N]
    python studio/play.py диск.dsk [--song N|ИМЯ.YZ]

Мелодия ложится:
- с --disk - на копию готового диска с плеером (out/play/, yzdisk.py): AS65 не
  нужен, тем же именем мелодия заменяется;
- без --disk - на новый диск со свежесобранным плеером, как у listen.py (нужен AS65).

--frame N - сразу перейти к кадру N (N раз ВПРАВО), --menu - не запускать, а
оставить меню; --wait - ждать, пока окно закроют. Оконный eCat3 ищется как в
render.find_gui: ECAT3_EXE, выпуск в ECAT3_DIR, сборки в src/cmake-build-*.
Окно хранит свои настройки в out/play/work/ecat.ini, ecat.ini самого eCat3 не
трогается.
"""

import argparse
import os
import sys

import build
import mkdisk840
import render
import tables
import yzdisk
import yztext

OUTDIR = os.path.join(build.OUT, "play")
BOOT_MS = 12000                 # «Быстропускалка», плеер, каталог - на скорости MAX
PLAYING = 0x76                  # player.a65: playing = 1, когда файл загружен и играет


def row_ms(data):
    """Длительность строки в начале мелодии, мс (speed и N из заголовка)"""
    return data[67] * data[66] * 1000.0 / tables.TIMER_CLOCK


def script(disk_path, index, start=True, frame=0, row=150.0):
    """Сценарий: загрузка на MAX, затем 1x, выбор index-й мелодии меню (с 0).
    ВПРАВО ставит переход на следующий кадр в конце строки: нажатия в одной
    строке сливаются, а во время загрузки файла пропадают. Поэтому - ждать
    playing и нажимать не чаще, чем через полторы строки (row, мс)"""
    lines = [
        'MACHINE "agat/Agat-9-yazs.ext"',
        'COMMAND fdd0.load("%s")' % os.path.abspath(disk_path).replace("\\", "/"),
        "RESET cold",
        "SPEED MAX",
        "WAIT %d" % BOOT_MS,
        "SPEED 1",
    ]
    if index:
        lines.append("KEY 60,60" + ",down" * index)
    if start:
        lines.append("KEY 100,100,ret")
        if frame:
            lines.append("WAITFOR ram.value($%02X) == 1, 60000" % PLAYING)
            lines.append("KEY %d,50" % max(100, int(row * 1.5)) + ",right" * frame)
    return lines


def song_index(disk, song):
    """--song: номер в меню (с 1) или имя файла -> индекс с 0"""
    menu = yzdisk.songs(disk)
    if not menu:
        sys.exit("на диске нет мелодий *.YZ")
    if song.isdigit():
        i = int(song) - 1
        if not 0 <= i < len(menu):
            sys.exit("мелодий на диске %d" % len(menu))
        return i
    name = yzdisk.disk_name(song)
    if name not in menu:
        sys.exit("на диске нет %s; есть: %s" % (name, ", ".join(menu)))
    return menu.index(name)


def write_disk(path, disk):
    try:
        with open(path, "wb") as f:
            f.write(bytes(disk.d))
    except PermissionError:
        sys.exit("%s занят - закройте прошлое окно eCat3 с этим диском" % path)


def main():
    ap = argparse.ArgumentParser(description="Мелодия в оконном eCat3 (docs/text-format.md)")
    ap.add_argument("src", help="файл .yzt или .yz, имя партитуры score/ или диск .dsk")
    ap.add_argument("--disk", help="готовый диск с плеером: мелодия ляжет на его копию (без AS65)")
    ap.add_argument("--song", help="для .dsk: какую мелодию запустить - номер в меню (с 1) или имя")
    ap.add_argument("--frame", type=int, default=0, help="перейти к кадру N")
    ap.add_argument("--menu", action="store_true", help="не запускать мелодию, оставить меню")
    ap.add_argument("--wait", action="store_true", help="ждать, пока окно eCat3 закроют")
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    src = a.src
    start = not a.menu

    if src.lower().endswith(".dsk"):
        if a.disk:
            ap.error("--disk - для мелодии; диск .dsk открывается как есть")
        disk_path = os.path.abspath(src)
        with open(disk_path, "rb") as f:
            disk = mkdisk840.Disk840(f.read())
        index = song_index(disk, a.song) if a.song else 0
        start = start and a.song is not None
        stem = os.path.splitext(os.path.basename(src))[0]
        data = yzdisk.extract(disk, yzdisk.songs(disk)[index]) if start else None
    else:
        if a.song:
            ap.error("--song - только для диска .dsk")
        data = yzdisk.song_data(src)
        name = yzdisk.disk_name(src)
        stem = os.path.splitext(os.path.basename(src))[0]
        disk_path = os.path.join(OUTDIR, stem + ".dsk")
        if a.disk:
            with open(a.disk, "rb") as f:
                disk = mkdisk840.Disk840(f.read())
            try:
                yzdisk.put_song(disk, name, data)
            except ValueError as e:
                sys.exit(str(e))
            for w in yzdisk.warnings(disk):
                print("внимание:", w, file=sys.stderr)
            write_disk(disk_path, disk)
        else:
            if not os.path.isfile(build.AS65) or os.name != "nt":
                sys.exit("нет AS65 (%s): задайте готовый диск с плеером, например --disk "
                         "dist/yazs-player.dsk" % build.AS65)
            if os.path.exists(disk_path):
                try:
                    os.remove(disk_path)
                except PermissionError:
                    sys.exit("%s занят - закройте прошлое окно eCat3 с этим диском" % disk_path)
            disk = build.player_disk([(name, data)], disk_path, OUTDIR)
        index = yzdisk.songs(disk).index(name)
        print("%s: %s, на диске %s - %d-я в меню" % (name, yztext.summary(data), disk_path, index + 1))

    lines = script(disk_path, index, start, a.frame if start else 0, row_ms(data) if data else 150.0)
    exe = render.launch_gui(lines, "play_" + stem, OUTDIR, wait=a.wait)
    print("eCat3: %s" % exe)
    print("клавиши плеера: ВЛЕВО/ВПРАВО - кадр, R - повтор, ВВОД - пульт/трекер, РЕД - меню")


if __name__ == "__main__":
    main()
