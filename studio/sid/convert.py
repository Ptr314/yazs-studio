# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Снятые регистры SID (c64.Dump) -> мелодия .YZ для ЯЗС (compose.Song). Как и
почему так переводится - docs/SID.md.

Одна строка .YZ = один кадр SID: N = 80, speed = 2 (строка 1/49.875 с, кадр PAL
1/50.125 с). Голоса SID 1-3 - тоновые каналы 1-3, ноты - по фронтам GATE:
- высота по кадрам: нота + DET (1/16 полутона), арпеджио - макрос арпеджио
  инструмента, вибрато - макрос высоты (или вибрато движка), лиги без нового удара;
  при синхронизации - частота ведущего голоса (heard);
- инструмент на ноту: полосы - по волне и фильтру, огибающая - ADSR SID,
  разложенная по тикам на ступени D4+D5 / D5 / щипок D4 (с loud - и с D3);
- шумовые ноты, «таблицы волн» ударных и ноты с падением на октаву (шум и
  падение - вместе с отпусканием) - в ударные 6 (бочка, томы, малый) и 7 (тарелки);
- chorus: каналы 4-5 повторяют ноты импульса с ШИМ с расстройкой.
"""

import math
import os

import numpy as np

import compose
import pyplay
import tables

from .c64 import FPS, hz

HF, MF, LF, D3, D4, D5 = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
TICK_MS = 1000.0 * 80 / tables.TIMER_CLOCK          # 10.03 мс
ATT = [2, 8, 16, 24, 38, 56, 68, 80, 100, 250, 500, 800, 1000, 3000, 5000, 8000]
DR = [3 * a for a in ATT]
K_EXP = math.log(256)                               # спад/отпускание SID: до -48 дБ за время шага

# Уровни ступеней огибающей ЯЗС, дБ от D3+D4+D5 (README: без D3 на 8-10 дБ тише,
# D5 без D4 на ~4 дБ тише)
LEVELS = [(D3 | D4 | D5, 0.0), (D3 | D5, -3.5), (D4 | D5, -9.0), (D5, -12.5)]
# 6581: срез по регистру (0-2047) - грубая кривая reSID; 8580 - линейная
FC6581 = [(0, 220), (256, 240), (512, 600), (768, 1500), (1024, 3500), (1280, 6000),
          (1536, 9000), (2047, 12000)]
# синхронизация медленным ведомым: тише этой доли амплитуды голос считается молчащим
AMP_MIN = 0.3


def db(x):
    return 20 * math.log10(x) if x > 1e-6 else -120.0


def fc_hz(fc, model8580=False):
    if model8580:
        return 30 + fc * 5.8
    for (x0, y0), (x1, y1) in zip(FC6581, FC6581[1:]):
        if fc <= x1:
            return y0 + (y1 - y0) * (fc - x0) / float(x1 - x0)
    return FC6581[-1][1]


# --- огибающая ---

def sid_level(ad, sr, t_ms):
    """Уровень SID 0..1 при удержанном GATE через t_ms после фронта"""
    a = ATT[ad >> 4]
    d = DR[ad & 15]
    s = (sr >> 4) / 15.0
    if t_ms < a:
        return t_ms / a
    return s + (1 - s) * math.exp(-K_EXP * (t_ms - a) / d)


LEVELS_SOFT = [(D4 | D5, 0.0), (D5, -3.5)]


def held_macro(ad, sr, bus, loud=False):
    """Макрос регистра на удержание GATE: ступени по уровню SID, без повторного D4.
    loud - лестница с D3 (+9..12 дБ): три голоса с D3 перегружают смеситель ЯЗС"""
    lv_tab = LEVELS if loud else LEVELS_SOFT
    off = len(lv_tab)
    a = ATT[ad >> 4]
    d = DR[ad & 15]
    s = (sr >> 4) / 15.0
    slow = a >= 250
    if s <= 1 / 15.0 and d <= 300 and not slow:
        # щипок: D4 сам спадает на 15 дБ за 300 мс; снять, когда SID ниже -26 дБ
        n = 1
        while n < 120 and db(sid_level(ad, sr, n * TICK_MS)) > -26:
            n += 1
        return [bus | (D3 if loud else 0) | D4] * n + [bus], "pluck"
    state = next(i for i, (r, _) in enumerate(lv_tab) if not r & D4) if slow else 0
    out = []
    n_ticks = min(200, int((a + d * 0.8) / TICK_MS) + 2)
    for k in range(n_ticks):
        t = k * TICK_MS
        # атака - это удар D4 (или плавная атака D5): уровень считается полным
        L = db(sid_level(ad, sr, t)) if t >= a else 0.0
        charged = t >= 250 or slow
        # ближайшая по уровню разрешенная ступень; текущей - запас 1.5 дБ
        cands = []
        for j in range(state, off + 1):
            reg, lv = lv_tab[j] if j < off else (0, -40.0 if loud else -30.0)
            if j != state and j < off:
                if (reg & D4) and not (lv_tab[state][0] & D4):
                    continue              # D4 заново не поднимаем
                if (reg & D3) and not (lv_tab[state][0] & D3):
                    continue              # D3 обратно не включаем
                if not (reg & D4) and not charged:
                    continue              # D5 без D4 - только после зарядки (~0.25 с)
            cands.append((abs(lv - L) - (1.5 if j == state else 0.0), j))
        state = min(cands)[1]
        out.append(bus | (lv_tab[state][0] if state < off else 0))
        if state == off:
            break
    # хвост одинаковых значений не нужен: макрос держит последнее
    while len(out) > 1 and out[-1] == out[-2]:
        out.pop()
    return out, "held"


def release_macro(held, sr, bus, loud=False):
    """Отпускание после снятия GATE от значения удержания"""
    r = DR[sr & 15]
    last = held[-1]
    if r <= 72 or not (last & D5):
        return [bus | (last & D3)]
    out = []
    lv0 = dict(LEVELS if loud else LEVELS_SOFT).get(last & 0x38, 0.0)
    for k in range(200):
        L = lv0 + db(math.exp(-K_EXP * k * TICK_MS / r))
        if L > -6 and (last & D3):
            v = D3 | D5
        elif L > -16:
            v = D5
        else:
            out.append(bus)
            break
        out.append(bus | v)
    while len(out) > 1 and out[-1] == out[-2]:
        out.pop()
    return out


def vib_macro(t16, D, period):
    """Вибрато SID как макрос высоты (1/16 полутона за тик): (макрос, повтор) или None.
    Кадр k - тик 2k от включения; приращение кадра делится на два тика. Начало цикла
    ищется: у Хаббарда первый шаг вибрато - скачок на полразмаха"""
    d = [t16[i] - t16[i - 1] for i in range(1, len(t16))]      # d[k-1] - приращение кадра k
    P0 = int(round(period))
    for P in sorted(range(max(2, P0 - 2), P0 + 3), key=lambda x: abs(x - period)):
        r = _vib_cycle(d, D, P)
        if r:
            return r
    return None


def _vib_cycle(d, D, P):
    for st in range(max(0, D - 1), max(0, D - 1) + P + 1):
        if len(d) < st + P + 2:
            return None
        seg = list(d[st:st + P])
        if not any(seg):
            continue
        # округление до 1/16 дает разброс приращений на единицу: сверка с допуском 1
        bad = sum(1 for i in range(st + P, len(d)) if abs(d[i] - seg[(i - st) % P]) > 1)
        if bad > max(1, (len(d) - st) // 10):
            continue
        if abs(sum(seg)) > 2:
            continue
        while sum(seg) != 0:                 # сумма цикла - ноль, иначе высота уползет
            i = max(range(P), key=lambda j: abs(seg[j]))
            seg[i] -= 1 if sum(seg) > 0 else -1
        macro = [0]
        for x in d[:st]:
            macro += [x // 2, x - x // 2]
        loop = len(macro)
        for x in seg:
            macro += [x // 2, x - x // 2]
        if len(macro) > 120:
            return None
        return [v & 0xFF for v in macro], loop
    return None


# --- разбор нот ---

def wave_class(ctrl, pw):
    w = ctrl >> 4
    if ctrl & 4 and w & 1:
        return "ring"
    if ctrl & 2:
        return "sync"
    if w == 1:
        return "tri"
    if w == 4:
        duty = (pw & 0xFFF) / 4096.0
        return "pw" if 0.2 <= duty <= 0.8 else "pn"
    if w & 2:
        return "saw"
    if w & 4:
        return "pw"
    return "tri"


BUS = {"tri": LF, "saw": LF | MF | HF, "pw": LF | MF, "pn": MF | HF, "ring": MF | HF, "sync": LF | MF | HF}
LABEL = {"tri": "ТРЕ", "saw": "ПИЛ", "pw": "ИМШ", "pn": "ИМУ", "ring": "КОЛ", "sync": "СИН"}


def agat_text(t):
    return "".join(c if c in tables.AGAT else " " for c in t.upper())


def heard(d, v):
    """Что слышно у голоса v по кадрам: (частота, доля амплитуды, слышен ли выход).
    - Синхронизация: фаза сбрасывается с периодом ведущего голоса (голос 1 - от 3, 2 - от 1,
      3 - от 2), поэтому высота - его. Ведомый медленнее ведущего (r = f/fm < 1) не проходит
      цикл: треугольник поднимается до 2r, пила - до r, импульс не доходит до ширины - тишина.
      Так считаются только ноты, где синхронизация - большая часть кадров под GATE: одиночный
      кадр в ударном (у Mike Brown) высоту ноты не меняет.
    - Голос через фильтр, у которого не выбран ни один выход (режим 0), не слышен; голос 3 при
      3OFF ($D418 D7) не слышен, если идет мимо фильтра."""
    m = (v + 2) % 3
    ctrl = d.ctrl[v].astype(np.int32)
    f = d.freq[v].astype(np.int64)
    fm = d.freq[m].astype(np.int64)
    sync = ((ctrl & 2) != 0) & ((d.ctrl[m].astype(np.int32) & 8) == 0) & (fm > 0)
    in_note = np.zeros(len(f), bool)
    for s, g, nxt in d.notes(v):
        if sync[s:max(g, s + 1)].mean() > 0.5:
            in_note[s:nxt] = True
    sync &= in_note
    freq = np.where(sync, fm, f)
    r = np.where(sync, f / np.maximum(fm, 1).astype(float), 1.0)
    w = ctrl >> 4
    pw = (d.pw[v] & 0xFFF) / 4096.0
    amp = np.where(~sync, 1.0,
                   np.where((w & 2) != 0, np.minimum(1.0, r),
                            np.where((w & 1) != 0, np.minimum(1.0, 2 * r),
                                     np.where(w == 4, (r > pw + 0.02).astype(float), 1.0))))
    routed = ((d.route >> v) & 1).astype(bool)
    out = ~(routed & (d.mode == 0))
    if v == 2:
        out &= ~((d.v3off == 1) & ~routed)
    return freq, amp, out


class Converter(object):
    """dump - c64.Dump, sf - psid.SidFile; end - сколько кадров переводить;
    chorus - False, True (два голоса, где больше ШИМ) или номера голосов [1, 2];
    release_drums - ударные и по отпусканию: спад высоты и шум после снятия GATE (томы
    Mike Brown в Joe Blade 2 - бочка, слушатели предпочли ее тоновому щелчку)"""

    def __init__(self, dump, sf, chorus=False, end=None, loud=False, version=None, release_drums=False):
        self.loud = loud
        self.release_drums = release_drums
        self.d = dump
        self.freq, self.amp, self.out = zip(*[heard(dump, v) for v in range(3)])
        self.m8580 = "8580" in sf.model and "6581" not in sf.model
        self.chorus = chorus
        self.end = end or dump.frames
        title = sf.name if sf.name not in ("<?>", "") else \
            os.path.splitext(os.path.basename(sf.path))[0].replace("_", " ")
        sub = " ".join(x for x in (sf.author, sf.released) if x and x != "<?>")
        self.song = compose.Song(agat_text(title)[:30], agat_text(sub)[:30], bpm=FPS * 60, rows_per_beat=1,
                                 beats_per_bar=64, speed=2, version=version)
        assert self.song.n == 80 and self.song.speed == 2, (self.song.n, self.song.speed)
        self.ins_index = {}
        self.ins_info = []
        self.drums = {5: {}, 6: {}}       # строка -> (приоритет, пресет)
        self.plan = [dict() for _ in range(5)]   # канал -> строка -> высота (1/16), записанная покадрово
        self.tonal_rows = [set() for _ in range(5)]   # строки, где канал должен звучать тоном
        self.row_kind = [dict() for _ in range(5)]
        self.notes_log = [[] for _ in range(5)]
        self.stats = {"tonal": 0, "drum6": 0, "drum7": 0, "legato": 0, "det": 0, "noise_attack": 0}

    # инструменты
    def instrument(self, cls, ad, sr, bus, mot=None):
        """mot: None, ("arp", макрос, повтор) или ("vib", задержка, скорость, глубина)"""
        key = (cls, ad, sr, bus, mot)
        if key in self.ins_index:
            return self.ins_index[key]
        held, kind = held_macro(ad, sr, bus, self.loud)
        rel = release_macro(held, sr, bus, self.loud)
        mark = {"arp": "А", "vib": "В", "pitch": "В"}.get(mot[0], " ") if mot else " "
        label = "%s%s%02X%02X" % (LABEL[cls], mark, ad, sr)
        s = (sr >> 4)
        name = "i%d" % len(self.ins_info)
        kw = {}
        if mot and mot[0] == "arp":
            kw["arp"], kw["arp_loop"] = list(mot[1]), mot[2]
        if mot and mot[0] == "vib":
            kw["vib"] = (mot[1], mot[2], mot[3])
        if mot and mot[0] == "pitch":
            kw["pitch"], kw["pitch_loop"] = list(mot[1]), mot[2]
        self.song.instrument(name, label, held, rel=rel,
                             meter=(15, s if kind == "held" else 0, 2 if kind == "held" else 8), **kw)
        idx = self.song.inames[name]
        self.ins_index[key] = idx
        self.ins_info.append({"key": key, "held": held, "rel": rel, "kind": kind})
        return idx

    def note_bus(self, v, frames, f0):
        d = self.d
        cls = {}
        for f in frames:
            c = wave_class(int(d.ctrl[v][f]), int(d.pw[v][f]))
            cls[c] = cls.get(c, 0) + 1
        c = max(cls, key=cls.get)
        bus = BUS[c]
        routed = [f for f in frames if (d.route[f] >> v) & 1]
        if len(routed) * 2 >= len(frames):
            f = routed[len(routed) // 2]
            mode = int(d.mode[f])
            cut = fc_hz(int(d.fc[f]), self.m8580)
            # выход фильтра - сумма выбранных: LP+BP - тот же НЧ, BP+HP - ВЧ, LP+HP -
            # режекторный (вырезает узкую полосу у среза), LP+BP+HP - почти без фильтра:
            # последние два полосы не меняют
            if mode in (1, 3):        # LP
                if cut < 2 * f0:
                    bus = LF
                elif cut < 5 * f0:
                    bus = (bus & (LF | MF)) or LF
            elif mode == 2:           # BP
                bus = MF
            elif mode in (4, 6):      # HP
                bus = MF | HF if cut < 2 * f0 else HF
        return c, bus

    @staticmethod
    def falling(p):
        """Высота (полутона по кадрам ноты с отпусканием) падает почти каждый кадр и до
        конца: удар. Не удар:
        - нота, которая после «подбоя» встает на высоту (бас Тела: D#3, B1, затем D#1 ровно);
        - арпеджио: высота возвращается вверх или держится ступенями (аккорды Тела
          F5 F5 C5 C5 G4 G4 F4 F4, вверх - уже на отпускании)"""
        steps = list(zip(p, p[1:]))
        if not steps or any(b - a > 0.5 for a, b in steps):
            return False
        return sum(1 for a, b in steps if a - b < 0.1) * 3 <= len(steps)

    def drum(self, ch, row, prio, preset):
        if ch == 5 and not self.loud:
            preset &= 7                   # ударный 6 с D3 вдвое громче всех тонов вместе
        old = self.drums[ch].get(row)
        if old is None or prio > old[0]:
            self.drums[ch][row] = (prio, preset)

    def semi(self, freq):
        """Высота в полутонах .YZ (0 = C0), дробная"""
        return 57 + 12 * math.log2(hz(freq) / 440.0)

    def t16(self, freq):
        return int(round(self.semi(freq) * 16))

    @staticmethod
    def segments(p, thr=0.75):
        """Начала участков с новой высотой (сдвиг > thr полутона, держится 3 кадра)"""
        segs, center = [0], p[0]
        for i in range(1, len(p)):
            if all(abs(x - center) > thr for x in p[i:i + 3]):
                segs.append(i)
                center = p[i]
        return segs

    @staticmethod
    def motion(p):
        """Движение высоты ноты по кадрам (полутона): ("static",), ("arp", r0, цикл),
        ("vib", D, период, размах) или None - писать покадрово"""
        if len(p) < 3:
            return ("static",)
        offs = [x - p[0] for x in p]
        r = [int(round(o)) for o in offs]
        if all(abs(o - ro) < 0.15 for o, ro in zip(offs, r)) and len(set(r)) > 1:
            for k in (1, 2, 3, 4):
                if len(r) > k + 1 and all(r[i] == r[i + k] for i in range(1, len(r) - k)):
                    return ("arp", r[0], r[1:1 + k])
            return None
        mx = max(abs(x) for x in offs)
        if mx < 0.07:
            return ("static",)
        if mx > 1.0 or len(p) < 8:
            return None
        D = next(i for i, x in enumerate(offs) if abs(x) > 0.07)
        sg = [(i, 1 if x > 0 else -1) for i, x in enumerate(offs) if i >= D and abs(x) > 0.07]
        chg = [sg[j][0] for j in range(1, len(sg)) if sg[j][1] != sg[j - 1][1]]
        if len(chg) < 2:
            return None
        period = 2.0 * (chg[-1] - chg[0]) / max(1, len(chg) - 1)
        if period < 2:
            return None
        return ("vib", D, period, mx)

    def voice(self, v, ch):
        d, s_ = self.d, self.song
        # freq - слышимая высота (при синхронизации - ведущего голоса), raw - регистр голоса
        ctrl, freq, raw = d.ctrl[v], self.freq[v], d.freq[v]
        amp, out = self.amp[v], self.out[v]
        cur_det, cur_ins = 0, None
        sounding_until = -1
        for s, g, nxt in d.notes(v):
            if s >= self.end:
                break
            nxt = min(nxt, self.end)
            g = max(min(g, nxt), s + 1)
            gated = list(range(s, g))
            waves = [int(ctrl[f]) >> 4 for f in gated]
            noise = [f for f, w in zip(gated, waves) if w & 8 and out[f]]
            tonal = [f for f, w in zip(gated, waves) if w and not w & 8 and not ctrl[f] & 8 and freq[f] > 0
                     and out[f] and amp[f] >= AMP_MIN]
            ad, sr = int(d.ad[v][s]), int(d.sr[v][s])
            dur_ms = (g - s) * 1000 / FPS + DR[sr & 15] * 0.3
            # отпускание, пока не стихло на ~24 дБ: тарелка Тела - кадр шума, кадр тона и
            # шум на долгом отпускании
            after = list(range(g, min(nxt, g + int(DR[sr & 15] * 0.5 * FPS / 1000.0) + 1)))
            noise_after = [f for f in after if (int(ctrl[f]) >> 4) & 8 and out[f]]
            # шум на отпускании считается, если он есть и под GATE (с release_drums - всегда:
            # Joe Blade 2 № 3, пила D3, затем шум - том)
            n8 = sum(1 for f in noise + noise_after if f < s + 8) if noise or self.release_drums else 0
            drum = None
            # --- ударные ---
            if noise and (len(noise) + len(noise_after)) * 2 >= len(gated) + len(after):
                nf = int(np.median([raw[f] for f in noise + noise_after]))
                if nf < 0x400:
                    drum = (5, 3, 0x08)                 # «стук» шума на нулевой частоте - бочка
                elif nf >= 0x6000 and any(hz(int(raw[f])) < 400 for f in tonal):
                    # высокий шум с тоном корпуса ниже 400 Гц - малый (у Тела шум и импульс
                    # G3); тарелки и хай-хэт - шум с кольцевой A5 или без тона
                    drum = (5, 2, 0x0E)
                elif nf >= 0x6000:
                    drum = (6, 2, 0x0B) if dur_ms > 250 else (6, 1, 0x03)
                elif nf >= 0x2000:
                    drum = (5, 2, 0x0E)                 # малый
                else:
                    drum = (5, 2, 0x0D)
            elif not tonal:
                continue
            else:
                p = [self.semi(int(freq[f])) for f in tonal]
                hz_t = [hz(int(freq[f])) for f in tonal]
                # падение на октаву за 8 кадров под GATE; у нот длиннее 4 кадров высота (с
                # отпусканием, по регистру голоса) должна падать до конца. С release_drums падение
                # считается и по отпусканию, если под GATE хотя бы два кадра тона (томы Mike Brown:
                # шум, импульс G#3-E3 и спад до D1 на отпускании)
                fr = [f for f in tonal + after if raw[f] > 0 and out[f] and int(ctrl[f]) >> 4 and
                      not (int(ctrl[f]) >> 4) & 8 and not ctrl[f] & 8]
                hz_r = [hz(int(raw[f])) for f in fr]
                pr = [self.semi(int(raw[f])) for f in fr]
                drop_g = min(p[:8]) - p[0] <= -12 and (len(p) <= 4 or self.falling(pr))
                drop_r = self.release_drums and len(p) >= 2 and min(pr[:8]) - pr[0] <= -12 and \
                    self.falling(pr)
                if n8 >= 2:
                    # таблица волн ударного: шум и тон вперемешку
                    tail = hz_t[min(len(hz_t) - 1, 6)]
                    if tail < 90:
                        drum = (5, 3, 0x08)
                    elif n8 >= 4:
                        drum = (5, 2, 0x0E)
                    else:
                        drum = (5, 2, 0x09 if hz_t[0] < 200 else (0x0B if hz_t[0] < 400 else 0x0D))
                elif len(gated) <= 15 and (drop_g or drop_r):
                    # пресет - по высоте под GATE, у падения по отпусканию - с ним
                    hs = hz_r if drop_r and (len(p) > 4 or not drop_g) else hz_t
                    f0, f1 = hs[0], hs[min(7, len(hs) - 1)]
                    preset = 0x08 if (f1 < 80 or f0 < 200) else (0x09 if f0 < 300 else (0x0B if f0 < 500 else 0x0D))
                    drum = (5, 3 if preset == 0x08 else 2, preset)
            if drum:
                self.drum(drum[0], s, drum[1], drum[2])
                if sounding_until > s:
                    s_.put(ch, s, (compose.CMD_CUT,))
                sounding_until = -1
                continue
            # --- тоновая нота ---
            self.stats["tonal"] += 1
            on = tonal[0]
            if on > s:
                self.stats["noise_attack"] += 1
                if sounding_until > s:
                    s_.put(ch, s, (compose.CMD_CUT,))
            contiguous = tonal == list(range(on, on + len(tonal)))
            mot = self.motion(p) if contiguous else None
            legs = None
            if mot is None and contiguous:
                # лиги внутри ноты (новая высота без снятия GATE), на каждой - вибрато или ровно
                sp = self.segments(p)
                parts = [p[a:b] for a, b in zip(sp, sp[1:] + [len(p)])]
                if len(sp) > 1 and all(max(abs(x - q[0]) for x in q) <= 0.6 for q in parts):
                    legs = sp
                    m0 = self.motion(parts[0])
                    if not (m0 and m0[0] == "vib"):
                        longest = max(parts, key=len)
                        m1 = self.motion(longest)
                        m0 = ("vib", m0[1] if m0 and m0[0] == "vib" else 4, m1[2], m1[3]) if m1 and m1[0] == "vib" else ("static",)
                    mot = m0
            f0 = float(np.median(hz_t))
            cls, bus = self.note_bus(v, tonal, f0)
            insmot = None
            if mot and mot[0] == "arp":
                r0, cyc = mot[1], list(mot[2])
                lo = min([r0] + cyc)
                semi0 = p[0] + lo
                base = int(round(semi0))
                det = int(round((semi0 - base) * 16))
                # кадр 0 - r0, дальше цикл с кадра 1; на кадр - два тика
                macro = [r0 - lo] + [x - lo for x in cyc for _ in (0, 1)]
                insmot = ("arp", tuple(macro), 1)
                self.stats["arp_notes"] = self.stats.get("arp_notes", 0) + 1
            elif mot and mot[0] == "vib":
                D, period, mx = mot[1], mot[2], mot[3]
                base = int(round(p[0]))
                det = int(round((p[0] - base) * 16))
                vm = None if legs else vib_macro([int(round(x * 16)) for x in p], D, period)
                if vm:
                    insmot = ("pitch", tuple(vm[0]), vm[1])
                    self.stats["vib_macro_notes"] = self.stats.get("vib_macro_notes", 0) + 1
                else:
                    insmot = ("vib", max(0, 2 * D - 1), max(1, min(15, int(round(32.0 / period)))),
                              max(1, min(15, int(round(mx * 16)))))
                    self.stats["vib_notes"] = self.stats.get("vib_notes", 0) + 1
            else:
                lo, hi = min(p), max(p)
                base = int(round((lo + hi) / 2.0))
                if (hi - lo) * 16 > 254:
                    base = int(round(p[0]))
                det = int(round((p[0] - base) * 16))
            base = max(0, min(95, base))
            det = max(-127, min(127, det))
            ins = self.instrument(cls, ad, sr, bus, insmot)
            if ins != cur_ins:
                s_.put(ch, on, (compose.CMD_INSTR, ins))
                cur_ins = ins
            if det != cur_det:
                s_.put(ch, on, (compose.CMD_FX + compose.EFFECTS["det"], det & 0xFF))
                cur_det = det
                self.stats["det"] += 1
            s_.put(ch, on, (base,))
            rel_frames = int(len(self.ins_info[ins]["rel"]) * TICK_MS * FPS / 1000.0) + 2
            audible = min(nxt, g + rel_frames)
            kind = "frame" if mot is None else ("legato" if legs else (insmot[0] if insmot else mot[0]))
            for f in range(on, g):
                w_ = int(ctrl[f]) >> 4
                if freq[f] > 0 and w_ and not w_ & 8 and not ctrl[f] & 8 and out[f] and amp[f] >= AMP_MIN:
                    self.tonal_rows[ch].add(f)
                    self.row_kind[ch][f] = kind
            if mot is None:
                self.plan[ch][on] = base * 16 + det
                for f in range(on + 1, audible):
                    if freq[f] == 0 or ctrl[f] & 8 or (int(ctrl[f]) >> 4) & 8 or not int(ctrl[f]) >> 4:
                        continue
                    t = self.t16(int(freq[f]))
                    want = t - base * 16
                    if f < g and abs(want) > 127:
                        base = max(0, min(95, int(round(t / 16.0))))
                        s_.put(ch, f, (compose.CMD_LEGATO, base))
                        self.stats["legato"] += 1
                        want = t - base * 16
                    want = max(-127, min(127, want))
                    if want != cur_det:
                        s_.put(ch, f, (compose.CMD_FX + compose.EFFECTS["det"], want & 0xFF))
                        cur_det = want
                        self.stats["det"] += 1
                    if f < g:
                        self.plan[ch][f] = base * 16 + want
                self.stats["frame_notes"] = self.stats.get("frame_notes", 0) + 1
            elif legs:
                for k in legs[1:]:
                    q = p[k]
                    b2 = max(0, min(95, int(round(q))))
                    d2 = max(-127, min(127, int(round((q - b2) * 16))))
                    if d2 != cur_det:
                        s_.put(ch, on + k, (compose.CMD_FX + compose.EFFECTS["det"], d2 & 0xFF))
                        cur_det = d2
                        self.stats["det"] += 1
                    s_.put(ch, on + k, (compose.CMD_LEGATO, b2))
                    self.stats["legato"] += 1
                self.stats["legato_notes"] = self.stats.get("legato_notes", 0) + 1
            elif mot[0] == "static":
                self.plan[ch][on] = base * 16 + det
            if g < nxt:
                s_.put(ch, g, (compose.CMD_OFF,))
            sounding_until = audible
            pwm = cls in ("pw", "pn") and sum(1 for f in range(on + 1, g) if d.pw[v][f] != d.pw[v][f - 1]) >= 2
            self.notes_log[ch].append({"on": on, "nxt": nxt, "ins": ins, "det": det, "pwm": pwm})

    def chorus_voice(self, src, ch, off16):
        """Канал ch повторяет ноты импульса с ШИМ канала src с расстройкой off16:
        ширину импульса ЯЗС не меняет, движение тембра дают биения двух каналов"""
        s_ = self.song
        DET = compose.CMD_FX + compose.EFFECTS["det"]
        sounding = False
        n = 0
        for nl in self.notes_log[src]:
            if not nl["pwm"]:
                if sounding:
                    s_.put(ch, nl["on"], (compose.CMD_OFF,))
                    sounding = False
                continue
            s_.put(ch, nl["on"], (compose.CMD_INSTR, nl["ins"]))
            s_.put(ch, nl["on"], (DET, max(-127, min(127, nl["det"] + off16)) & 0xFF))
            for row in range(nl["on"], nl["nxt"]):
                for c in s_.rows[src].get(row, []):
                    if c[0] == compose.CMD_INSTR or (row == nl["on"] and c[0] == DET):
                        continue
                    if c[0] == DET:
                        dv = c[1] - 256 if c[1] & 0x80 else c[1]
                        c = (DET, max(-127, min(127, dv + off16)) & 0xFF)
                    s_.put(ch, row, c)
            sounding = True
            n += 1
        self.stats["chorus%d" % ch] = n

    def run(self):
        for v in range(3):
            self.voice(v, v)
        for ch, ev in self.drums.items():
            for row, (_, preset) in ev.items():
                self.song.put(ch, row, (preset,))
                self.stats["drum6" if ch == 5 else "drum7"] += 1
        if self.chorus:
            # два голоса, где больше всего нот с ШИМ; +-3/16 полутона = +-19 центов
            if isinstance(self.chorus, (list, tuple)):
                order = [v - 1 for v in self.chorus]
            else:
                order = sorted(range(3), key=lambda v: -sum(1 for n in self.notes_log[v] if n["pwm"]))[:2]
            self.chorus_voice(order[0], 3, 3)
            self.chorus_voice(order[1], 4, -3)
            self.stats["chorus_of"] = [v + 1 for v in order]
        self.song.end_row = max(self.song.end_row, self.end)
        return self.song


# --- кадры .YZ ---

def make_bounds(total, L, loop_start=None):
    """Кадры по L строк; с кадром повтора - и с начала повтора"""
    if loop_start:
        b = list(range(0, loop_start, L)) + list(range(loop_start, total, L)) + [total]
    else:
        b = list(range(0, total, L)) + [total]
    return sorted(set(b))


def estimate(song, bounds):
    """(кадров, паттернов, байт v1, байт v2 без выравнивания блоков) - без сборки файла"""
    keys = [sorted(song.rows[ch]) for ch in range(8)]
    seen, size = set(), 0
    for a, b in zip(bounds, bounds[1:]):
        for ch in range(8):
            p = song.encode_pattern(ch, a, b - a, keys)
            if p not in seen:
                seen.add(p)
                size += len(p)
    frames, npat = len(bounds) - 1, len(seen)
    rest = sum(len(i.encode()) + 2 for i in song.instruments) + sum(len(t) + 3 for t in song.texts) + 2
    return frames, npat, compose.HDR_V1 + 9 * frames + 2 * npat + size + rest, \
        compose.HDR_V2 + 17 * frames + 3 * npat + size + rest


def choose_frames(song, total, loop_start=None, version=None):
    """Длина кадра (24-255 строк), при которой файл меньше: в v1, если он туда
    помещается (или version = 1), иначе в v2. [(байт, L, версия)] по возрастанию"""
    v1, v2 = [], []
    for L in range(24, 256):
        b = make_bounds(total, L, loop_start)
        frames, npat, s1, s2 = estimate(song, b)
        if frames <= 255 and npat <= 256 and s1 <= compose.MAX_V1:
            v1.append((s1, L, 1))
        v2.append((s2, L, 2))
    if version == 1:
        return sorted(v1)
    if version == 2 or not v1:
        return sorted(v2)
    return sorted(v1)


def build(song, total, loop_start=None, loop_from_start=False, version=None):
    """Собрать .YZ с лучшей длиной кадра: (данные, длина кадра, кадр повтора)"""
    errors = []
    for size, L, ver in choose_frames(song, total, loop_start, version)[:20]:
        bounds = make_bounds(total, L, loop_start)
        song.loop = bounds.index(loop_start) if loop_start else (0 if loop_from_start else None)
        song.version = ver
        try:
            return song.build(bounds), L, song.loop
        except ValueError as e:
            errors.append(str(e))
    raise ValueError("мелодия не помещается в формат: %s" % (errors[-1] if errors else
                                                              "нет подходящей длины кадра"))


# --- сверка с эталонной моделью движка ---

def verify(data, conv, end):
    """pyplay по .YZ: на тике 1 каждой строки - период каналов 1-3 против SID и плана"""
    p = pyplay.Player(data)
    errs, miss, extra, exact_bad, n_plan = [], 0, 0, 0, 0
    by_kind = {}
    row = 0
    while row < end:
        tk = p.tick
        if not p.step():
            break
        if tk != 1:
            continue
        for ch in range(3):
            t = p.tone[ch]
            if row in conv.tonal_rows[ch]:
                if t.state != 1:
                    miss += 1
                    continue
                f_yz = tables.CLOCK / float(t.last_per)
                f_sid = hz(int(conv.freq[ch][row]))
                if f_sid > 0:
                    e_ = 1200 * math.log2(f_yz / f_sid)
                    errs.append(e_)
                    k_ = conv.row_kind[ch].get(row, "?")
                    by_kind.setdefault(k_, []).append(abs(e_))
                want = conv.plan[ch].get(row)
                if want is not None:
                    n_plan += 1
                    if t.last_per != pyplay.period_of(max(0, min(1535, want))):
                        exact_bad += 1
            elif t.state == 1:
                extra += 1
        row += 1
    e = np.abs(np.array(errs)) if errs else np.zeros(1)
    return {"rows": row, "tonal": len(errs), "silent_in_tonal": miss, "playing_outside": extra,
            "plan_rows": n_plan, "plan_not_exact": exact_bad,
            "cents_median": round(float(np.median(e)), 1), "cents_p95": round(float(np.percentile(e, 95)), 1),
            "share_over_25c": round(float(np.mean(e > 25)), 3),
            "over_25c_by_kind": {k: "%d/%d" % (sum(1 for x in v if x > 25), len(v)) for k, v in sorted(by_kind.items())}}
