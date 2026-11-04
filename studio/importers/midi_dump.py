"""Минимальный разбор SMF: ноты по дорожкам в долях (четвертях).
    python studio/importers/midi_dump.py file.mid [дорожка] [доли_от] [доли_до]"""
import struct
import sys

NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]


def vlq(d, i):
    v = 0
    while True:
        b = d[i]
        i += 1
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            return v, i


def parse(path):
    d = open(path, "rb").read()
    assert d[:4] == b"MThd"
    fmt, ntr, div = struct.unpack(">HHH", d[8:14])
    i = 14
    tracks = []
    for _ in range(ntr):
        assert d[i:i + 4] == b"MTrk", d[i:i + 4]
        ln = struct.unpack(">I", d[i + 4:i + 8])[0]
        t = d[i + 8:i + 8 + ln]
        i += 8 + ln
        notes, meta, on = [], [], {}
        p, tick, run = 0, 0, 0
        while p < len(t):
            dt, p = vlq(t, p)
            tick += dt
            st = t[p]
            if st & 0x80:
                p += 1
                run = st
            else:
                st = run
            if st == 0xFF:
                typ = t[p]
                l, p = vlq(t, p + 1)
                data = t[p:p + l]
                p += l
                if typ == 0x03:
                    meta.append(("name", data.decode("latin-1")))
                elif typ == 0x51:
                    meta.append(("tempo", tick, 60e6 / int.from_bytes(data, "big")))
                elif typ == 0x58:
                    meta.append(("time", tick, data[0], 2 ** data[1]))
                elif typ == 0x59:
                    meta.append(("key", tick, struct.unpack("b", data[:1])[0], data[1]))
            elif st in (0xF0, 0xF7):
                l, p = vlq(t, p)
                p += l
            else:
                hi = st & 0xF0
                ch = st & 0x0F
                if hi in (0xC0, 0xD0):
                    if hi == 0xC0:
                        meta.append(("prog", tick, ch, t[p]))
                    p += 1
                    continue
                a, b = t[p], t[p + 1]
                p += 2
                if hi == 0x90 and b:
                    on[(ch, a)] = (tick, b)
                elif hi == 0x80 or (hi == 0x90 and not b):
                    if (ch, a) in on:
                        s, v = on.pop((ch, a))
                        notes.append((s / div, (tick - s) / div, a, v, ch))
        notes.sort()
        tracks.append((meta, notes))
    return div, tracks


def nm(n):
    return "%s%d" % (NAMES[n % 12], n // 12 - 1)


def main():
    div, tracks = parse(sys.argv[1])
    sel = int(sys.argv[2]) if len(sys.argv) > 2 else None
    b0 = float(sys.argv[3]) if len(sys.argv) > 3 else 0
    b1 = float(sys.argv[4]) if len(sys.argv) > 4 else 1e9
    for k, (meta, notes) in enumerate(tracks):
        if sel is not None and k != sel:
            continue
        lo = min((n[2] for n in notes), default=0)
        hi = max((n[2] for n in notes), default=0)
        print("== дорожка %d: %d нот, %s..%s, %s" % (k, len(notes), nm(lo), nm(hi),
                                                    [m for m in meta][:8]))
        if sel is None:
            continue
        for s, l, a, v, ch in notes:
            if b0 <= s < b1:
                print("%8.3f %6.3f %-4s v%d" % (s, l, nm(a), v))


if __name__ == "__main__":
    main()
