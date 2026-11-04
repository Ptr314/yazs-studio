# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Снимки экрана плеера: меню, пульт и трекер во время игры (процессор
остановлен на время снимка - индикаторы меняются каждый тик).

    python studio/shots.py файл.yz|модуль|диск.dsk [секунд_игры]   -> out/shots/*.png
"""

import os
import sys

import listen
import render


def main():
    src = sys.argv[1]
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    out = os.path.join(render.OUT, "shots")
    os.makedirs(out, exist_ok=True)
    if src.lower().endswith(".dsk"):
        disk, stem = os.path.abspath(src), os.path.splitext(os.path.basename(src))[0]
    else:
        disk, info, stem = listen.make_disk(src, out)
    render.run(['MACHINE "agat/Agat-9-yazs.ext"', 'COMMAND fdd0.load("%s")' % disk.replace("\\", "/"),
                "RESET cold", "SPEED MAX", "WAIT 12000", 'SCREEN "%s-menu.png"' % stem,
                "KEY 100,100,ret", "WAIT %d" % (secs * 1000), "COMMAND cpu.stop()",
                'SCREEN "%s-panel.png"' % stem, "COMMAND cpu.run()",
                "KEY 100,100,ret", "WAIT 3000", "COMMAND cpu.stop()", 'SCREEN "%s-tracker.png"' % stem,
                "EXIT"], "shots_" + stem, out)
    for v in ("menu", "panel", "tracker"):
        print(os.path.join(out, "%s-%s.png" % (stem, v)))


if __name__ == "__main__":
    main()
