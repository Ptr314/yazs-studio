# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Мелодия SID (PSID, Commodore 64) -> .YZ для ЯЗС. Что переносится и как - docs/SID.md.

    python studio/sid2yz.py файл.sid [файл.sid ...] [ключи]

    --song N         мелодия N (по умолчанию - начальная из заголовка); --all - все
    --seconds S      не больше S секунд (без ключа - до конца или одного повтора, до 300 с)
    --out КАТАЛОГ    куда писать .yz (по умолчанию текущий)
    --chorus [1,2]   каналы 4-5 - хорус голосов с ШИМ (без номеров - два самых «шимовых»)
    --loud           огибающие с D3 и ударный 6 с D3: громче, но три голоса перегружают ячейку
    --no-loop        не искать повтор (иначе - до конца первого повтора и кадр повтора)
    --version 1|2    версия .YZ (по умолчанию младшая, в которую мелодия помещается)
    --stat           только сводка: что мелодия использует из SID, без перевода
    --frames В:С:N   покадровая распечатка голоса В (1-3) с кадра С, N кадров
    --disk ОБРАЗ     диск 840 КБ с плеером и всеми переведенными мелодиями (и .hfe)

После перевода модель движка (pyplay) играет .YZ и сверяет высоту каналов с
регистрами SID по кадрам: медиана и 95-й процентиль отклонения в центах.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compose  # noqa: E402
from sid import c64, convert, features, psid  # noqa: E402


def disk_name(sf, song, chorus):
    base = convert.agat_text(sf.name if sf.name not in ("", "<?>") else
                             os.path.splitext(os.path.basename(sf.path))[0].replace("_", " "))
    tail = (" %d" % song if sf.songs > 1 else "") + (" ХОРУС" if chorus else "")
    return ("SID." + " ".join(base.split()))[:30 - len(tail) - 3].rstrip() + tail + ".YZ"


def one(sf, song, a, results):
    tag = "%s.%02d" % (os.path.splitext(os.path.basename(sf.path))[0], song)
    try:
        d = c64.run(sf, song, a.seconds or 300)
    except (c64.Unsupported, c64.cpu6502.Halt, c64.cpu6502.Timeout) as e:
        print("%s: не переводится - %s" % (tag, e))
        return
    if a.frames:
        v, f0, n = (int(x) for x in a.frames.split(":"))
        d.print_frames(v - 1, f0, n)
        return
    if a.stat:
        features.report(features.analyze(d), tag)
        return
    lp = None if a.no_loop else features.find_loop(d)
    end = d.frames
    loop_start, from_start = None, False
    if lp and lp[0] + lp[1] <= end:
        end = lp[0] + lp[1]
        loop_start = lp[0] or None
        from_start = lp[0] == 0
    chorus = a.chorus
    if chorus and chorus != "auto":
        chorus = [int(x) for x in chorus.split(",")]
    conv = convert.Converter(d, sf, chorus=chorus, end=end, loud=a.loud, version=a.version)
    song_obj = conv.run()
    try:
        data, L, loop_frame = convert.build(song_obj, end, loop_start, from_start, a.version)
    except ValueError as e:
        print("%s: %s (попробуйте --seconds)" % (tag, e))
        return
    name = tag + (".chorus" if chorus else "")
    path = os.path.join(a.out, name + ".yz")
    open(path, "wb").write(data)
    st = song_obj.stats
    print("%s: %.1f с SID%s, кадр .YZ %d строк -> %s" % (
        tag, end / c64.FPS, (", повтор с %.1f с" % (loop_start / c64.FPS)) if loop_start else
        (", повтор с начала" if from_start else ""), L, path))
    print("  v%(version)d: %(bytes)d байт (блоков %(blocks)d), %(frames)d кадров, %(patterns)d паттернов, "
          "%(seconds)d с" % st + ", инструментов %d" % len(song_obj.instruments))
    s = conv.stats
    print("  нот %d (покадрово %d, арпеджио %d, вибрато %d+%d, лиги %d), ударных %d + %d%s" % (
        s["tonal"], s.get("frame_notes", 0), s.get("arp_notes", 0), s.get("vib_macro_notes", 0),
        s.get("vib_notes", 0), s.get("legato_notes", 0), s["drum6"], s["drum7"],
        (", хорус голосов %s" % s["chorus_of"]) if "chorus_of" in s else ""))
    v = convert.verify(data, conv, end)
    print("  высота против SID: медиана %.1f, 95%% - %.1f цента; больше 25 центов - %.1f%% строк "
          "(по видам: %s)" % (v["cents_median"], v["cents_p95"], 100 * v["share_over_25c"],
                              ", ".join("%s %s" % kv for kv in v["over_25c_by_kind"].items())))
    if v["silent_in_tonal"] or v["plan_not_exact"]:
        print("  ВНИМАНИЕ: молчит на тоновых строках %d, высота не по плану %d" % (
            v["silent_in_tonal"], v["plan_not_exact"]))
    results.append((disk_name(sf, song, chorus), data))


def main():
    ap = argparse.ArgumentParser(description="SID -> .YZ (ЯЗС Агата)")
    ap.add_argument("sid", nargs="+")
    ap.add_argument("--song", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--out", default=".")
    ap.add_argument("--chorus", nargs="?", const="auto")
    ap.add_argument("--loud", action="store_true")
    ap.add_argument("--no-loop", action="store_true")
    ap.add_argument("--version", type=int, choices=(1, 2))
    ap.add_argument("--stat", action="store_true")
    ap.add_argument("--frames")
    ap.add_argument("--disk")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    results = []
    if a.stat:
        print(features.LEGEND + "\n")
    for path in a.sid:
        sf = psid.SidFile(path)
        print(sf.describe())
        songs = range(1, sf.songs + 1) if a.all else [a.song or sf.start_song]
        for s in songs:
            one(sf, s, a, results)
    if a.disk and results:
        import build
        names = set()
        files = []
        for n, data in results:
            k = 2
            base = n
            while n in names:
                n = base[:-3][:27] + "%d.YZ" % k
                k += 1
            names.add(n)
            files.append((n, data))
        build.gen_sources()
        disk = build.player_disk(files, os.path.abspath(a.disk), os.path.abspath(a.out))
        print("диск:", os.path.abspath(a.disk))
        for ftype, name, n in disk.listing():
            print("  %02X %4d  %s" % (ftype, n, name))
        print("hfe:", build.save_hfe(os.path.abspath(a.disk), os.path.abspath(a.out)))


if __name__ == "__main__":
    main()
