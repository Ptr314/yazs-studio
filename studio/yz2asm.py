# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Мелодии .YZ -> текст для ассемблера игры: встраиваемый плеер и данные
(docs/yz2asm.md). У каждой мелодии свой вход: jsr <вход> играет ее до конца и
возвращается. Плеер - player/yzplay.a65 (вариант D опыта experiments/embed):
поток нот каждого занятого канала, огибающие инструментов, словарь периодов и
повторы фраз - общие на всю игру. Звук - как у плеера Студии, тик в тик:
компилятор сверяет свою модель плеера с моделью движка (pyplay.py), а готовый
текст собирается AS65 и проигрывается на эмуляторе 6502 против той же модели.

    python studio/yz2asm.py [имя=]мелодия ... [-o music.a65] [ключи]

Мелодия - файл .yz, текстовый вид .yzt или партитура score/<имя>.py. Имя
входа - <префикс><имя>, по умолчанию имя файла. Ключи - в --help.
"""

import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile

import pyplay
import tables
from sid import cpu6502

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(ROOT, "player", "yzplay.a65")
AS65 = os.path.join(ROOT, "third_party", "as65", "as65.exe")
CNT = (0, 1, 2, 4, 5)           # регистры счетчиков тоновых каналов 1-5
TAIL = 100                      # тиков отпускания после конца (ui.a65)
CHECKED = set(range(0, 15)) - {3, 7}
FX = ("ARP", "SLIDE_UP", "SLIDE_DN", "PORTA", "VIB", "DETUNE", "BUS", "TREMOLO", "DELAY", "CUT",
      "SPEED", "TEMPO", "JUMP", "TEXT", "TRANSPOSE", "RETRIG", "BREAK")
LIMIT_TICKS = 100 * 60 * 60     # час при тике 100 Гц: дольше - мелодия не кончается
TOP = 0xC000                    # с $C000 - ввод-вывод, ПЗУ слотов и банки: образ - ниже


class Rejected(Exception):
    """Мелодия не укладывается в нотный поток (или набор - в ограничения плеера)"""


def num(s):
    s = s.strip()
    if s.startswith("$"):
        return int(s[1:], 16)
    return int(s, 0)


# --- Мелодии ---

def load_input(arg):
    """(имя входа, байты .YZ, источник)"""
    if "=" in arg and not os.path.exists(arg):
        name, path = arg.split("=", 1)
    else:
        name, path = "", arg
    if os.path.isfile(path):
        import yztext
        data = yztext.load(path)
        stem = os.path.basename(path).split(".")[0] if path.lower().endswith(".yzt") else \
            os.path.splitext(os.path.basename(path))[0]
    elif os.path.isfile(os.path.join(HERE, "score", path + ".py")):
        import build
        data = build.load_score(path).build()
        stem = path
    else:
        raise SystemExit("нет такой мелодии: %s (файл .yz/.yzt или партитура score/)" % path)
    name = name or stem
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not name or name[0].isdigit():
        name = "m" + name
    return name, data, path


def no_loop(data):
    """Повтор с кадра loop - только по R в плеере Студии; встроенный играет раз"""
    d = bytearray(data)
    d[3] &= 0xFE
    return bytes(d)


class Trace(pyplay.Player):
    """Модель движка с журналом событий для нотного потока"""

    def __init__(self, data):
        self.parsed = []        # (тик, канал, вид, нота)
        self.ons = {}           # (тик удара, канал) -> вид разбора
        self.cut_offs = []      # (тик, канал): отпускание по CUT
        self.tempos = []        # (тик, N)
        self.snap = []
        self.where = []
        self.fx = collections.Counter()
        pyplay.Player.__init__(self, data)

    def parse(self, ch):
        if self.wait[ch]:
            return pyplay.Player.parse(self, ch)
        if ch < 5:
            t = self.tone[ch]
            st0 = t.state
            pyplay.Player.parse(self, ch)
            if st0 == 1 and t.state == 2:
                self.parsed.append((self.ticks, ch, "off", None))
            if st0 != 0 and t.state == 0:
                self.parsed.append((self.ticks, ch, "cut", None))
            if t.pend in ("note", "legato"):
                self.parsed.append((self.ticks, ch, "hit" if t.pend == "note" else "leg", t.pend_note))
        elif ch < 7:
            i = ch - 5
            n0 = len(self.writes)
            pyplay.Player.parse(self, ch)
            if any(a == 13 + i for _, a, _ in self.writes[n0:]):
                self.parsed.append((self.ticks, ch, "doff", None))
            if self.drum_pend[i] is not None:
                self.parsed.append((self.ticks, ch, "dhit", self.drum_pend[i] & 0x0F))
        else:
            pyplay.Player.parse(self, ch)

    def effect(self, ch, t, e, p):
        self.fx[e] += 1
        if e == 11:
            self.tempos.append((self.ticks, p))
        pyplay.Player.effect(self, ch, t, e, p)

    def note_on(self, t):
        self.ons[(self.ticks, self.tone.index(t))] = t.pend
        pyplay.Player.note_on(self, t)

    def tone_tick(self, ch, t):
        st0 = t.state
        pyplay.Player.tone_tick(self, ch, t)
        if st0 == 1 and t.state == 2:
            self.cut_offs.append((self.ticks, ch))

    def step(self):
        self.where.append((self.frame, self.row))
        r = pyplay.Player.step(self)
        self.snap.append([(t.state, t.last_per, t.ins) for t in self.tone])
        if self.ticks > LIMIT_TICKS:
            raise Rejected("мелодия не кончается (переход JUMP назад?)")
        return r


class Tune(object):
    """Мелодия: события по каналам в тиках разбора, эталон записей модели"""

    def __init__(self, name, data, src):
        self.name, self.src = name, src
        self.data = no_loop(data)
        tr = Trace(self.data)
        n0 = len(tr.writes)
        self.init = [(a, v) for _, a, v in tr.writes]
        while tr.step():
            pass
        self.end = tr.ticks
        self.n = self.data[66]
        self.trace = tr
        # эталон: тики мелодии и хвост (как плеер Студии)
        for _ in range(TAIL):
            for ch in range(5):
                t = tr.tone[ch]
                if t.state == 1:
                    t.state, t.regpos = 2, 0
                pyplay.Player.tone_tick(tr, ch, t)
            tr.ticks += 1
        self.ref = [[] for _ in range(tr.ticks)]
        for t, a, v in tr.writes[n0:]:
            self.ref[t].append((a, v))
        # события
        self.ev = collections.defaultdict(list)     # канал -> [(тик, порядок, вид, арг...)]
        for tick, ch, kind, note in tr.parsed:
            if kind in ("hit", "leg"):
                on = tr.ons.get((tick + 1, ch))
                if on is None:
                    raise Rejected("%s: DELAY (удар не в следующий тик после разбора)" % name)
                st, per, ins = tr.snap[tick + 1][ch]
                self.ev[ch].append((tick, 2, kind, per, ins))
            elif kind in ("off", "cut", "doff"):
                self.ev[ch].append((tick, 0, kind))
            else:
                self.ev[ch].append((tick, 2, kind, note))
        for tick, ch in tr.cut_offs:
            self.ev[ch].append((tick, 0, "off"))
        self.tempos = tr.tempos
        for ch in self.ev:
            self.ev[ch].sort(key=lambda e: (e[0], e[1]))
        self.chans = sorted(self.ev)

    def seconds(self):
        return self.end * self.n / 7980.0

    def features(self):
        """Что в мелодии есть из того, что нотный поток не передает"""
        out = [FX[e] for e in sorted(self.trace.fx) if e not in (5, 9, 10, 11, 12, 13, 14, 16)]
        names = set()
        for ch, lst in self.ev.items():
            for e in lst:
                if e[2] in ("hit", "leg"):
                    names.add(e[4])
        for i in sorted(names):
            ins = instrument(self.trace, i)
            what = [w for w, on in (("вибрато", ins["vib"]), ("арпеджио", ins["arp"]),
                                    ("макрос высоты", ins["pit"])) if on]
            if what:
                out.append("инструмент %d «%s»: %s" % (i, ins["label"], ", ".join(what)))
        return out


def instrument(p, i):
    d = p.d
    base = p.ins_rec(i)

    def macro(off):
        a = base + off
        return d[a], d[a + 1], list(d[a + 2:a + 2 + d[a]])

    label = "".join(c or "?" for c in tables.from_agat(d[base:base + 8])).rstrip()
    return {"reg": macro(d[base + 13]), "rel": macro(d[base + 14]), "vib": d[base + 11],
            "arp": d[base + 15], "pit": d[base + 16], "label": label}


def rle(m):
    """Макрос (длина, повтор, значения) -> пары (тиков, значение), пара повтора"""
    ln, loop, vals = m
    loop = loop if loop != 0xFF else len(vals) - 1
    runs, j = [], 0
    for i, v in enumerate(vals):
        if runs and runs[-1][1] == v and i != loop and runs[-1][0] < 255:
            runs[-1][0] += 1
        else:
            if i == loop:
                j = len(runs)
            runs.append([1, v])
    return runs, j


def env_record(ins):
    """+0 смещение огибающей отпускания; пары (тиков, значение); (0, смещение повтора)"""
    out = [0]
    for k, key in enumerate(("reg", "rel")):
        if k == 1:
            out[0] = len(out)
        runs, j = rle(ins[key])
        base = len(out)
        for n, v in runs:
            out += [n, v]
        out += [0, base + 2 * j]
    if len(out) > 255:
        raise Rejected("огибающая инструмента длиннее 255 байт")
    return out


# --- Игра: словари, модель плеера, потоки ---

class Game(object):
    def __init__(self, tunes, tail=True, phrases_on=True):
        self.tunes = tunes
        self.tail = tail
        chans = set()
        for t in tunes:
            chans |= set(t.chans)
        self.tones = [c for c in sorted(chans) if c < 5]
        self.drums = [c for c in sorted(chans) if c >= 5]
        if not chans:
            self.tones = [0]
        self.chans = self.tones + self.drums
        # инструменты (по огибающим) и периоды
        self.ins_key, self.ins_rec = {}, []
        per = collections.Counter()
        for t in tunes:
            t.ins_map = {}
            for ch, lst in t.ev.items():
                for e in lst:
                    if e[2] in ("hit", "leg"):
                        per[e[3]] += 1
                        if e[4] not in t.ins_map:
                            ins = instrument(t.trace, e[4])
                            key = (tuple(ins["reg"][2]), ins["reg"][:2], tuple(ins["rel"][2]), ins["rel"][:2])
                            if key not in self.ins_key:
                                self.ins_key[key] = len(self.ins_rec)
                                self.ins_rec.append(env_record(ins))
                            t.ins_map[e[4]] = self.ins_key[key]
        if len(self.ins_rec) > 16:
            raise Rejected("инструментов (разных огибающих) в игре %d, плеер берет до 16" % len(self.ins_rec))
        # словарь: сначала периоды ударов (частые - в 5-битный индекс ноты), за ними -
        # периоды движения высоты внутри нот ($F7, их находит simulate(fix=True))
        self.per = [p for p, _ in sorted(per.items(), key=lambda x: (-x[1], x[0]))]
        if len(self.per) > 31:
            self.per.insert(31, 0)          # 31 - пауза
        self.per_i = {p: i for i, p in enumerate(self.per) if i != 31 or len(self.per) <= 31}
        for t in tunes:
            self.simulate(t, fix=True)
            for c in t.ev:
                t.ev[c].sort(key=lambda e: (e[0], e[1]))
        if len(self.per) > 256:
            raise Rejected("разных периодов в игре %d, словарь - до 256" % len(self.per))
        for t in tunes:
            self.validate(t)
        self.tokens = [self.tune_tokens(t) for t in tunes]
        dc = collections.Counter(tok[2] for tt in self.tokens for ch in tt for tok in ch
                                 if tok[0] in ("note", "rest"))
        self.durs = [d for d, _ in sorted(dc.items(), key=lambda x: (-x[1], x[0]))][:7]
        flat = [[self.encode(tok) for tok in ch] for tt in self.tokens for ch in tt]
        if phrases_on:
            self.streams, self.bodies = phrases(flat)
        else:
            self.streams, self.bodies = flat, []
        kinds = set(tok[0] for s in self.streams + self.bodies for tok in s)
        self.flags = {
            "F_HDRN": len(set(t.n for t in tunes)) > 1,
            "F_KEY": False,
            "F_TAIL": tail,
            "F_TONES": bool(self.tones),
            "F_DRUMS": bool(self.drums),
            "F_TD": bool(self.tones) and bool(self.drums),
            "F_LONG": 0xF0 in kinds,
            "F_CALL": bool(self.bodies),
            "F_OFF": 0xF3 in kinds,
            "F_CUT": 0xF4 in kinds,
            "F_LEG": 0xF5 in kinds,
            "F_TEMPO": 0xF6 in kinds,
            "F_PER": 0xF7 in kinds,
        }
        self.flags["F_DOFF"] = self.flags["F_DRUMS"] and (self.flags["F_OFF"] or self.flags["F_CUT"])

    def add_per(self, p):
        if p not in self.per_i:
            self.per_i[p] = len(self.per)
            self.per.append(p)
        return self.per_i[p]

    def ctab(self):
        out = []
        for c in self.chans:
            out += [8 + c, CNT[c] if c < 5 else 0]
        return out

    # --- модель плеера ---

    def simulate(self, t, fix=False):
        """Записи нотного потока по тикам: [[(регистр, значение)...]...]. fix - где
        модель движка пишет период, а поток нет (скольжение, вибрато, DETUNE внутри
        ноты), добавить в мелодию событие «период» ($F7) в этот тик"""
        st = {c: dict(pend=0, state=0, lreg=0, lnote=None, note=0, pins=0, ins=0, leg=0, eo=0, ec=0)
              for c in self.chans}
        at = collections.defaultdict(list)
        for c, lst in t.ev.items():
            for e in lst:
                at[(c, e[0])].append(e)
        for tick, n in t.tempos:
            at[("tempo", tick)].append(n)
        total = t.end + (TAIL if self.tail else 0)
        out = [[] for _ in range(total)]

        def env_start(s, y):
            rec = self.ins_rec[s["ins"]]
            s["ec"], s["eo"] = rec[y], y

        def env_step(s):
            rec = self.ins_rec[s["ins"]]
            y = s["eo"]
            v = rec[y + 1]
            s["ec"] -= 1
            if s["ec"] == 0:
                y += 2
                if rec[y] == 0:
                    y = rec[y + 1]
                s["ec"], s["eo"] = rec[y], y
            return v

        def rout(s, c, v, w):
            if v != s["lreg"]:
                s["lreg"] = v
                w.append((8 + c, v))

        def release(s):
            s["state"] = 2
            env_start(s, self.ins_rec[s["ins"]][0])

        def wper(s, c, idx, w):
            if idx != s["lnote"]:
                s["lnote"] = idx
                p = self.per[idx]
                w += [(CNT[c], p & 255), (CNT[c], p >> 8)]

        def tone(s, c, w):
            if s["pend"]:
                s["pend"] -= 1
                if s["pend"] == 0:
                    s["ins"] = s["pins"]
                    wper(s, c, s["note"], w)
                    restart = True
                    if s["leg"]:
                        s["leg"] = 0
                        if s["state"] == 1:
                            restart = False
                    if restart:
                        s["state"] = 1
                        env_start(s, 1)
            if s["state"] == 0:
                return
            v = env_step(s)
            if s["pend"] and not s["leg"]:
                v &= 0xEF
            rout(s, c, v, w)

        for k in range(total):
            w = out[k]
            if k < t.end:
                for n in at.get(("tempo", k), ()):
                    w += [(6, n), (6, 0)]
                for c in self.chans:
                    s = st[c]
                    for e in at.get((c, k), ()):
                        kind = e[2]
                        if kind in ("hit", "leg"):
                            s["note"] = self.per_i[e[3]]
                            s["pins"] = t.ins_map[e[4]]
                            s["pend"] = 2
                            s["leg"] = 1 if kind == "leg" else 0
                        elif kind == "off":
                            if s["state"] == 1:
                                release(s)
                        elif kind == "cut":
                            s["state"] = 0
                            rout(s, c, 0, w)
                        elif kind == "dhit":
                            s["note"] = e[3]
                            s["pend"] = 2
                        elif kind == "doff":
                            s["pend"] = 0
                            w.append((8 + c, s["lreg"]))
                        elif kind == "per":
                            wper(s, c, self.per_i[e[3]], w)
                    if c < 5:
                        if fix:
                            trial, tw = dict(s), []
                            tone(trial, c, tw)
                            want = [v for a, v in t.ref[k] if a == CNT[c]]
                            got = [v for a, v in tw if a == CNT[c]]
                            if want != got and not got and len(want) == 2:
                                p = want[0] | (want[1] << 8)
                                t.ev[c].append((k, 1, "per", p))
                                wper(s, c, self.add_per(p), w)
                        tone(s, c, w)
                    elif s["pend"]:
                        s["pend"] -= 1
                        v = s["note"]
                        if s["pend"] == 0:
                            s["lreg"] = v
                            v |= 0x10
                        w.append((8 + c, v))
            else:
                for c in self.tones:
                    s = st[c]
                    if s["state"] == 1:
                        release(s)
                    tone(s, c, w)
        return out

    def validate(self, t):
        sim = self.simulate(t)
        ref = t.ref if self.tail else t.ref[:t.end]
        for k in range(len(ref)):
            a = collections.Counter(x for x in sim[k] if x[0] in CHECKED)
            b = collections.Counter(x for x in ref[k] if x[0] in CHECKED)
            if a != b:
                if k < len(t.trace.where):
                    f, r = t.trace.where[k]
                    place = "тик %d (кадр %d, строка %d)" % (k, f, r)
                    hint = ""
                else:
                    place = "тик %d (хвост после конца)" % k
                    hint = "; после конца меняется высота (вибрато при отпускании?) - соберите с --no-tail"
                feats = t.features()
                raise Rejected("%s: не укладывается в нотный поток: %s, модель пишет %s, поток - %s%s%s" % (
                    t.name, place, sorted((b - a).elements()), sorted((a - b).elements()), hint,
                    ("; в мелодии есть: " + "; ".join(feats)) if feats else ""))

    # --- потоки ---

    def tune_tokens(self, t):
        """По каналу игры: ("ins", i) ("note", n, d) ("rest", 31, d) ("off",) ("cut",)
        ("leg",) ("tempo", N) ("end",)"""
        out = []
        for ci, c in enumerate(self.chans):
            evs = list(t.ev.get(c, []))
            if ci == 0:
                evs += [(tick, 1, "tempo", n) for tick, n in t.tempos]
                evs.sort(key=lambda e: (e[0], e[1]))
            toks = []
            cur_ins = None
            by_t = collections.OrderedDict()
            for e in evs:
                by_t.setdefault(e[0], []).append(e)
            times = list(by_t)

            def wait(kind, n, d):
                first = True
                while d > 0:
                    step = min(d, 255)
                    toks.append((kind if first else "rest", n if first else 31, step))
                    first = False
                    d -= step

            if not times or times[0] > 0:
                wait("rest", 31, (times[0] if times else t.end))
            for i, tick in enumerate(times):
                nxt = times[i + 1] if i + 1 < len(times) else t.end
                timed = None
                for e in by_t[tick]:
                    if e[2] in ("off", "cut"):
                        toks.append((e[2],))
                    elif e[2] == "doff":
                        toks.append(("off",))
                    elif e[2] == "tempo":
                        toks.append(("tempo", e[3]))
                    elif e[2] == "per":
                        toks.append(("per", self.per_i[e[3]]))
                    else:
                        timed = e
                if timed is None:
                    wait("rest", 31, nxt - tick)
                elif timed[2] == "dhit":
                    wait("note", timed[3], nxt - tick)
                else:
                    gi = t.ins_map[timed[4]]
                    if gi != cur_ins:
                        toks.append(("ins", gi))
                        cur_ins = gi
                    if timed[2] == "leg":
                        toks.append(("leg",))
                    wait("note", self.per_i[timed[3]], nxt - tick)
            if ci == 0:
                toks.append(("end",))
            out.append(toks)
        return out

    def encode(self, tok):
        k = tok[0]
        if k in ("note", "rest"):
            n, d = tok[1], tok[2]
            if n < 32 and d in self.durs:
                return ((self.durs.index(d) << 5) | n,)
            return (0xF0, n, d)
        return {"ins": lambda: (0xE0 + tok[1],), "off": lambda: (0xF3,), "cut": lambda: (0xF4,),
                "leg": lambda: (0xF5,), "tempo": lambda: (0xF6, tok[1]), "per": lambda: (0xF7, tok[1]),
                "end": lambda: (0xFF,)}[k]()


def phrases(streams, call_len=3, ret_len=1, max_len=32):
    """Повторяющиеся куски потоков -> фразы (вызов $F1 и возврат $F2, один уровень)"""
    streams = [list(s) for s in streams]
    bodies = []
    while True:
        cand = collections.defaultdict(list)
        for si, s in enumerate(streams):
            n = len(s)
            for i in range(n):
                if s[i][0] == "call" or s[i] == (0xFF,):
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
            starts = set(i for s2, i in best_occ if s2 == si)
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


# --- Текст для ассемблера ---

def preprocess(text, flags):
    """if/else/endif шаблона по флагам"""
    out, stack, active = [], [], True
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"if\s+(\w+)$", s)
        if m:
            cond = bool(flags[m.group(1)])
            stack.append((active, cond))
            active = active and cond
            continue
        if s == "else":
            parent, cond = stack[-1]
            active = parent and not cond
            continue
        if s == "endif":
            active = stack.pop()[0]
            continue
        if active:
            out.append(line)
    if stack:
        raise ValueError("шаблон: if без endif")
    return out


def strip_comments(lines):
    out = []
    for ln in lines:
        code = re.sub(r"\s*;.*$", "", ln)
        if code.strip() or not ln.strip():
            out.append(code.rstrip())
    return [ln for i, ln in enumerate(out) if ln or (i and out[i - 1])]


def db_lines(data, label=None):
    out = [label] if label else []
    for i in range(0, len(data), 16):
        out.append("            db " + ",".join("$%02X" % (b & 255) for b in data[i:i + 16]))
    return out


def stream_lines(toks, label):
    out = [label]
    buf = []
    for tok in toks:
        if tok[0] == "call":
            if buf:
                out += db_lines(buf)
                buf = []
            out.append("            db $F1")
            out.append("            dw yz_ph%d" % tok[1])
        else:
            buf += list(tok)
    if buf:
        out += db_lines(buf)
    return out


def generate(game, opts):
    """Текст .a65 (строки) и сводка"""
    g = game
    nch = len(g.chans)
    flags = dict(g.flags, F_KEY=opts.key, F_SAVEZP=opts.save_zp)
    zp = [("yz_ptr", 2), ("yz_ip", 2), ("yz_chp", 2 * nch)] + \
        ([("yz_ret", 2 * nch)] if flags["F_CALL"] else []) + [("yz_end", 1), ("yz_tail", 1)]
    zero = ["yz_wait", "yz_pend", "yz_state", "yz_lreg"] + (["yz_leg"] if flags["F_LEG"] else [])
    ram = zero + ["yz_lnote", "yz_note", "yz_pins", "yz_ins", "yz_ec", "yz_eo"]
    equ = [("yz_card", "$%04X" % opts.card)]
    if not flags["F_HDRN"]:
        equ.append(("yz_n", str(g.tunes[0].n)))
    equ += [("yz_tailn", str(TAIL)), ("yz_nch2", str(2 * nch)), ("yz_nt2", str(2 * len(g.tones))),
            ("yz_zlen", str(len(zero) * 2 * nch))]
    a = opts.zp
    for name, n in zp:
        equ.append((name, "$%02X" % a))
        a += n
    zp_bytes = a - opts.zp
    if a > 0x100:
        raise SystemExit("переменные нулевой страницы не помещаются: $%02X + %d" % (opts.zp, zp_bytes))
    a = opts.ram
    equ.append(("yz_vars", "$%04X" % a))
    for name in ram:
        equ.append((name, "$%04X" % a))
        a += 2 * nch
    if flags["F_SAVEZP"]:
        equ += [("yz_zsave", "$%04X" % a), ("yz_zpn", str(zp_bytes))]
        a += zp_bytes
    ram_bytes = a - opts.ram
    tmpl = open(TEMPLATE, encoding="utf-8").read()
    head = [ln for ln in tmpl.splitlines()[:2]]
    code = preprocess("\n".join(tmpl.splitlines()[2:]), flags)

    out = head + [
        ";",
        "; Сгенерировано studio/yz2asm.py (ЯЗС-Студия, docs/yz2asm.md) - не править: пересоберите.",
        "; Мелодии (вход: jsr <вход>, звук до конца, потом RTS; портит A, X, Y):"]
    for t in g.tunes:
        out.append(";   %-20s %5.1f с  %s" % ("yz_" + t.name, t.seconds(), t.src))
    out += [";", "; ЯЗС: $%04X (слот %d). Нулевая страница $%02X-$%02X, ОЗУ $%04X-$%04X: только на время" % (
        opts.card, (opts.card - 0xC080) // 16, opts.zp, opts.zp + zp_bytes - 1, opts.ram,
        opts.ram + ram_bytes - 1),
        "; звука, после выхода не нужны%s. Прерывания на время звука запрещены (SEI), стек - 8 байт." % (
            " (нулевая страница - восстанавливается)" if flags["F_SAVEZP"] else ""),
        "; Возможности сборки: " + ", ".join(k[2:] for k, v in sorted(flags.items()) if v), ""]
    for k, v in equ:
        out.append("%-11s equ %s" % (k, v))
    out.append("")
    out += code
    # общие данные
    out += ["", "; --- Общие данные: каналы, словари, инструменты, общие фразы ---", "yz_shared"]
    out += db_lines(g.ctab(), "yz_ctab")
    if g.tones:
        out += db_lines([p & 255 for p in g.per], "yz_pdlo")
        out += db_lines([p >> 8 for p in g.per], "yz_pdhi")
    out += db_lines(g.durs or [1], "yz_durt")
    if g.tones:
        out.append("yz_itab")
        if g.ins_rec:
            out.append("            dw " + ",".join("yz_i%d" % i for i in range(len(g.ins_rec))))
        for i, rec in enumerate(g.ins_rec):
            out += db_lines(rec, "yz_i%d" % i)
    users = collections.defaultdict(set)
    for idx, s in enumerate(g.streams):
        for tok in s:
            if tok[0] == "call":
                users[tok[1]].add(idx // nch)
    own = collections.defaultdict(list)
    for pid, body in enumerate(g.bodies):
        u = users[pid]
        if len(u) == 1:
            own[min(u)].append(pid)
        else:
            out += stream_lines(body + [(0xF2,)], "yz_ph%d" % pid)
    # мелодии
    out += ["", "; --- Мелодии ---"]
    for k, t in enumerate(g.tunes):
        out.append("")
        out.append("yz_%-8s jsr yz_play" % t.name)
        if flags["F_HDRN"]:
            out += db_lines([t.n])
        out.append("            dw " + ",".join("yz_%s_%d" % (t.name, c) for c in range(nch)))
        for c in range(nch):
            out += stream_lines(g.streams[k * nch + c], "yz_%s_%d" % (t.name, c))
        for pid in own[k]:
            out += stream_lines(g.bodies[pid] + [(0xF2,)], "yz_ph%d" % pid)
    out.append("yz_last")
    if opts.plain:
        out = strip_comments(out)
    text = "\n".join(out) + "\n"
    text = re.sub(r"\byz_", opts.prefix, text)
    return text, dict(zp=zp_bytes, ram=ram_bytes, flags=flags)


# --- Сборка и проверка на 6502 ---

def assemble(path, org, workdir):
    """AS65: (образ, символы); None - AS65 не запускается"""
    if not os.path.exists(AS65):
        return None
    wrap = os.path.join(workdir, "yz2asm_check.a65")
    lst = os.path.join(workdir, "yz2asm_check.lst")
    binf = os.path.join(workdir, "yz2asm_check.bin")
    with open(wrap, "w", encoding="utf-8") as f:
        f.write("            org $%04X\n            include \"%s\"\n" % (
            org, os.path.abspath(path).replace("\\", "/")))
    for p in (lst, binf):
        if os.path.exists(p):
            os.remove(p)
    try:
        proc = subprocess.run([AS65, "-t", "-l", "-l" + lst, "-n", "-w", "-h0", "-o" + binf, wrap],
                              cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError:
        return None
    text = proc.stdout.decode("cp866", errors="replace")
    listing = open(lst, encoding="cp866", errors="replace").read() if os.path.exists(lst) else ""
    if proc.returncode != 0 or not os.path.exists(binf) or "rror" in text:
        errs = [ln for ln in listing.splitlines() if "rror" in ln][:10]
        raise SystemExit("AS65 не собрал %s:\n%s\n%s" % (path, text[-1500:], "\n".join(errs)))
    sym = {m.group(1): int(m.group(2), 16)
           for m in re.finditer(r"^\s*(\w+)\s*:\s*\$([0-9A-Fa-f]+)\s+\d+", listing, re.M)}
    return open(binf, "rb").read(), sym


def place_error(org, size, ram, ram_bytes):
    """Образ size байт с org не ложится в ОЗУ: текст ошибки, иначе None. Данные на
    $C000-$C0FF плеер читал бы из ввода-вывода, и проверка на 6502 падала бы на
    случайном тике, а не здесь"""
    end = org + size
    if end > TOP:
        return "образ $%04X-$%04X заходит на $%04X (ввод-вывод, ПЗУ): %s" % (
            org, end - 1, TOP, "--org не выше $%04X" % (TOP - size) if size <= TOP else "не помещается")
    if org < ram + ram_bytes and ram < end:
        return "образ $%04X-$%04X перекрывает переменные плеера $%04X-$%04X (--ram)" % (
            org, end - 1, ram, ram + ram_bytes - 1)
    return None


class Card(cpu6502.CPU6502):
    """6502 с ЯЗС: чтение +0 - флаг таймера взведен (начало тика); клавиатура $C000"""

    def __init__(self, mem, card, key_at=None):
        cpu6502.CPU6502.__init__(self, mem)
        self.card = card
        self.log = []
        self.polls = 0
        self.key_at = key_at

    def rd(self, a):
        if 0xC000 <= a <= 0xC0FF:
            if a == self.card:
                self.polls += 1
                self.log.append(("poll",))
                return 0x80
            if a == 0xC000 and self.key_at is not None and self.polls >= self.key_at:
                return 0xC1
            return 0
        return self.m[a]

    def wr(self, a, v):
        if 0xC000 <= a <= 0xC0FF:
            if self.card <= a < self.card + 16:
                self.log.append(("w", a - self.card, v))
            return
        self.m[a] = v


def run_check(image, org, sym, game, opts):
    """Каждая мелодия на 6502 против модели. Список ошибок"""
    errs = []
    for k, t in enumerate(game.tunes):
        entry = sym[opts.prefix + t.name]
        # без хвоста: конец виден в начале следующего тика - он пустой, потом выход
        want = t.ref if game.tail else t.ref[:t.end] + [[]]
        for key_at in ([None] + ([min(len(want), 40)] if opts.key else [])):
            mem = bytearray(65536)
            mem[org:org + len(image)] = image
            zp_pat = [(0x5A + 3 * i) & 255 for i in range(opts.zp_bytes)]
            if opts.save_zp:
                mem[opts.zp:opts.zp + opts.zp_bytes] = bytes(zp_pat)
            cpu = Card(mem, opts.card, key_at)
            try:
                cpu.call(entry, limit=(len(want) + 10) * 20000)     # тик - до 20000 тактов
            except cpu6502.Timeout:
                errs.append("%s: плеер не вернулся" % t.name)
                continue
            init, ticks, cur, exitw, exiting = [], [], None, [], False
            for e in cpu.log:
                if e[0] == "poll":
                    cur = []
                    ticks.append(cur)
                elif ticks and e[1] == 15 and e[2] == 0xC0:
                    exiting = True
                if e[0] == "w":
                    (exitw if exiting else (init if cur is None else cur)).append((e[1], e[2]))
            exp = want if key_at is None else want[:key_at - 1] + [[]]
            what = "%s%s" % (t.name, "" if key_at is None else " (клавиша на тике %d)" % (key_at - 1))
            if [v for a, v in init if a == 6] != [t.n, 0]:
                errs.append("%s: таймер на входе" % what)
            if len(ticks) != len(exp):
                errs.append("%s: тиков %d, ждали %d" % (what, len(ticks), len(exp)))
            for i in range(min(len(ticks), len(exp))):
                a = collections.Counter(x for x in ticks[i] if x[0] in CHECKED)
                b = collections.Counter(x for x in exp[i] if x[0] in CHECKED)
                if a != b:
                    errs.append("%s: тик %d: плеер %s, модель %s" % (what, i, sorted(a.elements()),
                                                                    sorted(b.elements())))
                    break
            if sorted(x for x in exitw if x[0] in CHECKED) != [(a, 0) for a in range(8, 15)]:
                errs.append("%s: выход без тишины" % what)
            if opts.save_zp and list(mem[opts.zp:opts.zp + opts.zp_bytes]) != zp_pat:
                errs.append("%s: нулевая страница не восстановлена" % what)
    return errs


# --- eCat3 ---

def ecat3_check(path, game, opts, workdir):
    """Игра в eCat3: драйвер с $4000 зовет все входы подряд, диск с «Быстропускалкой»;
    снимки регистров каждые 100 мс против модели (как verify.py)"""
    import mkdisk840
    import render
    drv = os.path.join(workdir, "yz2asm_game.a65")
    with open(drv, "w", encoding="utf-8") as f:
        f.write("            org $4000\n")
        for t in game.tunes:
            f.write("            jsr %s%s\n" % (opts.prefix, t.name))
        f.write("yz_halt     jmp yz_halt\n            include \"%s\"\n" % os.path.abspath(path).replace("\\", "/"))
    binf = os.path.join(workdir, "yz2asm_game.bin")
    lst = os.path.join(workdir, "yz2asm_game.lst")
    proc = subprocess.run([AS65, "-l" + lst, "-n", "-w", "-h0", "-o" + binf, drv], cwd=workdir,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0 or not os.path.exists(binf):
        raise SystemExit("AS65: игра для eCat3 не собралась")
    disk = mkdisk840.Disk840(open(os.path.join(ROOT, "disk", "template840.dsk"), "rb").read())
    if any(n == "SOUNDTEST" for _, n, _ in disk.listing()):
        disk.delete("SOUNDTEST")
    disk.set_volume("ЯЗС-ИГРА")
    disk.add("ЯЗС-ИГРА", mkdisk840.T_BIN, mkdisk840.b_body(0x4000, open(binf, "rb").read()), locked=True)
    dsk = os.path.join(workdir, "yz2asm_game.dsk")
    open(dsk, "wb").write(bytes(disk.d))
    # модель: состояние после каждого тика всей игры
    states, ends = [], []
    per, lo, phase = [None] * 5, {}, {a: 0 for a in CNT}
    for t in game.tunes:
        regs = [0] * 7
        for ws in (t.ref if game.tail else t.ref[:t.end] + [[]]):
            for a, v in ws:
                if 8 <= a <= 14:
                    regs[a - 8] = v
                elif a in CNT:
                    if phase[a] == 0:
                        lo[a] = v
                    else:
                        per[CNT.index(a)] = lo[a] | (v << 8)
                    phase[a] ^= 1
            states.append((tuple(regs), tuple(per)))
        ends.append(len(states))
    secs = int(sum(len(t.ref) * t.n / 7980.0 for t in game.tunes)) + 15
    lines = ['MACHINE "agat/Agat-9-yazs.ext"',
             'COMMAND fdd0.load("%s")' % dsk.replace("\\", "/"), "RESET cold", "SPEED MAX", "LOGDEFS 8,16"]
    for _ in range(secs * 10):
        lines += ["WAIT 100", "LOG yazs.irqs", "LOG yazs.regs($8,$E)", "LOG yazs.counters"]
    lines.append("EXIT")
    out = render.run(lines, "yz2asm_game", workdir, timeout=3600)
    vals = {"irqs": [], "regs": [], "counters": []}
    for line in out.splitlines():
        m = re.match(r"\[yazs\.(irqs|regs|counters)\](.*)", line)
        if m:
            text = m.group(2).split(":", 1)[1] if m.group(1) == "regs" else m.group(2)
            vals[m.group(1)].append([int(x, 16) for x in re.findall(r"\$([0-9A-Fa-f]+)", text)])
    ok = bad = 0
    for (irq,), regs, cnt in zip(vals["irqs"], vals["regs"], vals["counters"]):
        if irq == 0:
            continue
        regs, per_now = tuple(regs[:7]), tuple(cnt[:5])
        cands = [g for g in (irq - 1, irq - 2) if 0 <= g < len(states)]
        good = True
        for c in range(7):
            opts_c = []
            for g in cands:
                opts_c.append((states[g][0][c], states[g][1][c] if c < 5 else None))
                if g >= 1 and c < 5:
                    opts_c.append((states[g][0][c], states[g - 1][1][c]))
            if not any(r == regs[c] and (c >= 5 or p is None or p == per_now[c] or per_now[c] == 0)
                       for r, p in opts_c):
                good = False
        if not good and regs == (0,) * 7 and (irq in ends or irq >= len(states)):
            good = True
        ok += good
        bad += not good
    last = vals["irqs"][-1][0] if vals["irqs"] else 0
    return ok, bad, last, len(states)


# --- Командная строка ---

def main():
    ap = argparse.ArgumentParser(description="Мелодии .YZ -> встраиваемый плеер и данные для AS65 "
                                             "(docs/yz2asm.md)")
    ap.add_argument("inputs", nargs="+", metavar="[имя=]мелодия",
                    help="файл .yz/.yzt или партитура score/; имя - для входа")
    ap.add_argument("-o", "--out", default="yzmusic.a65", help="текст для ассемблера (yzmusic.a65)")
    ap.add_argument("--prefix", default="yz_", help="префикс всех имен (yz_): входы - <префикс><имя>")
    ap.add_argument("--slot", type=int, default=1, help="слот ЯЗС (1)")
    ap.add_argument("--zp", default="$10", help="начало переменных в нулевой странице ($10)")
    ap.add_argument("--ram", default="$0900", help="начало переменных в ОЗУ ($0900)")
    ap.add_argument("--key", action="store_true", help="выход по клавише (код остается в $C000)")
    ap.add_argument("--save-zp", action="store_true",
                    help="сохранять свои ячейки нулевой страницы и восстанавливать на выходе "
                         "(вызов из Бейсика: CALL адрес)")
    ap.add_argument("--no-tail", action="store_true",
                    help="без секунды отпускания после конца (не как у Студии, -40 байт)")
    ap.add_argument("--no-phrases", action="store_true", help="не искать повторы")
    ap.add_argument("--plain", action="store_true", help="без комментариев")
    ap.add_argument("--no-check", action="store_true", help="не проверять на 6502")
    ap.add_argument("--bin", help="еще и собрать образ с адреса --org")
    ap.add_argument("--org", default="$4000", help="адрес образа для --bin ($4000)")
    ap.add_argument("--ecat3", action="store_true", help="проверить в eCat3 (консольная сборка)")
    opts = ap.parse_args()
    opts.card = 0xC080 + 16 * opts.slot
    opts.zp, opts.ram, opts.org = num(opts.zp), num(opts.ram), num(opts.org)
    if not re.match(r"[A-Za-z_][A-Za-z0-9_]*$", opts.prefix):
        raise SystemExit("префикс %r - не имя" % opts.prefix)

    tunes, names = [], set()
    try:
        for arg in opts.inputs:
            name, data, src = load_input(arg)
            base, n = name, 2
            while name in names:
                name = "%s_%d" % (base, n)
                n += 1
            names.add(name)
            tunes.append(Tune(name, data, src))
        game = Game(tunes, tail=not opts.no_tail, phrases_on=not opts.no_phrases)
    except Rejected as e:
        raise SystemExit("yz2asm: %s" % e)
    text, info = generate(game, opts)
    opts.zp_bytes = info["zp"]
    if os.path.dirname(opts.out):
        os.makedirs(os.path.dirname(opts.out), exist_ok=True)
    with open(opts.out, "w", encoding="utf-8") as f:
        f.write(text)

    work = tempfile.mkdtemp(prefix="yz2asm_")
    res = None if opts.no_check and not opts.bin else assemble(opts.out, opts.org, work)
    print("%s: мелодий %d, каналов %d (тоновых %d, ударных %d)" % (
        opts.out, len(tunes), len(game.chans), len(game.tones), len(game.drums)))
    if res:
        image, sym = res
        p = opts.prefix
        entries = [sym[p + t.name] for t in tunes]
        code = sym[p + "shared"] - sym[p + "play"]
        shared = entries[0] - sym[p + "shared"]
        bounds = entries + [sym[p + "last"]]
        sizes = [bounds[i + 1] - bounds[i] for i in range(len(tunes))]
        print("  плеер %d, общие данные %d, мелодии %d: всего %d байт; нулевая страница %d, ОЗУ %d" % (
            code, shared, sum(sizes), sym[p + "last"] - sym[p + "play"], info["zp"], info["ram"]))
        for t, s in zip(tunes, sizes):
            print("  %-24s %5.1f с  %5d байт  вход $%04X (при сборке с $%04X)" % (
                p + t.name, t.seconds(), s, sym[p + t.name], opts.org))
        err = place_error(opts.org, len(image), opts.ram, info["ram"])
        if err:
            raise SystemExit("yz2asm: " + err)
        if opts.bin:
            with open(opts.bin, "wb") as f:
                f.write(image)
            print("  образ с $%04X: %s" % (opts.org, opts.bin))
        if not opts.no_check:
            errs = run_check(image, opts.org, sym, game, opts)
            if errs:
                for e in errs[:10]:
                    print("  ОШИБКА: " + e)
                raise SystemExit("yz2asm: проверка на 6502 не прошла")
            print("  проверка на 6502: все %d мелодий совпали с моделью тик в тик%s" % (
                len(tunes), ", выход по клавише - тоже" if opts.key else ""))
    elif not opts.no_check:
        print("  AS65 не запускается: без проверки и размеров кода")
    if opts.ecat3:
        ok, bad, last, total = ecat3_check(opts.out, game, opts, work)
        print("  eCat3: снимков совпало %d, расходятся %d; тиков по флагу %d, по модели %d" % (
            ok, bad, last, total))
        if bad or last != total:
            raise SystemExit("yz2asm: проверка в eCat3 не прошла")


if __name__ == "__main__":
    main()
