# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Компиляторы вариантов встраиваемого плеера: набор .YZ игры -> текст для AS65
(игра = плеер + общие данные + мелодии со входом tune_NN). Варианты и форматы -
README.md рядом, плееры - players/*.a65.

    compile_game(вариант, [данные .yz...]) -> Game
    assemble(game, каталог) -> (двоичный образ, символы); game.sizes() - байты по частям

Время во всех вариантах - тики модели: снимается прогоном studio/pyplay.py.
"""

import collections
import os
import re
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
STUDIO = os.path.join(ROOT, "studio")
if STUDIO not in sys.path:
    sys.path.insert(0, STUDIO)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pyplay                   # noqa: E402
import tables                   # noqa: E402
import run6502                  # noqa: E402

AS65 = os.path.join(ROOT, "third_party", "as65", "as65.exe")
PLAYERS = os.path.join(HERE, "players")
ORG = 0x4000
YZ_ZP = 0x10
YZ_RAM = 0x0900
CNT = (0, 1, 2, 4, 5)           # регистры счетчиков тоновых каналов 1-5
VARIANTS = ("A", "C", "B1", "B2", "E", "D")


def w16(d, o):
    return d[o] | (d[o + 1] << 8)


def s8(v):
    return v - 256 if v & 0x80 else v


class CompileError(Exception):
    pass


# --- .YZ v1 по частям ---

class Macro(object):
    def __init__(self, d, a):
        self.ln, self.loop = d[a], d[a + 1]
        self.vals = list(d[a + 2:a + 2 + self.ln])

    def raw(self):
        return [self.ln, self.loop] + self.vals

    def key(self):
        return (self.ln, self.loop, tuple(self.vals))


class Instrument(object):
    def __init__(self, d, base):
        self.vdl, self.vsp, self.vdp, self.det = d[base + 9], d[base + 10], d[base + 11], d[base + 12]
        self.reg = Macro(d, base + d[base + 13])
        self.rel = Macro(d, base + d[base + 14])
        self.arp = Macro(d, base + d[base + 15]) if d[base + 15] else None
        self.pit = Macro(d, base + d[base + 16]) if d[base + 16] else None


class YZ(object):
    def __init__(self, data, name=""):
        d = self.d = bytes(data)
        if d[:2] != b"YZ" or d[2] != 1:
            raise CompileError("%s: нужен .YZ версии 1" % name)
        self.name = name
        self.n, self.speed, self.nframes = d[66], d[67], d[68]
        o_ord, o_pat, o_ins, o_txt = w16(d, 70), w16(d, 72), w16(d, 74), w16(d, 76)
        self.frames = [(d[o_ord + 9 * f], list(d[o_ord + 9 * f + 1:o_ord + 9 * f + 9]))
                       for f in range(self.nframes)]
        self.pat_off = [w16(d, o_pat + 2 * i) for i in range((o_ins - o_pat) // 2)]
        self.ins = [Instrument(d, w16(d, o_ins + 2 * i)) for i in range((o_txt - o_ins) // 2)]
        self.pat_rows = {}
        for rows, pats in self.frames:
            for p in pats:
                self.pat_rows.setdefault(p, rows)

    def pattern(self, p):
        """байты паттерна p (по числу строк его кадра)"""
        d, pos, rows, r = self.d, self.pat_off[p], self.pat_rows[p], 0
        start = pos
        while r < rows:
            b = d[pos]
            pos += 1
            if b >= 0x80:
                r += b - 0x7F
            elif b in (0x62, 0x63) or b >= 0x64:
                pos += 1
        return list(d[start:pos])

    def pattern_rows(self, p):
        """паттерн p по строкам: список команд [(байт, параметр|None)] на строку"""
        d, pos, rows = self.d, self.pat_off[p], self.pat_rows[p]
        out, cur = [], []
        while len(out) < rows:
            b = d[pos]
            pos += 1
            if b >= 0x80:
                out.append(cur)
                cur = []
                out.extend([] for _ in range(b - 0x80))
            elif b in (0x62, 0x63) or b >= 0x64:
                cur.append((b, d[pos]))
                pos += 1
            else:
                cur.append((b, None))
        return out[:rows]


def encode_rows(rows):
    """строки команд -> байты паттерна ($80+n - конец строки и n пустых)"""
    out = []
    i = 0
    while i < len(rows):
        for b, p in rows[i]:
            out.append(b)
            if p is not None:
                out.append(p)
        j = i + 1
        while j < len(rows) and not rows[j] and j - i - 1 < 127:
            j += 1
        out.append(0x80 + (j - i - 1))
        i = j
    return out


# --- Снятие событий с модели ---

class Trace(pyplay.Player):
    """Модель с журналом: разбор нот по (тик, канал, кадр, строка), состояние
    каналов после каждого тика, эффекты"""

    def __init__(self, data):
        self.parsed = []
        self.snap = []
        self.fx = collections.Counter()
        self.cmds = collections.Counter()
        pyplay.Player.__init__(self, data)

    def parse(self, ch):
        if ch >= 5:
            w0 = self.wait[ch]
            pos = self.ptr[ch]
            pyplay.Player.parse(self, ch)
            if w0 == 0 and self.d[pos] < 0x80:
                self.cmds["канал %d" % (ch + 1)] += 1
            return
        t = self.tone[ch]
        st0, w0 = t.state, self.wait[ch]
        pyplay.Player.parse(self, ch)
        if w0:
            return
        if st0 == 1 and t.state == 2:
            self.parsed.append((self.ticks, ch, "off", None, self.frame, self.row))
        if st0 != 0 and t.state == 0:
            self.parsed.append((self.ticks, ch, "cut", None, self.frame, self.row))
        if t.pend == "note":
            self.parsed.append((self.ticks, ch, "note", t.pend_note, self.frame, self.row))
        elif t.pend == "legato":
            self.cmds["лига"] += 1

    def effect(self, ch, t, e, p):
        self.fx[e] += 1
        pyplay.Player.effect(self, ch, t, e, p)

    def step(self):
        r = pyplay.Player.step(self)
        self.snap.append([(t.state, t.last_per, t.ins, t.delay) for t in self.tone])
        return r


class Events(object):
    """Мелодия для вариантов C и D: ноты по каналам с периодом и инструментом
    удара, конец мелодии в тиках. Проверяет, что высота меняется только при
    ударе, а регистры - только по макросам инструментов"""

    def __init__(self, yz, ref):
        tr = Trace(yz.d)
        while tr.step():
            pass
        self.end = tr.ticks
        bad = [e for e in tr.fx if e not in (5, 13, 14)]
        if bad or tr.cmds:
            raise CompileError("%s: эффекты %s, команды %s - не для нотного варианта" % (
                yz.name, sorted(bad), dict(tr.cmds)))
        self.ch = collections.defaultdict(list)       # канал -> [(тик, вид, период, инстр.)]
        self.at = {}                                  # (кадр, канал, строка) -> (период, инстр.)
        for tick, ch, kind, note, frame, row in tr.parsed:
            if kind == "note":
                st, per, ins, delay = tr.snap[tick + 1][ch]
                if delay:
                    raise CompileError("%s: DELAY" % yz.name)
                self.ch[ch].append((tick, "note", per, ins))
                key = (frame, ch, row)
                if self.at.get(key, (per, ins)) != (per, ins):
                    raise CompileError("%s: паттерн звучит по-разному в разных местах" % yz.name)
                self.at[key] = (per, ins)
            else:
                self.ch[ch].append((tick, kind, None, None))
        # счетчики пишутся только в тик удара своего канала
        hits = set((tick + 1, ch) for tick, ch, kind, *_ in tr.parsed if kind == "note")
        for k, ws in enumerate(ref.ticks):
            for a, v in ws:
                if a in CNT and (k, CNT.index(a)) not in hits:
                    raise CompileError("%s: высота меняется не при ударе (тик %d)" % (yz.name, k))
                if a in (6, 13, 14):
                    raise CompileError("%s: TEMPO или ударные" % yz.name)
        self.used = sorted(self.ch)
        self.yz = yz


def rle(m):
    """Макрос модели -> пары (тиков, значение) и пара повтора: [(n, v)...], j"""
    vals = m.vals
    loop = m.loop if m.loop != 0xFF else len(vals) - 1
    runs = []
    for i, v in enumerate(vals):
        if runs and runs[-1][1] == v and i != loop and runs[-1][0] < 255:
            runs[-1][0] += 1
        else:
            if i == loop:
                j = len(runs)
            runs.append([1, v])
    return [tuple(r) for r in runs], j


def env_record(ins):
    """Запись инструмента C/D: +0 смещение отпускания, пары, (0, смещение повтора)"""
    out = [0]
    for k, m in enumerate((ins.reg, ins.rel)):
        if k == 1:
            out[0] = len(out)
        runs, j = rle(m)
        base = len(out)
        for n, v in runs:
            out += [n, v]
        out += [0, base + 2 * j]
    if len(out) > 255:
        raise CompileError("инструмент длиннее 255 байт")
    return out


# --- Текст для AS65 ---

class Game(object):
    """Текст игры по частям: code (плеер), shared (общие данные), tNN (мелодии)"""

    def __init__(self, variant, names):
        self.variant = variant
        self.names = names
        self.equ = []           # (имя, значение)
        self.includes = []
        self.parts = collections.OrderedDict()
        self.calc = {}          # размеры без плеера (расчет)
        self.notes = []

    def part(self, name):
        return self.parts.setdefault(name, [])

    def db(self, part, data, label=None):
        lines = self.part(part)
        data = list(data)
        if label:
            lines.append(label)
        for i in range(0, len(data), 16):
            lines.append("            db " + ",".join("$%02X" % (b & 255) for b in data[i:i + 16]))

    def dw(self, part, words, label=None):
        lines = self.part(part)
        if label:
            lines.append(label)
        for i in range(0, len(words), 8):
            lines.append("            dw " + ",".join(str(x) for x in words[i:i + 8]))

    def raw(self, part, line):
        self.part(part).append(line)

    def source(self):
        out = ["; Сгенерировано experiments/embed/variants.py: вариант %s" % self.variant, ""]
        for k, v in self.equ:
            out.append("%-11s equ %s" % (k, v))
        out += ["", "            org $%04X" % ORG, "drv"]
        for i in range(len(self.names)):
            out.append("            jsr tune_%02d" % (i + 1))
        out += ["drv_end     jmp drv_end", "p_start"]
        for inc in self.includes:
            out.append('            include "%s"' % os.path.join(PLAYERS, inc).replace("\\", "/"))
        out.append("p_end")
        for name, lines in self.parts.items():
            out.append("%s_start" % name)
            out += lines
            out.append("%s_end" % name)
        out.append("game_end")
        return "\n".join(out) + "\n"


def zp_ram(game, zp, ram):
    """Переменные: zp - [(имя, байт)], ram - [(имя, байт)]"""
    a = YZ_ZP
    for name, n in zp:
        game.equ.append((name, "$%02X" % a))
        a += n
    game.zp_bytes = a - YZ_ZP
    a = YZ_RAM
    for name, n in ram:
        game.equ.append((name, "$%04X" % a))
        a += n
    game.ram_bytes = a - YZ_RAM


def common_equ(game, tail=True):
    game.equ += [("YZ_CARD", "$C090"), ("YZ_TAIL", str(run6502.TAIL if tail else 0))]


def entry(game, k):
    game.raw("t%02d" % (k + 1), "tune_%02d     jsr yzplay" % (k + 1))


def same(vals):
    return len(set(vals)) == 1


# --- A: универсальный движок, .YZ без строк ---

def compile_A(yzs, tail=True):
    g = Game("A", [y.name for y in yzs])
    common_equ(g, tail)
    zp_ram(g, [("yzp", 2), ("zt", 2), ("ip", 2), ("t0", 1), ("t1", 1), ("t2", 1), ("t3", 1),
               ("tick", 1), ("speed", 1), ("row", 1), ("frows", 1), ("frame", 1), ("frames", 1),
               ("jump", 1), ("brkf", 1), ("ended", 1), ("ntimer", 1), ("ch", 1), ("ch2", 1),
               ("tot", 2), ("per", 2), ("oct", 1), ("mpos", 1), ("moff", 1), ("mval", 1),
               ("vibv", 1), ("ordp", 2), ("ptabp", 2), ("itabp", 2), ("tmp16", 2), ("tail", 1),
               ("patp", 16)],
           [(n, 8) for n in ("c_ins", "c_pend", "c_pnote", "c_pins", "c_delay", "c_cut",
                             "c_cutreq", "c_state", "c_regpos", "c_arppos", "c_pitpos", "c_curlo",
                             "c_curhi", "c_tgtlo", "c_tgthi", "c_porta", "c_slide", "c_arpfx",
                             "c_arpph", "c_vibfx", "c_vibcnt", "c_vibph", "c_det", "c_bus",
                             "c_trem", "c_tremph", "c_trans", "c_retrig", "c_retcnt", "c_lreg",
                             "c_lperlo", "c_lperhi", "c_wait", "c_pdirty")]
           + [("d_pend", 2), ("d_preset", 2)])
    g.includes = ["common.a65", "trk_full.a65"]
    # таблицы движка - как gen_tables.a65 плеера Студии; вибрато - с границы страницы
    ptab = tables.period_table()
    g.raw("shared", "            align 256")
    g.raw("shared", "tab_start")
    g.db("shared", tables.vibrato_table(), "vibtab")
    g.db("shared", [p & 255 for p in ptab], "ptab_lo")
    g.db("shared", [p >> 8 for p in ptab], "ptab_hi")
    g.db("shared", [n // 12 for n in range(96)], "div12")
    g.db("shared", [n % 12 for n in range(96)], "mod12")
    g.db("shared", [0] + [(1 << (o - 1)) & 255 for o in range(1, 8)], "rnd_lo")
    g.db("shared", [0] + [(1 << (o - 1)) >> 8 for o in range(1, 8)], "rnd_hi")
    for k, y in enumerate(yzs):
        t = "t%02d" % (k + 1)
        p = "a%02d_" % (k + 1)
        entry(g, k)
        g.db(t, [y.n, y.speed, y.nframes])
        g.dw(t, [p + "pt", p + "it"])
        for rows, pats in y.frames:
            g.db(t, [rows] + pats)
        g.dw(t, [p + "p%d" % i for i in range(len(y.pat_off))], p + "pt")
        g.dw(t, [p + "i%d" % i for i in range(len(y.ins))], p + "it")
        for i, ins in enumerate(y.ins):
            rec = [ins.vdl, ins.vsp, ins.vdp, ins.det, 0, 0, 0, 0]
            for slot, m in ((4, ins.reg), (5, ins.rel), (6, ins.arp), (7, ins.pit)):
                if m is not None:
                    rec[slot] = len(rec)
                    rec += m.raw()
            g.db(t, rec, p + "i%d" % i)
        for i in range(len(y.pat_off)):
            g.db(t, y.pattern(i) if i in y.pat_rows else [0x80], p + "p%d" % i)
    return g


# --- Общее для C и D: словари игры ---

class Dicts(object):
    """Словари игры: периоды (по частоте), инструменты (RLE), занятые каналы.
    reserve31 - индекс 31 не занимать (в D это пауза)"""

    def __init__(self, evs, reserve31=False):
        per = collections.Counter()
        self.ins_key = {}
        self.ins = []
        self.ins_rec = []
        for ev in evs:
            for ch, lst in ev.ch.items():
                for tick, kind, p, i in lst:
                    if kind == "note":
                        per[p] += 1
                        self.ins_id(ev.yz, i)
        self.per = [p for p, _ in sorted(per.items(), key=lambda x: (-x[1], x[0]))]
        if reserve31 and len(self.per) > 31:
            self.per.insert(31, 0)
        self.per_i = {p: i for i, p in enumerate(self.per) if not (reserve31 and i == 31)}
        if len(self.per) > 0x60:
            raise CompileError("в словаре периодов больше 96 значений")
        chans = set()
        for ev in evs:
            chans |= set(ev.used)
        self.chans = sorted(chans)

    def ins_id(self, yz, i):
        ins = yz.ins[i]
        if ins.arp or ins.pit or ins.vdp:
            raise CompileError("%s: у инструмента %d арпеджио, высота или вибрато" % (yz.name, i))
        key = (ins.reg.key(), ins.rel.key())
        if key not in self.ins_key:
            self.ins_key[key] = len(self.ins)
            self.ins.append(key)
            self.ins_rec.append(env_record(ins))
        return self.ins_key[key]

    def emit(self, g):
        nch = len(self.chans)
        tab = []
        for c in self.chans:
            tab += [8 + c, CNT[c]]
        g.db("shared", tab, "ch_tab")
        g.db("shared", [p & 255 for p in self.per], "pd_lo")
        g.db("shared", [p >> 8 for p in self.per], "pd_hi")
        g.raw("shared", "in_lo")
        g.raw("shared", "            db " + ",".join("lo(ins_%d)" % i for i in range(len(self.ins))))
        g.raw("shared", "in_hi")
        g.raw("shared", "            db " + ",".join("hi(ins_%d)" % i for i in range(len(self.ins))))
        for i, rec in enumerate(self.ins_rec):
            g.db("shared", rec, "ins_%d" % i)
        return nch


def tone_vars(g, nch, extra_zp, extra_ram):
    """Переменные C и D; c_pend, c_state, c_lreg, c_wait - подряд (ch_init)"""
    n = 2 * nch
    zp_ram(g, [("yzp", 2), ("ip", 2), ("chp", n)] + extra_zp,
           [(x, n) for x in ("c_pend", "c_state", "c_lreg", "c_wait", "c_lnote", "c_note",
                             "c_pins", "c_ins", "c_ec", "c_eo")] + extra_ram)
    g.equ.append(("NCH", str(nch)))


def game_consts(g, yzs, speed=False):
    """N (и speed) - константа сборки, если одинаковы у всех мелодий"""
    hdr_n = not same([y.n for y in yzs])
    g.equ += [("YZ_HDR_N", "1" if hdr_n else "0"), ("YZ_N", str(yzs[0].n))]
    if speed:
        if not same([y.speed for y in yzs]):
            raise CompileError("speed разный - вариант C пока не собирается")
        g.equ.append(("YZ_SPEED", str(yzs[0].speed)))
    return hdr_n


# --- C: трекер под набор, кадры только занятых каналов ---

def compile_C(yzs, refs, tail=True):
    g = Game("C", [y.name for y in yzs])
    common_equ(g, tail)
    evs = [Events(y, r) for y, r in zip(yzs, refs)]
    dic = Dicts(evs)
    nch = len(dic.chans)
    tone_vars(g, nch, [("fp", 2), ("nfr", 1), ("tick", 1), ("row", 1), ("frows", 1),
                       ("ended", 1), ("tail", 1)], [])
    hdr_n = game_consts(g, yzs, speed=True)
    g.includes = ["common.a65", "trk_min.a65", "tone.a65"]
    dic.emit(g)
    # паттерны: ноты -> индексы словаря, инструменты -> номера игры, DET/TEXT/TR убраны
    pats = collections.OrderedDict()      # байты -> (метка, мелодии)
    tune_frames = []
    for k, (y, ev) in enumerate(zip(yzs, evs)):
        frames = []
        ins_seen = set()        # c_pins плеер не обнуляет: инструмент - до первой ноты
        for f, (rows, pnums) in enumerate(y.frames):
            refs_f = []
            for c in dic.chans:
                out = []
                for r, cmds in enumerate(y.pattern_rows(pnums[c])):
                    cur = []
                    for b, p in cmds:
                        if b < 0x60:
                            if c not in ins_seen:
                                raise CompileError("%s: нота без инструмента" % y.name)
                            per, ins = ev.at[(f, c, r)]
                            cur.append((dic.per_i[per], None))
                        elif b == 0x62:
                            ins_seen.add(c)
                            cur.append((0x62, dic.ins_id(y, p)))
                        elif b in (0x64 + 5, 0x64 + 13, 0x64 + 14):
                            pass
                        else:
                            raise CompileError("%s: команда $%02X" % (y.name, b))
                    out.append(cur)
                data = tuple(encode_rows(out))
                if data not in pats:
                    pats[data] = ("cp%d" % len(pats), set())
                pats[data][1].add(k)
                refs_f.append(pats[data][0])
            frames.append((rows, refs_f))
        tune_frames.append(frames)
    for k, y in enumerate(yzs):
        t = "t%02d" % (k + 1)
        entry(g, k)
        if hdr_n:
            g.db(t, [y.n])
        g.db(t, [len(tune_frames[k])])
        for rows, refs_f in tune_frames[k]:
            g.db(t, [rows])
            g.dw(t, refs_f)
    for data, (label, users) in pats.items():
        part = "t%02d" % (min(users) + 1) if len(users) == 1 else "shared"
        g.db(part, data, label)
    g.calc["zlib_data"] = deflate_parts(g, dic)
    return g


# --- B: поток регистров ---

def stream_ticks(ref):
    return ref.ticks


def compile_B(yzs, refs, dense=True, ref_lz=False, tail=True):
    g = Game("E" if ref_lz else ("B2" if dense else "B1"), [y.name for y in yzs])
    common_equ(g, tail)
    zp_ram(g, [("yzp", 2), ("t0", 1), ("t1", 1), ("left", 1), ("rsav", 2)], [])
    hdr_n = game_consts(g, yzs)
    g.equ += [("B_DENSE", "1" if dense else "0"), ("B_REF", "1" if ref_lz else "0")]
    g.includes = ["common.a65", "reg.a65"]
    ticks_all = [r.ticks if tail else r.ticks[:r.music_ticks] for r in refs]
    rv, pd = [], []
    if dense:
        rvc, pdc = collections.Counter(), collections.Counter()
        for tk in ticks_all:
            for ws in tk:
                i = 0
                while i < len(ws):
                    a, v = ws[i]
                    if a in CNT and i + 1 < len(ws) and ws[i + 1][0] == a:
                        pdc[v | (ws[i + 1][1] << 8)] += 1
                        i += 2
                        continue
                    if 8 <= a <= 12:
                        rvc[v] += 1
                    i += 1
        rv = [v for v, _ in sorted(rvc.items(), key=lambda x: (-x[1], x[0]))][:8]
        pd = [p for p, _ in sorted(pdc.items(), key=lambda x: (-x[1], x[0]))][:256]
        g.db("shared", rv or [0], "rv_t")
        g.db("shared", list(CNT), "cnt_t")
        g.db("shared", [p & 255 for p in pd] or [0], "pd_lo")
        g.db("shared", [p >> 8 for p in pd] or [0], "pd_hi")
    rvi = {v: i for i, v in enumerate(rv)}
    pdi = {p: i for i, p in enumerate(pd)}
    streams = []
    for k, tk in enumerate(ticks_all):
        toks = []
        idle_max = 62 if dense else 126
        eot = 0xC0 if dense else 0x80

        def gap(n):
            # n пустых тиков после текущего
            while n > idle_max:
                toks.append((eot + idle_max,))
                n -= idle_max + 1
            toks.append((eot + n,))

        last = None
        for t, ws in enumerate(tk):
            if not ws:
                continue
            if last is None:
                if t > 0:
                    gap(t - 1)
            else:
                gap(t - last - 1)
            i = 0
            while i < len(ws):
                a, v = ws[i]
                if dense and a in CNT and i + 1 < len(ws) and ws[i + 1][0] == a and \
                        (v | (ws[i + 1][1] << 8)) in pdi:
                    toks.append((0x80 + (CNT.index(a) << 3), pdi[v | (ws[i + 1][1] << 8)]))
                    i += 2
                    continue
                if dense and 8 <= a <= 12 and v in rvi:
                    toks.append((0x40 + ((a - 8) << 3) + rvi[v],))
                elif a == 15 or a in (3, 7):
                    raise CompileError("запись в +%d" % a)
                else:
                    toks.append((a, v))
                i += 1
            last = t
        n = len(tk)
        if last is None:
            gap(n - 2) if n >= 2 else None
        elif last < n - 1:
            gap(n - 1 - last - 1)
        toks.append((0xFF,))
        streams.append(toks)
    if ref_lz:
        streams = lz_refs(streams)
    for k, (y, toks) in enumerate(zip(yzs, streams)):
        t = "t%02d" % (k + 1)
        entry(g, k)
        if hdr_n:
            g.db(t, [y.n])
        put_tokens(g, t, toks, "b%02d_" % (k + 1))
    g.calc["zlib_data"] = sum(raw_deflate(bytes(b for tok in s if tok[0] not in ("ref", "lab")
                                                for b in tok)) for s in streams)
    return g


def raw_deflate(data):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return len(c.compress(data) + c.flush())


def put_tokens(g, part, toks, prefix):
    """Токены потока: кортежи байт, ("ref", метка-1, n), ("lab", метка)"""
    buf = []

    def flush():
        if buf:
            g.db(part, buf)
            del buf[:]

    for tok in toks:
        if tok[0] == "lab":
            flush()
            g.raw(part, tok[1])
        elif tok[0] == "ref":
            flush()
            g.raw(part, "            db $0F")
            g.raw(part, "            dw %s-1" % tok[1])
            g.raw(part, "            db %d" % tok[2])
        else:
            buf += list(tok)
    flush()


def lz_refs(streams, min_bytes=5):
    """E: повторы - ссылками на уже лежащие в памяти токены (только из
    буквальных участков, по границам токенов). Мелодии лежат в порядке номеров"""
    lit = []                 # (мелодия, позиция токена) буквальных токенов в памяти
    index = collections.defaultdict(list)   # (tok, tok) -> [(s, i)]
    out = []
    labels = {}
    lab_n = [0]

    def label_of(s, i):
        key = (s, i)
        if key not in labels:
            labels[key] = "lz%d" % lab_n[0]
            lab_n[0] += 1
        return labels[key]

    literal = []            # по мелодиям: list[bool] буквальности токенов в итоговом потоке
    placed = []             # по мелодиям: исходные токены, лежащие буквально (позиции)
    for s, toks in enumerate(streams):
        res = []
        islit = [False] * len(toks)
        i = 0
        while i < len(toks):
            best = None
            if i + 1 < len(toks):
                for (s2, j) in index.get((toks[i], toks[i + 1]), ()):
                    src = streams[s2]
                    lit2 = literal[s2] if s2 < s else islit
                    n, nb = 0, 0
                    while (i + n < len(toks) and j + n < len(src) and src[j + n] == toks[i + n]
                           and lit2[j + n] and (s2 < s or j + n < i) and nb + len(toks[i + n]) <= 255
                           and toks[i + n][0] != 0xFF):
                        nb += len(toks[i + n])
                        n += 1
                    if nb >= min_bytes and (best is None or nb > best[2]):
                        best = (s2, j, nb, n)
            if best:
                s2, j, nb, n = best
                res.append(("ref", label_of(s2, j), nb))
                i += n
            else:
                islit[i] = True
                res.append(("src", i))
                if i >= 1 and islit[i - 1]:
                    index[(toks[i - 1], toks[i])].append((s, i - 1))
                i += 1
        literal.append(islit)
        out.append(res)
    final = []
    for s, res in enumerate(out):
        toks = []
        for r in res:
            if r[0] == "src":
                key = (s, r[1])
                if key in labels:
                    toks.append(("lab", labels[key]))
                toks.append(streams[s][r[1]])
            else:
                toks.append(r)
        final.append(toks)
    return final


# --- D: нотный поток каналов ---

def d_tokens(ev, dic, k):
    """Токены каналов мелодии (без кодировки длительностей): по каналу игры
    список ("ins", i) / ("note", n, d) / ("rest", d) / ("off",) / ("cut",) / ("end",)"""
    out = []
    for ci, c in enumerate(dic.chans):
        lst = ev.ch.get(c, [])
        toks = []
        cur_ins = None
        time = 0

        def rest(n):
            while n > 0:
                toks.append(("rest", min(n, 255)))
                n -= min(n, 255)

        for i, (tick, kind, per, ins) in enumerate(lst):
            nxt = lst[i + 1][0] if i + 1 < len(lst) else ev.end
            if tick > time:
                rest(tick - time)
            if kind == "note":
                gi = dic.ins_id(ev.yz, ins)
                if gi != cur_ins:
                    toks.append(("ins", gi))
                    cur_ins = gi
                d = nxt - tick
                toks.append(("note", dic.per_i[per], min(d, 255)))
                rest(d - min(d, 255))
            else:
                toks.append((kind,))
                rest(nxt - tick)
            time = nxt
        if not lst:
            rest(ev.end)
        if ci == 0:
            toks.append(("end",))
        out.append(toks)
    return out


def d2_bytes(tok, durs):
    kind = tok[0]
    if kind == "ins":
        return (0xE0 + tok[1],)
    if kind in ("note", "rest"):
        n, d = (tok[1], tok[2]) if kind == "note" else (31, tok[1])
        if n < 32 and d in durs:
            return ((durs.index(d) << 5) | n,)
        return (0xF0, n, d)
    if kind == "end":
        return (0xFF,)
    raise CompileError("D: %s" % kind)


def d1_bytes(tok, state, durs):
    """D1 (только расчет): нота байтом с текущей длительностью"""
    kind = tok[0]
    if kind == "note":
        n, d = tok[1], tok[2]
        out = ()
        if state.get("L") != d:
            state["L"] = d
            out = (0xC0 + durs.index(d),) if d in durs else (0xDF, d)
        return out + (n,)
    if kind == "ins":
        return (0xE0 + tok[1],)
    if kind == "rest":
        return (0xF1, tok[1])
    if kind == "end":
        return (0xFF,)
    raise CompileError("D1: %s" % kind)


def phrases(streams, call_len=3, ret_len=1, max_len=64):
    """Повторяющиеся куски потоков -> фразы (вызов и возврат, один уровень).
    streams: [[токены-байты...]...]; возвращает (потоки с ("call", id), фразы)"""
    streams = [list(s) for s in streams]
    bodies = []
    while True:
        cand = collections.defaultdict(list)
        for si, s in enumerate(streams):
            n = len(s)
            for i in range(n):
                if s[i][0] in ("call",) or s[i] == (0xFF,):
                    continue
                key = []
                for L in range(1, max_len + 1):
                    if i + L > n or s[i + L - 1][0] == "call" or s[i + L - 1] == (0xFF,):
                        break
                    key.append(s[i + L - 1])
                    if L >= 2:
                        cand[tuple(key)].append((si, i))
        best, best_gain, best_occ = None, 0, None
        for key, occ in cand.items():
            if len(occ) < 2:
                continue
            nb = sum(len(t) for t in key)
            used, last = [], {}
            for si, i in occ:
                if i >= last.get(si, -1):
                    used.append((si, i))
                    last[si] = i + len(key)
            k = len(used)
            gain = k * nb - (nb + ret_len + k * call_len)
            if gain > best_gain:
                best, best_gain, best_occ = key, gain, used
        if not best:
            break
        pid = len(bodies)
        bodies.append(list(best))
        for si in sorted(set(si for si, _ in best_occ)):
            starts = [i for s2, i in best_occ if s2 == si]
            s = streams[si]
            new, i = [], 0
            while i < len(s):
                if i in starts:
                    new.append(("call", pid))
                    i += len(best)
                else:
                    new.append(s[i])
                    i += 1
            streams[si] = new
    return streams, bodies


def compile_D(yzs, refs, tail=True, calls=True):
    g = Game("D", [y.name for y in yzs])
    common_equ(g, tail)
    evs = [Events(y, r) for y, r in zip(yzs, refs)]
    dic = Dicts(evs, reserve31=True)
    nch = len(dic.chans)
    toks = [d_tokens(ev, dic, k) for k, ev in enumerate(evs)]
    # длительности: 7 самых частых у нот и пауз (5-битный индекс ноты)
    dc = collections.Counter(t[-1] for tt in toks for ch in tt for t in ch
                             if t[0] in ("note", "rest"))
    durs = [d for d, _ in sorted(dc.items(), key=lambda x: (-x[1], x[0]))][:7]
    # D1 - расчет: словарь длительностей до 31
    durs1 = [d for d, _ in sorted(dc.items(), key=lambda x: (-x[1], x[0]))][:31]
    flat = []           # (мелодия, канал) -> байты-токены
    flat1 = []
    for k, tt in enumerate(toks):
        for ch in tt:
            flat.append([d2_bytes(t, durs) for t in ch])
            st = {}
            flat1.append([d1_bytes(t, st, durs1) for t in ch])
    if calls:
        streams, bodies = phrases(flat, ret_len=1)
        s1, b1 = phrases(flat1)
    else:
        streams, bodies, s1, b1 = flat, [], flat1, []
    g.calc["D1"] = sum(len(t) if t[0] != "call" else 3 for s in s1 for t in s) + \
        sum(sum(len(t) for t in b) + 1 for b in b1)
    need_long = any(t[0] == 0xF0 for s in streams + bodies for t in s)
    need_call = bool(bodies)
    tone_vars(g, nch, [("ended", 1), ("tail", 1)] + ([("c_ret", 2 * nch)] if need_call else []),
              [])
    hdr_n = game_consts(g, yzs)
    g.equ += [("D_LONG", "1" if need_long else "0"), ("D_CALL", "1" if need_call else "0")]
    g.includes = ["common.a65", "note.a65", "tone.a65"]
    dic.emit(g)
    g.db("shared", durs or [0], "dur_t")
    users = collections.defaultdict(set)
    for idx, s in enumerate(streams):
        for t in s:
            if t[0] == "call":
                users[t[1]].add(idx // nch)
    for k, y in enumerate(yzs):
        t = "t%02d" % (k + 1)
        entry(g, k)
        if hdr_n:
            g.db(t, [y.n])
        g.dw(t, ["d%02d_%d" % (k + 1, c) for c in range(nch)])
        for c in range(nch):
            out = [("lab", "d%02d_%d" % (k + 1, c))]
            for tok in streams[k * nch + c]:
                out.append(tok)
            put_d(g, t, out)
    for pid, body in enumerate(bodies):
        u = users[pid]
        part = "t%02d" % (min(u) + 1) if len(u) == 1 else "shared"
        put_d(g, part, [("lab", "ph%d" % pid)] + body + [(0xF2,)])
    g.calc["zlib_data"] = deflate_parts(g, dic)
    g.durs = durs
    return g


def put_d(g, part, toks):
    buf = []

    def flush():
        if buf:
            g.db(part, buf)
            del buf[:]

    for tok in toks:
        if tok[0] == "lab":
            flush()
            if tok[1]:
                g.raw(part, tok[1])
        elif tok[0] == "call":
            flush()
            g.raw(part, "            db $F1")
            g.raw(part, "            dw ph%d" % tok[1])
        else:
            buf += list(tok)
    flush()


def deflate_parts(g, dic):
    """zlib (raw deflate) данных мелодий без адресов: только оценка"""
    total = 0
    for name, lines in g.parts.items():
        if name == "shared":
            continue
        data = []
        for ln in lines:
            m = re.match(r"\s+db (.*)", ln)
            if m and "lo(" not in ln:
                data += [int(x[1:], 16) for x in m.group(1).split(",")]
            elif re.match(r"\s+dw ", ln):
                data += [0, 0] * len(ln.split(","))
        c = zlib.compressobj(9, zlib.DEFLATED, -15)
        total += len(c.compress(bytes(data)) + c.flush())
    return total


# --- F: музыка как код (только расчет) ---

def calc_F(refs):
    total = []
    for ref in refs:
        n, a_val, empty = 0, None, 0
        for ws in ref.ticks:
            if not ws:
                empty += 1
                continue
            if empty:
                n += 3 if empty == 1 else 5           # JSR wait / LDX #n: JSR waitn
                empty = 0
            for a, v in ws:
                if v != a_val:
                    n += 2
                    a_val = v
                n += 3
            n += 3                                    # JSR wait
        total.append(n + 1)
    return total


# --- Сборка ---

def compile_game(variant, yzs, refs=None, tail=True):
    refs = refs or [run6502.Reference(y.d) for y in yzs]
    if variant == "A":
        return compile_A(yzs, tail)
    if variant == "C":
        return compile_C(yzs, refs, tail)
    if variant == "B1":
        return compile_B(yzs, refs, dense=False, tail=tail)
    if variant == "B2":
        return compile_B(yzs, refs, dense=True, tail=tail)
    if variant == "E":
        return compile_B(yzs, refs, dense=True, ref_lz=True, tail=tail)
    if variant == "D":
        return compile_D(yzs, refs, tail)
    raise ValueError(variant)


def assemble(game, outdir, name):
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    src = os.path.join(outdir, name + ".a65")
    lst = os.path.join(outdir, name + ".lst")
    binf = os.path.join(outdir, name + ".bin")
    with open(src, "w", encoding="utf-8") as f:
        f.write(game.source())
    for p in (lst, binf):
        if os.path.exists(p):
            os.remove(p)
    proc = subprocess.run([AS65, "-t", "-l", "-l" + lst, "-n", "-w", "-h0", "-o" + binf, src],
                          cwd=outdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = proc.stdout.decode("cp866", errors="replace")
    listing = open(lst, encoding="cp866", errors="replace").read() if os.path.exists(lst) else ""
    if proc.returncode != 0 or not os.path.exists(binf) or "rror" in text:
        errs = [ln for ln in listing.splitlines() if "rror" in ln][:20]
        raise CompileError("AS65 %s:\n%s\n%s" % (src, text[-2000:], "\n".join(errs)))
    sym = {}
    for m in re.finditer(r"^\s*(\w+)\s*:\s*\$([0-9A-Fa-f]+)\s+\d+", listing, re.M):
        sym[m.group(1)] = int(m.group(2), 16)
    data = open(binf, "rb").read()
    game.sym = sym
    game.binary = data
    return data, sym


def sizes(game):
    """байты: code (плеер), shared (общие данные), tables (таблицы A без выравнивания),
    tunes [по мелодиям, со входом]"""
    s = game.sym
    out = {"code": s["p_end"] - s["p_start"]}
    sh = s.get("shared_end", 0) - s.get("shared_start", 0)
    if "tab_start" in s:
        sh = s["shared_end"] - s["tab_start"]
    out["shared"] = sh
    out["tunes"] = [s["t%02d_end" % (k + 1)] - s["t%02d_start" % (k + 1)]
                    for k in range(len(game.names))]
    out["zp"] = game.zp_bytes
    out["ram"] = game.ram_bytes
    return out


def load_set(paths):
    return [YZ(open(p, "rb").read(), os.path.splitext(os.path.basename(p))[0]) for p in paths]
