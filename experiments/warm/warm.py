"""«Теплая» версия симфонии - в сторону звучания демонстрации НКЛ.

Те же ноты по названиям (лейтмотив и гармония не меняются), но:
- мелодии и аккомпанемент на октаву ниже (в скерцо аккорды на две), бас на месте,
  кроме блюза (там сдвинута вся часть: бас шел выше аккомпанемента) и скерцо;
- полосы инструментов к НЧ и НЧ+СЧ: все/СЧ+ВЧ/СЧ -> НЧ+СЧ, ВЧ -> СЧ, НЧ+ВЧ -> НЧ;
  эффекты BUS в партитуре (развертка «фильтра» в синтвейве) не тронуты;
- ударные без D3 (короче и тише, как в демо).
Фактура, темп, огибающие и эффекты высоты - как в основной версии.

    python experiments/warm/warm.py build        диск dist/yazs-player-warm.dsk (и .hfe)
    python experiments/warm/warm.py listen [m..] WAV и MP3 частей в out/warm/listen
    python warm.py check        скрещивания с басом после сдвига
"""
import os
import sys

YP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio"))
sys.path.insert(0, YP)
import build  # noqa: E402
import tables  # noqa: E402
from compose import CMD_LEGATO  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = ["m1_toccata", "m2_adagio", "m3_scherzo", "m4_blues", "m5_synth", "m6_finale"]

# (канал, с такта, до такта (не включая), полутонов)
SHIFT = {
    "m1_toccata": [(c, 0, None, -12) for c in range(4)],
    "m2_adagio": [(0, 12, 24, -12), (1, 0, None, -12), (2, 0, None, -12), (3, 0, None, -12)],
    "m3_scherzo": [(0, 0, None, -12), (1, 0, None, -12), (2, 0, None, -24), (3, 0, None, -24),
                   (4, 0, None, -12)],
    "m4_blues": [(c, 0, None, -12) for c in range(5)],
    "m5_synth": [(c, 0, None, -12) for c in range(4)],
    "m6_finale": [(0, 0, None, -12), (1, 48, None, -12), (2, 48, None, -12), (3, 48, None, -12)],
}
BUS = {0: 0, 1: 2, 2: 6, 3: 6, 4: 4, 5: 4, 6: 6, 7: 6}


def is_note(c):
    return c[0] < 0x60 or c[0] == CMD_LEGATO


def warm(song, module):
    for ch, b0, b1, d in SHIFT.get(module, []):
        r0 = b0 * song.bar_rows
        r1 = b1 * song.bar_rows if b1 is not None else 10 ** 9
        for r, cmds in song.rows[ch].items():
            if not r0 <= r < r1:
                continue
            for i, c in enumerate(cmds):
                if c[0] == CMD_LEGATO:
                    n = c[1] + d
                    cmds[i] = (CMD_LEGATO, n)
                elif c[0] < 0x60:
                    n = c[0] + d
                    cmds[i] = (n,)
                else:
                    continue
                if not 0 <= n < 96:
                    raise ValueError("%s: канал %d строка %d нота %d" % (module, ch, r, n))
    for ins in song.instruments:
        ins.reg = [(v & ~7) | BUS[v & 7] for v in ins.reg]
        ins.rel = [(v & ~7) | BUS[v & 7] for v in ins.rel]
    for ch in (5, 6):
        for r, cmds in song.rows[ch].items():
            cmds[:] = [(c[0] & 0x07,) if c[0] < 0x60 else c for c in cmds]
    # Подписи на экране - под новые полосы и ударные без D3
    for a, b in TEXTS:
        a, b = tables.agat(a), tables.agat(b)
        song.texts = [t.replace(a, b) for t in song.texts]
    return song


TEXTS = [("НЧ+СЧ+ВЧ", "НЧ+СЧ"), ("СЧ+ВЧ", "НЧ+СЧ"), (", D3 - ГРОМЧЕ", "")]


_orig = build.load_score


def load_warm(name):
    return warm(_orig(name), name)


def sounding(song, ch):
    """Строка -> нота канала (держится до следующей ноты или отпускания)"""
    out = {}
    cur = None
    rows = song.rows[ch]
    for r in range(song.end_row + 1):
        for c in rows.get(r, []):
            if is_note(c):
                cur = c[-1] if c[0] == CMD_LEGATO else c[0]
            elif c[0] in (0x60, 0x61):
                cur = None
        if cur is not None:
            out[r] = cur
    return out


def check():
    for m in PARTS:
        s = load_warm(m)
        bass = sounding(s, 4)
        print("==", m)
        for ch in range(4):
            v = sounding(s, ch)
            both = [r for r in v if r in bass]
            below = [r for r in both if v[r] < bass[r]]
            same = [r for r in both if v[r] == bass[r]]
            if below or same:
                bars = sorted(set(r // s.bar_rows for r in below))
                print("  к%d ниже баса %d строк из %d (такты %s), в унисон %d" % (
                    ch, len(below), len(both), bars[:12], len(same)))


def main():
    build.load_score = load_warm
    cmd = sys.argv[1]
    if cmd == "build":
        build.SONGS = [s for s in build.SONGS if s[0] in PARTS]
        sys.argv = ["build.py", "--out", os.path.join(build.OUT, "warm"),
                    "--disk", os.path.join(build.DIST, "yazs-player-warm.dsk")]
        build.main()
    elif cmd == "listen":
        import listen
        for m in sys.argv[2:] or PARTS:
            sys.argv = ["listen.py", m, "--mp3", "--out", os.path.join(build.OUT, "warm", "listen")]
            listen.main()
    elif cmd == "check":
        check()


if __name__ == "__main__":
    main()
