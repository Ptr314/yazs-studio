"""Один диск с обеими версиями: часть, рядом она же в теплой версии, в конце тур по тембрам"""
import os
import sys

import warm  # noqa: F401  (путь к studio/)
import build  # noqa: E402
import mkdisk840  # noqa: E402
import render  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(build.OUT, "ab")
DISK = os.path.join(build.DIST, "yazs-player-ab.dsk")
MARK = " (ТЕПЛ.)"


def main():
    os.makedirs(OUT, exist_ok=True)
    build.gen_sources()
    player = build.assemble(OUT)
    disk = build.blank_disk(player)
    for module, fname in build.SONGS + [("boogie", "ЯЗС-БУГИ.YZ"), ("disco", "ЯЗС-ДИСКО.YZ"), ("mountainking", "ГРИГ.ГОРНЫЙ КОРОЛЬ.YZ"), ("sugarplum", "ЧАЙКОВСКИЙ.ФЕЯ ДРАЖЕ.YZ"), ("bumblebee", "РИМСКИЙ-КОРСАКОВ.ШМЕЛЬ.YZ"), ("entertainer", "ДЖОПЛИН.ENTERTAINER.YZ"), ("littlebrownjug", "LITTLE BROWN JUG.YZ"), ("manouche", "ЯЗС-МАНУШ.YZ"), ("ritz", "PUTTIN ON THE RITZ.YZ"), ("solveig", "ГРИГ.ПЕСНЯ СОЛЬВЕЙГ.YZ"), ("anitra", "ГРИГ.ТАНЕЦ АНИТРЫ.YZ")]:
        variants = [(fname, build.load_score(module))]
        if module in warm.PARTS:
            s = warm.warm(build.load_score(module), module)
            s.title = s.title + MARK
            s.subtitle = "ТЕПЛАЯ ВЕРСИЯ: НИЖЕ И ТЕМНЕЕ"
            assert len(s.title) <= 30
            variants.append((fname[:-3] + MARK + ".YZ", s))
        for name, song in variants:
            assert len(name) <= 30, name
            data = song.build()
            disk.add(name, mkdisk840.T_BIN, build.song_body(data))
            print("  %-30s %5d байт, %d:%02d" % (name, len(data), song.stats["seconds"] // 60,
                                                song.stats["seconds"] % 60))
    with open(DISK, "wb") as f:
        f.write(bytes(disk.d))
    print("диск:", DISK)
    for ftype, name, n in mkdisk840.Disk840(bytes(disk.d)).listing():
        print("  %02X %4d  %s" % (ftype, n, name))
    hfe = os.path.splitext(DISK)[0] + ".hfe"
    if os.path.exists(hfe):
        os.remove(hfe)
    render.run(['MACHINE "agat/Agat-9-yazs.ext"',
                'COMMAND fdd0.load("%s")' % DISK.replace("\\", "/"),
                'COMMAND fdd0.save("%s")' % hfe.replace("\\", "/"),
                "EXIT"], "hfe", OUT)
    print("hfe: ", hfe, os.path.getsize(hfe), "байт")

    # Проверка: меню, затем вторая строка (теплая токката) - пульт
    shots = os.path.join(OUT, "check")
    out = render.run(['MACHINE "agat/Agat-9-yazs.ext"',
                      'COMMAND fdd0.load("%s")' % DISK.replace("\\", "/"),
                      "RESET cold", "SPEED MAX", "WAIT 12000",
                      'SCREEN "menu.png"', "LOGDEFS 8,16", "LOG ram.value($4D,$4D)",
                      "KEY 100,100,down", "WAIT 300", "KEY 100,100,ret", "WAIT 4000",
                      "COMMAND cpu.stop()", 'SCREEN "play.png"', "LOG ram.value($1E,$1F)",
                      "COMMAND cpu.run()", "KEY 100,100,esc", "WAIT 1500",
                      "KEY 100,100," + ",".join(["down"] * 23), "WAIT 300", "KEY 100,100,ret", "WAIT 12000",
                      "COMMAND cpu.stop()", 'SCREEN "anitra.png"', "COMMAND cpu.run()",
                      "KEY 100,100,ret", "WAIT 3000", "COMMAND cpu.stop()", 'SCREEN "anitra-trk.png"',
                      "EXIT"], "check", shots)
    print("\n".join(l for l in out.splitlines() if l.startswith("[ram")))


main()
