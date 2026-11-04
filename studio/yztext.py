# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Текстовый вид .YZ (docs/text-format.md): сетка по кадрам, как экран трекера, и
сборка обратно в .YZ байт в байт - для небольших правок без редактора.

    python studio/yztext.py файл.yz  [-o файл.yzt]   .YZ -> текст (рядом с файлом)
    python studio/yztext.py имя      [-o файл.yzt]   партитура score/имя.py -> out/text/имя.yzt
    python studio/yztext.py файл.yzt [-o файл.yz]    текст -> .YZ (рядом с файлом)
    python studio/yztext.py --check [имена]          туда и обратно на партитурах

Собирает compose.Song.build(): одинаковые паттерны сливаются, версия (v1/v2) и
блоки - как у партитур. Номера паттернов в тексте не видны: их раздает сборка.
"""

import argparse
import glob
import os
import re
import sys

import compose
import tables

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "score"))
import instruments                                          # noqa: E402

# Разряды регистра тонового канала, как в score/instruments.py: старшие первыми
REG_BITS = [("HOLD", instruments.HOLD), ("HIT", instruments.HIT), ("LOUD", instruments.LOUD),
            ("LF", instruments.LF), ("MF", instruments.MF), ("HF", instruments.HF)]
REG_NAMES = dict(REG_BITS)
FX_NAMES = {v: k for k, v in compose.EFFECTS.items()}
FX_HEX = ("arp", "vib", "bus")          # параметр - тетрады или разряды
FX_SIGNED = ("det", "tr")
NOTE_NAMES = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]
CH_TITLES = ["1", "2", "3", "4", "5", "6", "7", "ctl"]
OFF, CUT = "===", "^^^"
CMD_OFF, CMD_CUT, CMD_INSTR, CMD_LEGATO, CMD_FX = (compose.CMD_OFF, compose.CMD_CUT, compose.CMD_INSTR,
                                                   compose.CMD_LEGATO, compose.CMD_FX)
FX_TEXT = CMD_FX + compose.EFFECTS["text"]
TEXT_DIR = os.path.join(os.path.dirname(HERE), "out", "text")

LEGEND = """\
; ЯЗС-Студия: текстовый вид .YZ, описание - docs/text-format.md
; собрать: python studio/yztext.py этот_файл.yzt
; ячейка: C-4 нота, _C-4 лига, === отпустить, ^^^ заглушить, @N инструмент,
;         {vib 0x53} эффект; в ударных 6, 7 - пресет hex (08); ctl - только эффекты"""


class TextError(ValueError):
    pass


def s8(v):
    return v - 256 if v & 0x80 else v


def w16(d, o):
    return d[o] | (d[o + 1] << 8)


# --- строки в кавычках: коды экрана Агата ---

def quote(data):
    out = []
    for b, ch in zip(data, tables.from_agat(data)):
        if ch is None:
            out.append("\\x%02X" % b)
        elif ch in "\"\\":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "\"" + "".join(out) + "\""


def unquote(s):
    """Содержимое кавычек -> коды экрана; \\xNN - код как есть"""
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            nxt = s[i + 1:i + 2]
            if nxt == "x":
                hx = s[i + 2:i + 4]
                if not re.match(r"[0-9A-Fa-f]{2}$", hx):
                    raise TextError("после \\x нужны две hex-цифры")
                out.append(int(hx, 16))
                i += 4
                continue
            if nxt not in ("\"", "\\"):
                raise TextError("неизвестное \\%s (есть \\\", \\\\, \\xNN)" % nxt)
            c = nxt
            i += 1
        if c not in tables.AGAT:
            raise TextError("нет знака %r в наборе Агата (код можно задать как \\xNN)" % c)
        out.append(tables.AGAT[c])
        i += 1
    return bytes(out)


STRING = r"\"((?:[^\"\\]|\\.)*)\""


def strip_comment(line):
    """Комментарий - от ; вне кавычек до конца строки"""
    q = False
    i = 0
    while i < len(line):
        c = line[i]
        if q and c == "\\":
            i += 2
            continue
        if c == "\"":
            q = not q
        elif c == ";" and not q:
            return line[:i]
        i += 1
    return line


# --- чтение .YZ ---

def decode_pattern(d, pos, rows):
    """Поток паттерна -> ({строка: [команды]}, длина в байтах)"""
    start = pos
    cells = {}
    r = 0
    cur = []
    while r < rows:
        if pos >= len(d):
            raise ValueError("паттерн с $%04X выходит за конец файла" % start)
        b = d[pos]
        pos += 1
        if b >= 0x80:
            if cur:
                cells[r] = cur
                cur = []
            r += 1 + b - 0x80
        elif b <= CMD_CUT:
            cur.append((b,))
        elif b <= CMD_FX + max(FX_NAMES):
            cur.append((b, d[pos]))
            pos += 1
        else:
            raise ValueError("байт $%02X в паттерне с $%04X" % (b, start))
    return cells, pos - start


class YZFile(object):
    """Разбор .YZ (docs/FORMAT.md). Чисел инструментов и подписей в заголовке нет:
    они берутся из расположения таблиц, как их кладет compose.py (таблица
    инструментов - сразу перед таблицей подписей, та - перед первым объектом)"""

    def __init__(self, data):
        d = self.d = bytes(data)
        if len(d) < compose.HDR_V1 or d[:2] != b"YZ" or d[2] not in (1, 2):
            raise ValueError("не файл .YZ версии 1 или 2")
        self.ver = d[2]
        self.title = d[4:34].rstrip(b"\xA0")
        self.subtitle = d[34:64].rstrip(b"\xA0")
        self.seconds = w16(d, 64)
        self.n, self.speed = d[66], d[67]
        o_ord, self.o_pat, o_ins, o_txt = (w16(d, 70 + 2 * i) for i in range(4))
        if self.ver == 1:
            nfr, loop, entry, self.main = d[68], d[69], 9, len(d)
        else:
            nfr, loop, entry, self.main = w16(d, 80), w16(d, 82), 17, w16(d, 84)
        self.loop = loop if d[3] & 1 else None
        self.frames = []                    # (строк, [паттерн канала 0-7])
        for f in range(nfr):
            o = o_ord + entry * f
            if self.ver == 1:
                pats = list(d[o + 1:o + 9])
            else:
                pats = [w16(d, o + 1 + 2 * c) for c in range(8)]
            self.frames.append((d[o], pats))
        self.cells = []                     # по кадрам: [канал] -> {строка: [команды]}
        self.patterns = {}                  # номер -> (блок, место, длина)
        for rows, pats in self.frames:
            fr = []
            for p in pats:
                blk, pos = self.pattern_pos(p)
                cells, ln = decode_pattern(d, pos, rows)
                self.patterns[p] = (blk, pos, ln)
                fr.append(cells)
            self.cells.append(fr)
        if o_txt < o_ins:
            raise ValueError("таблица подписей раньше таблицы инструментов")
        ins_at = [w16(d, o_ins + 2 * i) for i in range((o_txt - o_ins) // 2)]
        limit = min([self.main] + ins_at + [pos for blk, pos, ln in self.patterns.values() if blk == 0])
        offs = []
        while o_txt + 2 * len(offs) + 1 < limit:
            off = w16(d, o_txt + 2 * len(offs))
            offs.append(off)
            if off:
                limit = min(limit, off)
        if offs == [0]:
            offs = []                       # подписей нет: одна пустая запись
        self.texts = []
        for off in offs:
            end = d.index(0, off)
            self.texts.append(d[off:end])
        self.instruments = [self.instrument(i, o) for i, o in enumerate(ins_at)]

    def pattern_pos(self, p):
        """(блок, место в файле)"""
        if self.ver == 1:
            return 0, w16(self.d, self.o_pat + 2 * p)
        a = self.o_pat + 3 * p
        off, blk = w16(self.d, a), self.d[a + 2]
        return blk, (off if blk == 0 else self.main + (blk - 1) * compose.BLOCK + off)

    def instrument(self, i, o):
        d = self.d

        def macro(k, signed):
            off = d[o + 13 + k]
            if off == 0 and k >= 2:
                return None, 0xFF
            ln, loop = d[o + off], d[o + off + 1]
            vals = list(d[o + off + 2:o + off + 2 + ln])
            return ([s8(v) for v in vals] if signed else vals), loop
        reg, reg_loop = macro(0, False)
        rel, rel_loop = macro(1, False)
        arp, arp_loop = macro(2, True)
        pitch, pitch_loop = macro(3, True)
        return compose.Instrument(
            "i%d" % i, d[o:o + 8].rstrip(b"\xA0"), reg, reg_loop=reg_loop, rel=rel, rel_loop=rel_loop,
            arp=arp, arp_loop=arp_loop, pitch=pitch, pitch_loop=pitch_loop,
            vib=(d[o + 9], d[o + 10], d[o + 11]), detune=s8(d[o + 12]),
            meter=(d[o + 17] >> 4, d[o + 17] & 15, d[o + 18]), flags=d[o + 8])

    def main_pattern_bytes(self):
        return sum(ln for blk, pos, ln in self.patterns.values() if blk == 0)


# --- .YZ -> текст ---

def fmt_note(ch, n):
    if ch < 5:
        return NOTE_NAMES[n % 12] + str(n // 12)
    return "%02X" % n


def fmt_fx(e, p):
    name = FX_NAMES[e]
    if name in FX_HEX:
        return "{%s 0x%02X}" % (name, p)
    return "{%s %d}" % (name, s8(p) if name in FX_SIGNED else p)


def fmt_cell(ch, cmds):
    """Нота, лига или === первыми; остальное - в порядке байтов (Song.ordered
    при сборке поставит ноту обратно в конец строки)"""
    main, rest = [], []
    for c in cmds:
        b = c[0]
        if b < CMD_OFF:
            main.append(fmt_note(ch, b))
        elif b == CMD_LEGATO:
            main.append("_" + fmt_note(ch, c[1]))
        elif b == CMD_OFF:
            main.append(OFF)
        elif b == CMD_CUT:
            rest.append(CUT)
        elif b == CMD_INSTR:
            rest.append("@%d" % c[1])
        else:
            rest.append(fmt_fx(b - CMD_FX, c[1]))
    return " ".join(main + rest)


def fmt_reg(v):
    if v == 0:
        return "0"
    if v & 0xC0:
        return "0x%02X" % v
    return "+".join(name for name, bit in REG_BITS if v & bit)


def fmt_macro(vals, loop, fmt):
    s = " ".join(fmt(v) for v in vals)
    return s + (" loop %d" % loop if loop != 0xFF else "")


def render(yz, extra=()):
    L = []
    L.append(LEGEND)
    L.append("")
    L.append("title    " + quote(yz.title))
    L.append("subtitle " + quote(yz.subtitle))
    tick = tables.TIMER_CLOCK / float(yz.n or 1)
    L.append("tempo    %-5d; N таймера ЯЗС: тик %.1f Гц" % (yz.n, tick))
    L.append("speed    %-5d; тиков на строку: %.1f строки в секунду" % (yz.speed, tick / max(yz.speed, 1)))
    if yz.loop is not None:
        L.append("loop     %-5d; кадр повтора" % yz.loop)
    L.extend(extra)
    L.append("; в файле: v%d, %d байт, %d кадров, %d:%02d" % (
        yz.ver, len(yz.d), len(yz.frames), yz.seconds // 60, yz.seconds % 60))
    for i, ins in enumerate(yz.instruments):
        L.append("")
        L.append("instrument %d %s" % (i, quote(ins.label)))
        L.append("  reg    " + fmt_macro(ins.reg, ins.reg_loop, fmt_reg))
        L.append("  rel    " + fmt_macro(ins.rel, ins.rel_loop, fmt_reg))
        if ins.arp:
            L.append("  arp    " + fmt_macro(ins.arp, ins.arp_loop, str))
        if ins.pitch:
            L.append("  pitch  " + fmt_macro(ins.pitch, ins.pitch_loop, str))
        L.append("  vib    %d %d %d" % ins.vib)
        L.append("  detune %d" % ins.detune)
        L.append("  meter  %d %d %d" % ins.meter)
        if ins.flags:
            L.append("  flags  0x%02X" % ins.flags)
    if yz.texts:
        L.append("")
    for i, t in enumerate(yz.texts):
        L.append("text %d %s" % (i, quote(t)))
    seen = {}
    for f, (rows, pats) in enumerate(yz.frames):
        key = (rows, tuple(pats))
        same = seen.setdefault(key, f)
        L.append("")
        L.append("frame %d rows %d%s" % (f, rows, "   ; как кадр %d" % same if same != f else ""))
        rw = max(2, len(str(rows - 1)))
        grid = [[fmt_cell(ch, yz.cells[f][ch].get(r, [])) for ch in range(8)] for r in range(rows)]
        widths = [max([3, len(CH_TITLES[ch])] + [len(g[ch]) for g in grid]) for ch in range(8)]
        L.append((";" + " " * rw + "| " + " | ".join(
            t.ljust(wd) for t, wd in zip(CH_TITLES, widths))).rstrip())
        for r, g in enumerate(grid):
            line = "%0*d | " % (rw, r) + " | ".join(c.ljust(wd) for c, wd in zip(g, widths))
            caps = [quote(yz.texts[c[1]]) for ch in range(8) for c in yz.cells[f][ch].get(r, [])
                    if c[0] == FX_TEXT and c[1] < len(yz.texts)]
            L.append(line + "  ; " + ", ".join(caps) if caps else line.rstrip())
    return "\n".join(L) + "\n"


def decompile(data):
    """.YZ -> (текст, собирается ли он обратно в те же байты)"""
    yz = YZFile(data)
    tries = [[]]
    if yz.ver == 2:
        # v2, хотя влезает в v1; v2 с искусственно малой основной частью (проверки)
        tries += [["version  2"], ["version  2", "main_limit %d" % yz.main_pattern_bytes()]]
    for extra in tries:
        text = render(yz, extra)
        try:
            if compile_text(text)[0] == data:
                return text, True
        except TextError:
            pass
    return render(yz), False


# --- текст -> .YZ ---

LINE_ROW = re.compile(r"\s*(\d+)\s*\|(.*)$")
CELL_TOKEN = re.compile(r"\{\s*([A-Za-z_]+)(?:\s+([-+]?\w+))?\s*\}|\S+")
NOTE = re.compile(r"(_?)([A-Ga-g])([-#])(\d)$")
HEX_NOTE = re.compile(r"(_?)([0-9A-Fa-f]{2})$")
INSTR_KEYS = ("reg", "rel", "arp", "pitch", "vib", "detune", "meter", "flags")


def num(s, what, lo=None, hi=None):
    try:
        v = int(s, 16) if re.match(r"[-+]?0[xX]", s) else int(s, 10)
    except ValueError:
        raise TextError("%s: не число %r" % (what, s))
    if lo is not None and not lo <= v <= hi:
        raise TextError("%s: %d вне %d..%d" % (what, v, lo, hi))
    return v


class Frame(object):
    def __init__(self, number, rows, line):
        self.number, self.rows, self.line = number, rows, line
        self.last = -1
        self.cells = [dict() for _ in range(8)]     # канал -> {строка: (команды, строка текста)}


class Parser(object):
    def __init__(self):
        self.head = {}
        self.ins = {}                   # номер -> {поле: (значение, строка текста)}
        self.texts = {}
        self.frames = []
        self.cur_ins = None
        self.no = 0
        self.warnings = []

    def parse(self, text):
        for self.no, raw in enumerate(text.splitlines(), 1):
            line = strip_comment(raw).rstrip()
            if not line.strip():
                continue
            try:
                self.line(line)
            except TextError as e:
                raise TextError("строка %d: %s" % (self.no, e))
        return self

    def line(self, s):
        m = LINE_ROW.match(s)
        if m:
            return self.row(int(m.group(1)), m.group(2))
        parts = s.split(None, 1)
        word, rest = parts[0].lower(), (parts[1] if len(parts) > 1 else "").strip()
        if word in INSTR_KEYS:
            if self.cur_ins is None:
                raise TextError("%s - вне инструмента" % word)
            return self.instr_field(word, rest)
        self.cur_ins = None
        if word in ("title", "subtitle"):
            m = re.match(STRING + r"$", rest)
            if not m:
                raise TextError("%s: нужна строка в кавычках" % word)
            v = unquote(m.group(1))
            if len(v) > 30:
                raise TextError("%s длиннее 30 знаков" % word)
            self.set_head(word, v)
        elif word in ("tempo", "speed", "loop", "version", "main_limit"):
            lim = {"tempo": (1, 255), "speed": (2, 255), "loop": (0, 0xFFFE), "version": (1, 2),
                   "main_limit": (0, compose.MAIN_WITH_BLOCKS)}[word]
            self.set_head(word, num(rest, word, *lim))
        elif word == "instrument":
            m = re.match(r"(\d+)\s+" + STRING + r"$", rest)
            if not m:
                raise TextError("нужно: instrument N \"ИМЯ\"")
            i = num(m.group(1), "номер инструмента", 0, 255)
            if i in self.ins:
                raise TextError("инструмент %d уже был" % i)
            label = unquote(m.group(2))
            if len(label) > 8:
                raise TextError("имя инструмента длиннее 8 знаков")
            self.ins[i] = {"label": (label, self.no)}
            self.cur_ins = i
        elif word == "text":
            m = re.match(r"(\d+)\s+" + STRING + r"$", rest)
            if not m:
                raise TextError("нужно: text N \"ПОДПИСЬ\"")
            i = num(m.group(1), "номер подписи", 0, 254)
            if i in self.texts:
                raise TextError("подпись %d уже была" % i)
            t = unquote(m.group(2))
            if 0 in t:
                raise TextError("код 0 в подписи - ее конец")
            self.texts[i] = t
        elif word == "frame":
            m = re.match(r"(\d+)\s+rows\s+(\d+)$", rest)
            if not m:
                raise TextError("нужно: frame N rows СТРОК")
            self.frames.append(Frame(int(m.group(1)), num(m.group(2), "строк в кадре", 1, 255), self.no))
        else:
            raise TextError("не понять %r" % s.strip()[:40])

    def set_head(self, key, v):
        if key in self.head:
            raise TextError("%s уже задан" % key)
        self.head[key] = v

    def instr_field(self, key, rest):
        ins = self.ins[self.cur_ins]
        if key in ins:
            raise TextError("%s уже задан у инструмента %d" % (key, self.cur_ins))
        toks = rest.split()
        if key in ("reg", "rel", "arp", "pitch"):
            loop = 0xFF
            if len(toks) >= 2 and toks[-2].lower() == "loop":
                loop = num(toks[-1], "loop", 0, 255)
                toks = toks[:-2]
            if not toks:
                raise TextError("%s без значений" % key)
            if len(toks) > 255:
                raise TextError("%s: больше 255 значений" % key)
            if loop != 0xFF and loop >= len(toks):
                raise TextError("%s: loop %d за концом макроса" % (key, loop))
            if key in ("reg", "rel"):
                vals = [self.reg_value(t) for t in toks]
            else:
                vals = [num(t, key, -128, 127) for t in toks]
            ins[key] = ((vals, loop), self.no)
        elif key == "vib":
            if len(toks) != 3:
                raise TextError("vib: задержка, скорость, глубина")
            ins[key] = ((num(toks[0], "задержка вибрато", 0, 255), num(toks[1], "скорость вибрато", 0, 255),
                         num(toks[2], "глубина вибрато", 0, 15)), self.no)
        elif key == "meter":
            if len(toks) != 3:
                raise TextError("meter: пик, удержание, спад")
            ins[key] = ((num(toks[0], "пик", 0, 15), num(toks[1], "удержание", 0, 15),
                         num(toks[2], "спад", 0, 255)), self.no)
        else:
            if len(toks) != 1:
                raise TextError("%s: одно число" % key)
            lim = (-128, 127) if key == "detune" else (0, 255)
            ins[key] = (num(toks[0], key, *lim), self.no)

    @staticmethod
    def reg_value(tok):
        v = 0
        for part in tok.split("+"):
            name = part.upper()
            if name in REG_NAMES:
                v |= REG_NAMES[name]
            else:
                try:
                    v |= num(part, "регистр", 0, 255)
                except TextError:
                    raise TextError("регистр: %r - не число и не %s" % (
                        part, "/".join(n for n, _ in REG_BITS)))
        return v

    def row(self, r, rest):
        if not self.frames:
            raise TextError("строка сетки до первого frame")
        fr = self.frames[-1]
        if r >= fr.rows:
            raise TextError("строка %d вне кадра (строк %d)" % (r, fr.rows))
        if r <= fr.last:
            raise TextError("строки кадра - по возрастанию (была %d)" % fr.last)
        fr.last = r
        cells = rest.split("|")
        if any(c.strip() for c in cells[8:]):
            raise TextError("больше 8 ячеек (1-7 и ctl)")
        for ch, cell in enumerate(cells[:8]):
            cmds = self.cell(ch, cell)
            if cmds:
                fr.cells[ch][r] = (cmds, self.no)

    def cell(self, ch, text):
        cmds = []
        mains = 0
        where = "канал %s" % CH_TITLES[ch]
        for m in CELL_TOKEN.finditer(text):
            tok = m.group(0)
            if m.group(1):
                name = m.group(1).lower()
                if name not in compose.EFFECTS:
                    raise TextError("%s: эффект %r (есть: %s)" % (where, name, ", ".join(compose.EFFECTS)))
                p = num(m.group(2), name, -128, 255) if m.group(2) else 0
                cmds.append((CMD_FX + compose.EFFECTS[name], p & 0xFF))
            elif tok == OFF:
                cmds.append((CMD_OFF,))
                mains += 1
            elif tok == CUT:
                cmds.append((CMD_CUT,))
            elif tok.startswith("@"):
                cmds.append((CMD_INSTR, num(tok[1:], "%s: инструмент" % where, 0, 255)))
            elif ch >= 7:
                raise TextError("ctl: %r - здесь только эффекты {имя число}" % tok)
            else:
                cmds.append(self.note(ch, tok, where))
                mains += 1
        if mains > 1:
            raise TextError("%s: в ячейке больше одной ноты или ===" % where)
        return cmds

    @staticmethod
    def note(ch, tok, where):
        if ch < 5:
            m = NOTE.match(tok)
            if not m:
                raise TextError("%s: %r - не понять (нота вида C-4, C#4, _C-4)" % (where, tok))
            n = int(m.group(4)) * 12 + compose.NOTE_BASE[m.group(2).lower()] + (m.group(3) == "#")
            if not 0 <= n < 96:
                raise TextError("%s: нота %s вне C-0..B-7" % (where, tok))
        else:
            m = HEX_NOTE.match(tok)
            if not m:
                raise TextError("%s: %r - не понять (пресет двумя hex-цифрами: 08, _08)" % (where, tok))
            n = int(m.group(2), 16)
            if n >= 0x60:
                raise TextError("%s: пресет %s больше 5F" % (where, tok))
        return (CMD_LEGATO, n) if m.group(1) else (n,)

    # --- после разбора ---

    def song(self):
        for key in ("tempo", "speed"):
            if key not in self.head:
                raise TextError("нет строки %s" % key)
        if not self.frames:
            raise TextError("нет ни одного кадра (frame)")
        for f, fr in enumerate(self.frames):
            if fr.number != f:
                self.warnings.append("строка %d: frame %d стоит на месте %d: кадры нумеруются по "
                                     "порядку с 0, по нему же считают jump и loop" % (fr.line, fr.number, f))
        for what, d in (("инструмента", self.ins), ("подписи", self.texts)):
            for i in range(len(d)):
                if i not in d:
                    raise TextError("нет %s %d: номера - подряд с 0" % (what, i))
        loop = self.head.get("loop")
        if loop is not None and loop >= len(self.frames):
            raise TextError("loop %d: кадров всего %d" % (loop, len(self.frames)))
        s = compose.Song(self.head.get("title", b""), self.head.get("subtitle", b""))
        s.speed, s.n = self.head["speed"], self.head["tempo"]
        s.loop = loop
        s.version = self.head.get("version")
        s.main_limit = self.head.get("main_limit")
        for i in range(len(self.ins)):
            s.instruments.append(self.instrument(i, self.ins[i]))
        s.texts = [self.texts[i] for i in range(len(self.texts))]
        bounds = [0]
        for fr in self.frames:
            for ch in range(8):
                for r, (cmds, no) in sorted(fr.cells[ch].items()):
                    for c in cmds:
                        self.check_ref(c, no, len(s.instruments), len(s.texts))
                        s.put(ch, bounds[-1] + r, c)
            bounds.append(bounds[-1] + fr.rows)
        return s, bounds

    def instrument(self, i, f):
        label, no = f["label"]
        if "reg" not in f:
            raise TextError("строка %d: у инструмента %d нет reg" % (no, i))
        (reg, reg_loop), _ = f["reg"]
        kw = {"reg_loop": reg_loop}
        if "rel" in f:
            kw["rel"], kw["rel_loop"] = f["rel"][0]
        if "arp" in f:
            kw["arp"], kw["arp_loop"] = f["arp"][0]
        if "pitch" in f:
            kw["pitch"], kw["pitch_loop"] = f["pitch"][0]
        for key in ("vib", "detune", "meter", "flags"):
            if key in f:
                kw[key] = f[key][0]
        ins = compose.Instrument("i%d" % i, label, reg, **kw)
        try:
            ins.encode()
        except AssertionError:
            raise TextError("строка %d: инструмент %d со всеми макросами длиннее 255 байт" % (no, i))
        return ins

    def check_ref(self, c, no, n_ins, n_txt):
        b, p = c[0], (c[1] if len(c) > 1 else None)
        err = None
        if b == CMD_INSTR and p >= n_ins:
            err = "инструмента %d нет (всего %d)" % (p, n_ins)
        elif b == FX_TEXT and p != 0xFF and p >= n_txt:
            err = "подписи %d нет (всего %d; 255 - убрать)" % (p, n_txt)
        elif b == CMD_FX + compose.EFFECTS["jump"] and p >= len(self.frames):
            err = "jump %d: кадров всего %d" % (p, len(self.frames))
        elif b == CMD_FX + compose.EFFECTS["speed"] and p < 2:
            err = "speed %d: нужно 2-255" % p
        elif b == CMD_FX + compose.EFFECTS["tempo"] and p < 1:
            err = "tempo 0"
        if err:
            raise TextError("строка %d: %s" % (no, err))


def compile_text(text):
    """Текст -> (байты .YZ, compose.Song после сборки, предупреждения)"""
    p = Parser().parse(text)
    s, bounds = p.song()
    try:
        data = s.build(bounds)
    except ValueError as e:
        raise TextError("сборка: %s" % e)
    return data, s, p.warnings


def read_text(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def load(path):
    """Мелодия из файла: .yz как есть, .yzt - собранный; ошибка текста - выход с сообщением"""
    if path.lower().endswith(".yzt"):
        try:
            data, s, warnings = compile_text(read_text(path))
        except TextError as e:
            raise SystemExit("%s: %s" % (path, e))
        for w in warnings:
            print("%s: внимание: %s" % (path, w), file=sys.stderr)
        return data
    with open(path, "rb") as f:
        return f.read()


def roundtrip(data):
    """None, если .YZ -> текст -> .YZ дает те же байты, иначе - что не так"""
    try:
        text, exact = decompile(data)
    except ValueError as e:
        return "не разобрать: %s" % e
    return None if exact else "текст собирается в другие байты"


def score_modules():
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, "score", "*.py"))):
        m = os.path.splitext(os.path.basename(p))[0]
        if m not in ("common", "instruments") and not m.startswith("data_"):
            out.append(m)
    return out


def summary(data):
    ver, main, blocks = compose.yz_info(data)
    secs = w16(data, 64)
    return "%d байт, v%d%s, %d:%02d" % (len(data), ver, ", блоков %d" % blocks if blocks else "",
                                       secs // 60, secs % 60)


def main():
    ap = argparse.ArgumentParser(description="Текстовый вид .YZ: разобрать и собрать (docs/text-format.md)")
    ap.add_argument("src", nargs="*", help="файл.yz, файл.yzt или имя партитуры score/")
    ap.add_argument("-o", "--out", help="куда писать (по умолчанию - рядом, для партитуры - out/text/)")
    ap.add_argument("--check", action="store_true", help="туда и обратно на партитурах (все или названные)")
    a = ap.parse_args()
    if a.check:
        import build
        bad = 0
        names = a.src or score_modules()
        for m in names:
            err = roundtrip(build.load_score(m).build())
            if err:
                bad += 1
                print("  %s: %s" % (m, err))
        print("текстовый вид: %d партитур туда и обратно, расхождений %d" % (len(names), bad))
        sys.exit(1 if bad else 0)
    if len(a.src) != 1:
        ap.error("нужен один файл или имя партитуры")
    src = a.src[0]
    low = src.lower()
    if low.endswith(".yzt"):
        try:
            data, s, warnings = compile_text(read_text(src))
        except TextError as e:
            sys.exit("%s: %s" % (src, e))
        for w in warnings:
            print("внимание:", w, file=sys.stderr)
        out = a.out or os.path.splitext(src)[0] + ".yz"
        with open(out, "wb") as f:
            f.write(data)
        st = s.stats
        print("%s: %s, %d кадров, %d паттернов, speed %d, N %d" % (
            out, summary(data), st["frames"], st["patterns"], st["speed"], st["n"]))
        return
    if os.path.isfile(src):
        with open(src, "rb") as f:
            data = f.read()
        out = a.out or os.path.splitext(src)[0] + ".yzt"
    elif os.path.isfile(os.path.join(HERE, "score", src + ".py")):
        import build
        data = build.load_score(src).build()
        out = a.out or os.path.join(TEXT_DIR, src + ".yzt")
    else:
        sys.exit("нет файла %s и партитуры score/%s.py" % (src, src))
    try:
        text, exact = decompile(data)
    except ValueError as e:
        sys.exit("%s: не разобрать .YZ: %s" % (src, e))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print("%s: %s, %d строк текста" % (out, summary(data), text.count("\n")))
    if not exact:
        print("внимание: текст собирается в другие байты, чем у исходного файла (смысл должен быть тот же:"
              " compose.py по-своему расставляет команды и нумерует паттерны)", file=sys.stderr)


if __name__ == "__main__":
    main()
