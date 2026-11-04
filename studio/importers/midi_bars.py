"""Обзор MIDI по тактам: на такт - какие дорожки играют, сколько нот, верх/низ.
    python studio/importers/midi_bars.py file.mid [долей_в_такте] [такт_от] [такт_до] [--notes дорожка,...]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midi_dump import parse, nm   # noqa: E402


def main():
    path = sys.argv[1]
    bpb = float(sys.argv[2]) if len(sys.argv) > 2 else 2
    b0 = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    b1 = int(sys.argv[4]) if len(sys.argv) > 4 else 10 ** 6
    show = []
    if "--notes" in sys.argv:
        show = [int(x) for x in sys.argv[sys.argv.index("--notes") + 1].split(",")]
    div, tracks = parse(path)
    names = []
    for meta, notes in tracks:
        nmx = [m[1] for m in meta if m[0] == "name"]
        names.append((nmx[0] if nmx else "")[:10])
    last = max((n[0] for _, ns in tracks for n in ns), default=0)
    for b in range(b0, min(b1, int(last // bpb) + 1)):
        s0, s1 = b * bpb, (b + 1) * bpb
        cells = []
        for k, (meta, notes) in enumerate(tracks):
            ns = [n for n in notes if s0 <= n[0] < s1]
            if ns:
                cells.append("%d:%s %d %s-%s" % (k, names[k], len(ns), nm(min(n[2] for n in ns)),
                                                 nm(max(n[2] for n in ns))))
        print("такт %3d (%.1f): %s" % (b, s0, " | ".join(cells)))
        for k in show:
            ns = [n for n in tracks[k][1] if s0 <= n[0] < s1]
            if ns:
                # по моментам: аккорды через +
                by = {}
                for s, l, a, v, ch in ns:
                    by.setdefault(round((s - s0) * 4, 2), []).append((a, l))
                print("      %2d: %s" % (k, "  ".join(
                    "%g:%s/%g" % (t, "+".join(nm(a) for a, _ in sorted(x)), round(max(l for _, l in x) * 4, 2))
                    for t, x in sorted(by.items()))))


main()
