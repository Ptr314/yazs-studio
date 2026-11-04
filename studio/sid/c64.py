# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Прогон мелодии PSID в окружении C64 без ПЗУ и запись регистров SID по кадрам
(как siddump).

Окружение: 64 КБ ОЗУ с загруженной мелодией, init(A = мелодия - 1), затем play
раз в кадр PAL (19656 тактов). Ввод-вывод $D000-$DFFF виден по разрядам порта $01:
- SID $D400-$D7FF (зеркала через $20): запись - в лог, чтение OSC3/ENV3 - грубая
  модель голоса 3, остальные регистры - последнее значение на шине (держится
  ~0x1D00 тактов, как у 6581 в reSID);
- VIC: $D011/$D012 - растр по счетчику тактов, остальное - теневая память;
- CIA: таймеры A/B считают вниз от защелки, ICR читается нулем.
BRK и JAM - ошибка: вызов ПЗУ C64, которого нет.
"""

import math

import numpy as np

from . import cpu6502

PAL_CLOCK = 985248
FRAME = 19656                   # 312 строк по 63 такта
FPS = PAL_CLOCK / float(FRAME)  # 50.125 Гц
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def hz(freq):
    """Частота голоса по регистру (PAL)"""
    return freq * PAL_CLOCK / 16777216.0


def midi(freq):
    """Высота в полутонах MIDI (69 = A4 440 Гц), дробная; None для 0"""
    if freq <= 0:
        return None
    return 69 + 12 * math.log2(hz(freq) / 440.0)


def note_name(m):
    n = int(round(m))
    return "%s%d" % (NAMES[n % 12], n // 12 - 1)


class Unsupported(Exception):
    pass


class Env(object):
    def __init__(self, sf):
        self.sf = sf
        self.cpu = c = cpu6502.CPU6502()
        m = c.m
        m[sf.load:sf.load + len(sf.data)] = sf.data
        m[0], m[1] = 0x2F, 0x37
        self.io = bytearray(0x1000)        # теневая память $D000-$DFFF
        self.sid = bytearray(32)
        self.bus = 0
        self.bus_t = -10 ** 9
        self.frame = 0
        self.ev = []                       # (кадр, регистр, значение)
        self.reads = {}                    # чтения SID: регистр -> число
        self.cia_latch = {0xC04: 0xFFFF, 0xC06: 0xFFFF, 0xD04: 0xFFFF, 0xD06: 0xFFFF}
        self.cia_writes = 0
        self.v3_t0 = 0
        self.v3_acc = 0
        self.lfsr = 0x7FFFF8
        c.io_read = self.io_read
        c.io_write = self.io_write
        c.io_visible = self.io_visible
        c.table[0x00] = self.brk

    def brk(self):
        raise cpu6502.Halt("BRK в $%04X (вызов ПЗУ C64?)" % ((self.cpu.pc - 1) & 0xFFFF))

    def io_visible(self):
        m = self.cpu.m
        eff = ((m[1] & m[0]) | (~m[0] & 0x17)) & 7
        return (eff & 3) != 0 and (eff & 4) != 0

    # --- голос 3 для OSC3/ENV3 ---

    def v3_phase(self):
        f = self.sid[14] | (self.sid[15] << 8)
        return (self.v3_acc + f * (self.cpu.cycles - self.v3_t0)) & 0xFFFFFF

    def v3_sync(self):
        self.v3_acc = self.v3_phase()
        self.v3_t0 = self.cpu.cycles

    def osc3(self):
        acc = self.v3_phase()
        ctrl = self.sid[18]
        if ctrl & 0x80:
            self.lfsr = ((self.lfsr << 1) | (((self.lfsr >> 22) ^ (self.lfsr >> 17)) & 1)) & 0x7FFFFF
            return self.lfsr & 0xFF
        if ctrl & 0x40:
            pw = (self.sid[16] | (self.sid[17] << 8)) & 0xFFF
            return 0xFF if (acc >> 12) >= pw else 0
        if ctrl & 0x20:
            return acc >> 16
        if ctrl & 0x10:
            t = acc >> 15
            return (t ^ 0x1FF if t & 0x100 else t) & 0xFF
        return 0

    # --- ввод-вывод ---

    def io_read(self, a):
        o = a - 0xD000
        if 0x400 <= o < 0x800:
            r = o & 0x1F
            self.reads[r] = self.reads.get(r, 0) + 1
            if r == 0x1B:
                return self.osc3()
            if r == 0x1C:
                return (self.sid[20] >> 4) * 17 if self.sid[18] & 1 else 0
            return self.bus if self.cpu.cycles - self.bus_t < 0x1D00 else 0
        if o in (0x11, 0x12):
            line = (self.cpu.cycles % FRAME) // 63
            return (self.io[0x11] & 0x7F) | ((line >> 1) & 0x80) if o == 0x11 else line & 0xFF
        if 0xC00 <= o < 0xE00:
            base = o & 0xF0F
            if base in (0xC04, 0xC05, 0xC06, 0xC07, 0xD04, 0xD05, 0xD06, 0xD07):
                lat = self.cia_latch[base & ~1]
                v = lat - (self.cpu.cycles % (lat + 1))
                return v & 0xFF if base & 1 == 0 else v >> 8
            if base in (0xC0D, 0xD0D):
                return 0
        return self.io[o]

    def io_write(self, a, v):
        o = a - 0xD000
        if 0x400 <= o < 0x800:
            r = o & 0x1F
            if r in (14, 15, 18):
                self.v3_sync()
            self.sid[r] = v
            self.bus = v
            self.bus_t = self.cpu.cycles
            if r < 25:
                self.ev.append((self.frame, r, v))
            return
        if 0xC00 <= o < 0xE00:
            base = o & 0xF0F
            if base in (0xC04, 0xC05, 0xC06, 0xC07, 0xD04, 0xD05, 0xD06, 0xD07):
                k = base & ~1
                lat = self.cia_latch[k]
                lat = (lat & 0xFF00) | v if base & 1 == 0 else (lat & 0xFF) | (v << 8)
                self.cia_latch[k] = lat
                self.cia_writes += 1
        self.io[o] = v


def run(sf, song, seconds=300, quiet_s=4.0, still_s=10.0):
    """Прогон мелодии song (с 1): Dump. Конец - время, тишина (GATE снят у всех
    голосов quiet_s секунд) или «замерла» (регистры не меняются still_s секунд)"""
    if sf.magic == "RSID":
        raise Unsupported("RSID: нужно полное окружение C64 (прерывания, CIA, ПЗУ)")
    if sf.mus:
        raise Unsupported("MUS (Compute's Sidplayer): нужен свой проигрыватель")
    if sf.play == 0:
        raise Unsupported("play = 0: мелодия ставит свое прерывание, нужно окружение RSID")
    if sf.cia_speed(song):
        raise Unsupported("play по таймеру CIA (многоскоростная мелодия): не поддержано")
    if sf.sid2:
        raise Unsupported("второй SID: у ЯЗС голосов не хватит")
    env = Env(sf)
    c = env.cpu
    c.sp = 0xFF
    env.frame = -1                     # записи init - кадр -1
    init_cyc = c.call(sf.init, song - 1, limit=FRAME * 1000)
    regs, cyc = [], []
    quiet = still = 0
    sounded = False
    prev = None
    stop = "время"
    for f in range(int(seconds * FPS)):
        env.frame = f
        c.sp = 0xFF
        c.cycles = (c.cycles // FRAME + 1) * FRAME     # play - с начала кадра
        cyc.append(c.call(sf.play, 0, limit=FRAME * 4))
        snap = bytes(env.sid[:25])
        regs.append(snap)
        still = still + 1 if snap == prev else 0
        prev = snap
        tail = int(2 * FPS)
        if still > still_s * FPS:
            del regs[f - still + tail:]
            del cyc[f - still + tail:]
            stop = "замерла"
            break
        if any(env.sid[4 + 7 * v] & 1 for v in range(3)):
            sounded, quiet = True, 0
        else:
            quiet += 1
        if sounded and quiet > quiet_s * FPS:
            stop = "тишина"
            break
    meta = {"song": song, "stop": stop, "init_cycles": init_cyc,
            "play_avg": int(sum(cyc) / len(cyc)) if cyc else 0, "play_max": max(cyc) if cyc else 0,
            "sid_reads": dict(env.reads), "cia_writes": env.cia_writes,
            "undoc": {"%02X" % k: v for k, v in c.undoc_used.items()}}
    return Dump(regs, env.ev, cyc, meta)


class Dump(object):
    """Регистры SID по кадрам и все записи в него; разбор на голоса и ноты"""

    def __init__(self, regs, events, cyc, meta):
        self.meta = meta
        self.frames = len(regs)
        self.regs = np.frombuffer(b"".join(regs), dtype=np.uint8).reshape(-1, 25) if regs else \
            np.zeros((0, 25), np.uint8)
        self.cyc = np.array(cyc, dtype=np.int32)
        ev = np.array(events, dtype=np.int32).reshape(-1, 3)
        self.ev_f, self.ev_r, self.ev_v = ev[:, 0], ev[:, 1], ev[:, 2]
        R = self.regs.astype(np.int32)
        self.freq = [R[:, 7 * v] | (R[:, 7 * v + 1] << 8) for v in range(3)]
        self.pw = [R[:, 7 * v + 2] | ((R[:, 7 * v + 3] & 15) << 8) for v in range(3)]
        self.ctrl = [self.regs[:, 7 * v + 4] for v in range(3)]
        self.ad = [self.regs[:, 7 * v + 5] for v in range(3)]
        self.sr = [self.regs[:, 7 * v + 6] for v in range(3)]
        self.fc = (R[:, 21] & 7) | (R[:, 22] << 3)
        self.res = self.regs[:, 23] >> 4
        self.route = self.regs[:, 23] & 15
        self.mode = (self.regs[:, 24] >> 4) & 7
        self.v3off = (self.regs[:, 24] >> 7) & 1
        self.vol = self.regs[:, 24] & 15
        self._edges()

    def _edges(self):
        """По порядку записей: фронты GATE 0->1 и 1->0 (их может быть и два за кадр),
        число записей каждого регистра по кадрам"""
        self.gate_on = [np.zeros(self.frames, bool) for _ in range(3)]
        self.gate_off = [np.zeros(self.frames, bool) for _ in range(3)]
        self.wcount = np.zeros((self.frames + 1, 25), np.int32)
        prev = [0, 0, 0]
        for f, r, v in zip(self.ev_f, self.ev_r, self.ev_v):
            fi = max(int(f), 0)
            if fi >= self.frames:
                continue
            if f >= 0:
                self.wcount[fi, r] += 1
            if r in (4, 11, 18):
                k = r // 7
                if (v & 1) and not (prev[k] & 1):
                    self.gate_on[k][fi] = True
                if not (v & 1) and (prev[k] & 1):
                    self.gate_off[k][fi] = True
                prev[k] = int(v)

    def notes(self, v):
        """Ноты голоса: (кадр начала, кадр снятия GATE или конца, кадр следующего начала)"""
        ons = list(np.nonzero(self.gate_on[v])[0])
        out = []
        for i, s in enumerate(ons):
            nxt = ons[i + 1] if i + 1 < len(ons) else self.frames
            g = s
            while g < nxt and (self.ctrl[v][g] & 1):
                g += 1
            out.append((int(s), int(g), int(nxt)))
        return out

    def print_frames(self, v, f0, n):
        """Покадровая распечатка голоса v (0-2)"""
        print("кадр  частота нота      PW  ctrl  AD SR  фильтр(срез,рез,гол,реж,гр) записи")
        for f in range(f0, min(f0 + n, self.frames)):
            fr = int(self.freq[v][f])
            m = midi(fr)
            mark = "+" if self.gate_on[v][f] else ("-" if self.gate_off[v][f] else " ")
            print("%5d%s %5d  %-4s%+5.0fc %4d   %02X  %02X %02X  %4d %X %X %X %2d  %s" % (
                f, mark, fr, note_name(m) if m else "-", ((m - round(m)) * 100) if m else 0,
                self.pw[v][f], self.ctrl[v][f], self.ad[v][f], self.sr[v][f], self.fc[f], self.res[f],
                self.route[f], self.mode[f], self.vol[f],
                "".join("%d" % min(9, c) for c in self.wcount[f, 7 * v:7 * v + 7])))
