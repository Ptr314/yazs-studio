# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
ЯЗС-СБИВКА: демо ударных. Шаффл-электро в духе синти-фанка начала 80-х,
ми минор, 116, около полутора минут. Музыка своя: ориентир - звучание
электро-фанка тех лет (драм-машина с хлопками, бас октавами, стаккато
синтезатора), мелодий оттуда нет.

Что показывает:
- **бочка на тоновом канале** (канал 5): НЧ с D3, удар D4 на 9 тиков, макрос
  высоты вниз на 22 полутона за 13 тиков (A3 -> ~62 Гц), первый тик на НЧ+СЧ -
  щелчок атаки. Ударный 6 освобождается под малый барабан и очереди;
- **томы на тоновых каналах** 2-3 (в духе электронных томов 80-х): высота вниз
  на 9 полутонов, каналы по очереди, чтобы удары не обрывали друг друга;
- **очереди («сбивка») на шумовых каналах**, как в «Сириусе» демо НКЛ на 6-7 с:
  удар в каждой строке, 42 мс. Строк на долю 12, скорость 4 тика: шаффл - 8 + 4
  строки, очередь - 12 ударов на долю. Ударные бьют раз в строку (тик 1), так
  что быстрее очередь не бывает;
- в очереди работают оба шумовых канала: ударный 6 (малый без D3) отбивает
  каждый удар, ударный 7 чередует $0B (11 кГц, D3) и $00 (7 кГц без D3). В модели
  eCat3 ударный 7 сбросом D4 не гасится, и ровная очередь на нем одном сливается
  в шипение (провал между ударами 3-5 дБ); с чередованием D3 провал ~10 дБ через
  удар. На записи «Сириуса» с живой платы шум перед каждым ударом обрывается;
- пинг-понг ударных 6 и 7 через строку, дробь малого, разгон очереди
  (промежутки 4-3-2-1 строки), бочка очередью на тоновом канале, бочка
  ударного 6 для сравнения.

Форма: вступление (ударные по одному) - грув с басом - тема А (синтезатор) -
тема Б (аккорды, «медь») - брейк ударных с подписями - тема А с эхом -
тема Б короче - сбивка всеми и последний удар.

Уровни: D3 у бочки, томов и ведущего голоса; бас и аккорды без D3. Бочка одна дает пик
~0.77. Малый - $06 без D3, на сильных долях вместе с хлопком ударного 7 ($08):
так доля ~0.78. Малый с D3 ($0E) вместе с бочкой и басом дает 0.95-0.99, в
очереди - 0.96.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose import Song, CMD_INSTR, CMD_OFF                 # noqa: E402
from instruments import HF, MF, LF, LOUD, HIT, HOLD          # noqa: E402
from common import chord, name, voicing, shuffle, check_harmony   # noqa: E402

RPB = 12                      # строк на долю: шаффл 8 + 4, очередь - строка
BAR = 4 * RPB

# Ударный 6: малый, томы, шумная «бочка» (D2 = 0 - высоту дергает шум)
D6 = {"s": 0x06, "S": 0x06, "g": 0x05, "n": 0x02, "t": 0x09, "u": 0x0B, "v": 0x0D,
      "k": 0x08}
# Ударный 7: хэт 11 кГц, 7 и 8 кГц без D3; с D3 - открытый хэт, хлопок, тарелка
D7 = {"h": 0x03, "x": 0x00, "z": 0x02, "H": 0x0B, "c": 0x08, "o": 0x0A}
# Тоновые ударные: знак -> (инструмент, нота)
KICK = {"k": ("kick", 45), "K": ("kick_s", 45)}
TOMS = {"1": ("tom", 52), "2": ("tom", 48), "3": ("tom", 45), "4": ("tom", 41),
        "5": ("tom", 38), "6": ("tom", 34)}

# --- ударные по тактам: знак - строка, '.' - пусто ---

KICK_4 = "k........... k........... k........... k..........."
KICK_A = "k........... ........k... k........... ............"
KICK_B = "k........... ........k... k.......k... ........k..."
KICK_C = "k.......k... ............ k...k....... ........k..."
NONE = "............ " * 4

SN_A = "............ s........... ............ s..........."
SN_G = "........g... s........... ....g....... s..........."   # призрачные - мимо бочки
SN_C = "............ s........... ........g... s.....g....."
HAT_0 = "h.......z... h.......z... h.......z... h.......z..."
HAT_A = "h.......z... c.......z... h.......z... c.......z..."
HAT_C = "h...z...z... c...z...z... h...z...z... c...c...z..."


def last(bar_text, beats, repl):
    """Заменить последние beats долей такта"""
    b = bar_text.split()
    return " ".join(b[:4 - beats] + repl.split())


# --- MML ---

def n(x, ln):
    return "o%d %s%s" % (x // 12, name(x), ln)


def root(sym, lo=23):
    """Нижняя нота баса: окно си1..ля-диез2"""
    pc = chord(sym)[2]
    return next(x for x in range(lo, lo + 12) if x % 12 == pc)


BASS_A = [0, 0, 12, 0, 0, 7, 12, 0]          # восьмые шаффла: ступени от основания
BASS_G = [0, None, 0, 12, 0, 7, 12, 0]


def bass_bar(sym, pat=BASS_A):
    """Такт баса восьмыми; «C D» - по полтакта"""
    out = []
    syms = sym.split()
    per = 8 // len(syms)
    for i, x in enumerate(syms):
        r = root(x)
        for d in pat[:per]:
            out.append("r8" if d is None else n(r + d, "8"))
    return " ".join(out) + " |"


def stab_bar(sym, which, rhythm, top=59):
    """Аккорд-стаб: rhythm - восьмые 'X' (удар) и '.' (пауза); 'C D' - по полтакта"""
    syms = sym.split()
    per = len(rhythm) // len(syms)
    out = []
    for i, c in enumerate(rhythm):
        x = syms[min(i // per, len(syms) - 1)]
        out.append(n(voicing(x, top, 2)[which], "8") if c == "X" else "r8")
    return " ".join(out) + " |"


THEME_A_H = ["Em", "Em", "C", "D", "Em", "Em", "C D", "B7"]
THEME_A = [
    "r8 o4 b8 o5 e8 o4 b8 o5 d8 e8 r8 g8",
    "^8 f#8 e8 d8 e4 r4",
    "r8 o4 g8 o5 c8 o4 g8 o5 c8 e8 r8 g8",
    "^8 a8 f#8 d8 e8 f#8 r4",
    "o4 e8 o5 e8 o4 e8 b8 o5 d8 e8 o4 b8 o5 e8",
    "o5 g8 f#8 e8 d8 ^8 o4 b8 o5 d4",
    "o5 c4 o4 b8 a8 o5 d4 c8 o4 b8",
    "o4 a8 b8 o5 d#8 f#8 ^4 r4",
]
THEME_B_H = ["Am", "Am", "Em", "Em", "Am", "Am", "C", "B7"]
BRASS_B = [
    "o4 a8 o5 c8 e8 a8 ^8 g8 e8 c8",
    "o5 d8 c8 o4 a4 r4 r8 e8",
    "o4 g8 o5 c8 e8 g8 ^8 e8 d8 c8",
    "o4 b8 o5 d#8 f#8 a8 ^4 r4",
]
CALL = "XX.X.XX."           # аккорды: удар-удар, синкопы
CALL2 = "X......."
SKANK = ".X.X.X.X"          # на короткие восьмые шаффла


def bars(lst):
    return " | ".join(lst) + " |"


def rest(k):
    return "r1 | " * k


def song():
    s = Song("ЯЗС-СБИВКА", "ДЕМО УДАРНЫХ: ШАФФЛ-ЭЛЕКТРО", bpm=116, rows_per_beat=RPB,
             beats_per_bar=4, frame_bars=1)
    I = s.instrument
    # Бочка: щелчок НЧ+СЧ в первом тике, D4 9 тиков, высота вниз на 22 полутона
    kick_pitch = [-64, -56, -48, -40, -32, -28, -24, -20, -16, -12, -8, -4, 0]
    I("kick", "БОЧКА", [HIT | LOUD | LF | MF] + [HIT | LOUD | LF] * 8 + [LOUD | LF],
      pitch=kick_pitch, meter=(15, 0, 14))
    I("kick_s", "БОЧКА", [HIT | LF | MF] + [HIT | LF] * 6 + [LF], pitch=kick_pitch,
      meter=(10, 0, 14))
    # Том: высота вниз на 9 полутонов за 18 тиков, атака на НЧ+СЧ
    I("tom", "ТОМ", [HIT | LOUD | LF | MF] * 3 + [HIT | LOUD | LF] * 14 + [LOUD | LF],
      pitch=[-12] * 6 + [-8] * 6 + [-4] * 6 + [0], meter=(14, 0, 8))
    # Бас без D3: с D3 бас и бочка вместе дают пик 0.82, без него - 0.56
    I("bass", "СИНТ-БАС", [HIT | LF | MF] * 2 + [HIT | LF], meter=(12, 0, 8))
    I("lead", "СИНТЕЗ.", [HOLD | HIT | LOUD | MF | HF], vib=(24, 5, 2), meter=(15, 13, 2))
    I("echo", "ЭХО", [HOLD | HIT | MF], vib=(24, 5, 2), meter=(9, 7, 3))
    I("stab", "АККОРД", [HIT | MF | HF, HIT | MF], meter=(10, 0, 10))
    I("brass", "МЕДЬ", [HOLD | HIT | LOUD | LF | MF | HF] * 2 + [HOLD | HIT | LOUD | LF | MF],
      pitch=[-8, 2, 2, 2, 2, 0], vib=(20, 4, 2), meter=(15, 13, 2))
    I("hit", "АККОРД", [HOLD | HIT | LF | MF], meter=(11, 9, 2))

    row = [0]                        # начало текущей части
    hm = []                          # гармония: (строка, аккорд) - для check_harmony
    caps = []

    # --- ударные: сетка ---
    def hits(ch, start, text, kit):
        r = start
        for c in text:
            if c in " |":
                continue
            if c != ".":
                if ch < 5:
                    ins, note = kit[c]
                    s.put(ch, r, (CMD_INSTR, s.inames[ins]))
                    s.put(ch, r, (note,))
                else:
                    s.put(ch, r, (kit[c],))
            r += 1
        return r - start

    def drums(kick, d6, d7, toms=None, at=None):
        """Такт ударных: бочка (канал 5), ударные 6 и 7, томы (каналы 2-3 по очереди)"""
        r0 = row[0] if at is None else at
        for ch, txt, kit in ((4, kick, KICK), (5, d6, D6), (6, d7, D7)):
            assert hits(ch, r0, txt, kit) == BAR, txt
        if toms:
            k = 0
            r = r0
            for c in toms:
                if c in " |":
                    continue
                if c != ".":
                    ch = 1 + k % 2
                    s.put(ch, r, (CMD_INSTR, s.inames["tom"]))
                    s.put(ch, r, (TOMS[c][1],))
                    # отпустить после спада: звук тот же, check_harmony не считает
                    # том звучащим до следующей ноты канала
                    s.put(ch, r + 5, (CMD_OFF,))
                    k += 1
                r += 1
            assert r - r0 == BAR, toms
        return r0 + BAR

    def voice(ch, text, at=None, swing=True):
        r0 = row[0] if at is None else at
        end = s.voice(ch, shuffle(text, rpb=RPB) if swing else text, start=r0)
        return end

    def caption(bar_off, text):
        caps.append((row[0] + bar_off * BAR + 2, text))

    def harmony(lst):
        for i, sym in enumerate(lst):
            for j, x in enumerate(sym.split()):
                hm.append((row[0] + i * BAR + j * BAR // len(sym.split()), x))

    def next_part(nbars):
        row[0] += nbars * BAR

    # Очереди
    sirius6 = "......SSSSSS"             # последняя доля: от слабой половины к сильной
    sirius7 = "h.....HxHxHx"            # 11 кГц с D3 и 7 кГц без - через удар
    pp6 = "S.S.S.S.S.S. S.S.S.S.S.S."   # пинг-понг через строку
    pp7 = ".h.h.h.h.h.h .x.x.x.x.x.x"
    roll6 = "S.S.S.S.S.S. SSSSSSSSSSSS"  # дробь
    accel = [0, 4, 8, 11, 14, 16, 18, 20, 21, 22, 23]   # разгон: 4-4-3-3-2-2-2-1-1-1-1

    def acc6():
        return "".join("S" if r in accel else "." for r in range(24))

    def acc7():
        out = []
        for r in range(24):
            out.append(("H" if accel.index(r) % 2 == 0 else "x") if r in accel else ".")
        return "".join(out)

    # ================= вступление: ударные по одному =================
    caption(0, "БОЧКА - ТОНОВЫЙ КАНАЛ 5: D4 И ВЫСОТА ВНИЗ НА 22 ПОЛУТОНА")
    drums(KICK_4, NONE, NONE, at=row[0])
    caption(1, "ХЭТ - УДАРНЫЙ 7 (ШУМ 7-11 КГЦ), ШАФФЛ 8+4 СТРОКИ")
    drums(KICK_A, NONE, HAT_0, at=row[0] + BAR)
    caption(2, "МАЛЫЙ - УДАРНЫЙ 6, ХЛОПОК - УДАРНЫЙ 7 С D3")
    drums(KICK_A, SN_A, HAT_A, at=row[0] + 2 * BAR)
    caption(3, "ОЧЕРЕДЬ: УДАР В КАЖДОЙ СТРОКЕ (42 МС), ОБА ШУМОВЫХ КАНАЛА")
    drums(KICK_A, last(SN_A, 1, sirius6), last(HAT_A, 1, sirius7), at=row[0] + 3 * BAR)
    for c in range(4):
        s.put(c, row[0], (CMD_OFF,))
    next_part(4)

    # ================= грув: бас =================
    harmony(["Em"] * 4)
    caption(0, "БАС ОКТАВАМИ НА ШАФФЛЕ, БОЧКА НА 1, 2+ И 3")
    voice(3, "@bass q6 " + " ".join(bass_bar("Em", BASS_G) for _ in range(4)))
    for b in range(4):
        d7 = HAT_A if b else HAT_A.replace("h", "o", 1)
        if b == 3:
            caption(3, "ПИНГ-ПОНГ: УДАРНЫЕ 6 И 7 ЧЕРЕЗ СТРОКУ")
            drums(KICK_A, last(SN_G, 2, pp6), last(d7, 2, pp7), at=row[0] + b * BAR)
        else:
            drums(KICK_A, SN_G, d7, at=row[0] + b * BAR)
    next_part(4)

    # ================= тема А =================
    def theme_a(with_echo=False):
        harmony(THEME_A_H)
        a0 = row[0]
        voice(0, "@lead q7 " + bars(THEME_A))
        voice(3, "@bass q6 " + " ".join(bass_bar(x) for x in THEME_A_H))
        if with_echo:
            # эхо - голос на 8 строк позже, без D3; томы такта 8 - на его каналах
            src = s.rows[0]
            for r in range(a0, a0 + 7 * BAR + 16):
                for c in src.get(r, []):
                    s.put(1, r + 8, (CMD_INSTR, s.inames["echo"]) if c[0] == CMD_INSTR else c)
            s.put(1, a0 + 7 * BAR + 24, (CMD_OFF,))
            voice(2, "@stab " + " ".join(stab_bar(x, 1, SKANK) for x in THEME_A_H[:7])
                  + " r1 |")
        else:
            voice(1, "@stab " + " ".join(stab_bar(x, 0, SKANK) for x in THEME_A_H[:7])
                  + " r1 |")
            voice(2, "@stab " + " ".join(stab_bar(x, 1, SKANK) for x in THEME_A_H[:7])
                  + " r1 |")
        for b in range(8):
            r = a0 + b * BAR
            d7 = HAT_A.replace("h", "o", 1) if b == 0 else HAT_A
            if b == 3:
                drums(KICK_B, last(SN_G, 1, sirius6), last(d7, 1, sirius7), at=r)
            elif b == 7:
                drums(last(KICK_B, 2, "k........... ............"),
                      last(SN_G, 2, "............ ............"),
                      last(d7, 2, "h........... h.....HxHxHx"),
                      toms="............ ............ 1...2...3... 4...5...6...", at=r)
            else:
                drums(KICK_B, SN_G, d7, at=r)

    caption(0, "ТЕМА: СИНТЕЗАТОР СО СТАККАТО, АККОРДЫ НА КОРОТКИЕ ВОСЬМЫЕ")
    caption(7, "ТОМЫ НА ТОНОВЫХ КАНАЛАХ 2-3: ВЫСОТА ВНИЗ НА 9 ПОЛУТОНОВ")
    theme_a()
    next_part(8)

    # ================= тема Б: аккорды, медь =================
    def theme_b(nbars=8):
        harmony(THEME_B_H[:nbars])
        b0 = row[0]
        # такты 1-4: аккорды - синкопы, через такт - один удар
        voice(1, "@stab " + " ".join(stab_bar(x, 0, CALL if i % 2 == 0 else CALL2)
                                     for i, x in enumerate(THEME_B_H[:4])))
        voice(2, "@stab " + " ".join(stab_bar(x, 1, CALL if i % 2 == 0 else CALL2)
                                     for i, x in enumerate(THEME_B_H[:4])))
        if nbars > 4:
            # такты 5-8: медь, аккорды на короткие восьмые
            voice(0, "@brass " + bars(BRASS_B), at=b0 + 4 * BAR)
            voice(1, "@stab " + " ".join(stab_bar(x, 0, SKANK) for x in THEME_B_H[4:7])
                  + " r1 |", at=b0 + 4 * BAR)
            voice(2, "@stab " + " ".join(stab_bar(x, 1, SKANK) for x in THEME_B_H[4:7])
                  + " r1 |", at=b0 + 4 * BAR)
        voice(3, "@bass q6 " + " ".join(bass_bar(x) for x in THEME_B_H[:nbars]))
        for b in range(nbars):
            r = b0 + b * BAR
            d7 = HAT_C.replace("h", "o", 1) if b == 0 else HAT_C
            if b == 3:
                # бочка очередью на последней доле
                drums(last(KICK_C, 1, "k.k.k.k.k.k."), SN_C, d7, at=r)
            elif b == 7:
                drums(last(KICK_C, 2, "k........... ............"),
                      last(SN_C, 2, acc6()), last(d7, 2, acc7()), at=r)
            else:
                drums(KICK_C, SN_C, d7, at=r)

    caption(0, "АККОРДЫ НА СИНКОПАХ, ХЭТ ТРИОЛЯМИ, ДВА ХЛОПКА НА 4")
    caption(3, "БОЧКА ОЧЕРЕДЬЮ: ТОНОВЫЙ КАНАЛ, УДАР ЧЕРЕЗ 2 СТРОКИ")
    caption(4, "МЕДЬ: ПОДЪЕЗД К НОТЕ, ПЕРВЫЕ ТИКИ НА ВСЕХ ПОЛОСАХ")
    caption(7, "РАЗГОН ОЧЕРЕДИ: ПРОМЕЖУТКИ 4-3-2-1 СТРОКИ")
    theme_b()
    next_part(8)

    # ================= брейк ударных =================
    harmony(["Em"] * 8)
    k0 = row[0]
    # бас молчит в такте бочки ударного 6 (сравнение) и в двух последних
    voice(3, "@bass q6 " + bass_bar("Em", BASS_G) + " r1 | "
          + " ".join(bass_bar("Em", BASS_G) for _ in range(4)) + " r1 | r1 |")
    for c in (0, 1, 2):
        s.put(c, k0, (CMD_OFF,))
    caption(0, "БРЕЙК. БОЧКА НА ТОНОВОМ КАНАЛЕ: ~62 ГЦ, РАЗВЕРТКА ВНИЗ")
    drums(KICK_A, SN_A, HAT_A.replace("h", "o", 1), at=k0)
    caption(1, "ДЛЯ СРАВНЕНИЯ - БОЧКА УДАРНОГО 6 ($08): ~76 ГЦ БЕЗ РАЗВЕРТКИ")
    hits(5, k0 + BAR, "k........... s.......k... k........... s...........", D6)
    hits(4, k0 + BAR, NONE, KICK)
    hits(6, k0 + BAR, HAT_A, D7)
    caption(2, "ТОМЫ: ТОНОВЫЕ КАНАЛЫ ПО ОЧЕРЕДИ И ТОМЫ УДАРНОГО 6")
    drums("k........... ............ k........... ............",
          "............ ....v...u... ............ ....u...t...",
          "h.......z... c........... h.......z... c...........",
          toms="....1...2... ............ ....3...4... ............", at=k0 + 2 * BAR)
    caption(3, "ПИНГ-ПОНГ: УДАРНЫЕ 6 И 7 ЧЕРЕЗ СТРОКУ")
    drums(KICK_A, last(SN_A, 2, pp6), last(HAT_A, 2, pp7), at=k0 + 3 * BAR)
    caption(4, "ДРОБЬ МАЛОГО: УДАР В КАЖДОЙ СТРОКЕ, БЕЗ D3")
    drums(KICK_A, last(SN_A, 2, roll6), last(HAT_A, 2, "h.......z... h.......z..."),
          at=k0 + 4 * BAR)
    caption(5, "БОЧКА ОЧЕРЕДЬЮ: ЧЕРЕЗ 2 СТРОКИ, ПОТОМ В КАЖДОЙ")
    drums("k........... ........k... k.k.k.k.k.k. kkkkkkkkkkkk", SN_A,
          "o.......z... c.......z... h.......z... h.......z...", at=k0 + 5 * BAR)
    caption(6, "РАЗГОН: ПРОМЕЖУТКИ 4-3-2-1 СТРОКИ НА ОБОИХ ШУМОВЫХ")
    drums("k........... ............ ............ ............",
          "............ ............ " + acc6()[:12] + " " + acc6()[12:],
          "o........... ............ " + acc7()[:12] + " " + acc7()[12:], at=k0 + 6 * BAR)
    caption(7, "СБИВКА ВСЕМИ: ТОМЫ НА ТОНАХ, ОЧЕРЕДИ НА ШУМОВЫХ")
    drums("k........... ............ ............ k.k.k.k.....",
          "............ v...u...t... S.S.S.S.S.S. SSSSSSSSSSSS",
          "o........... ............ .h.h.h.h.h.h HxHxHxHxHxHx",
          toms="1...2...3... ............ ............ ........4.5.", at=k0 + 7 * BAR)
    next_part(8)

    # ================= тема А с эхом =================
    caption(0, "ЭХО: ГОЛОС НА 8 СТРОК ПОЗЖЕ, БЕЗ D3")
    caption(7, "ТОМЫ НА ТОНАХ, ОЧЕРЕДЬ НА ШУМОВЫХ")
    theme_a(with_echo=True)
    next_part(8)

    # ================= тема Б, короче =================
    caption(0, "АККОРДЫ НА СИНКОПАХ")
    theme_b(4)
    next_part(4)

    # ================= концовка =================
    e0 = row[0]
    harmony(["Em", "Em"])
    caption(0, "СБИВКА ВСЕМИ И ПОСЛЕДНИЙ УДАР")
    voice(3, "@bass q6 " + bass_bar("Em", BASS_G) + " o2 e4 r4 r2 |")
    for c in (0, 1, 2):
        s.put(c, e0, (CMD_OFF,))
    drums("k........... ........k... ............ k.k.k.k.k.k.",
          "............ s........... S.S.S.S.S.S. SSSSSSSSSSSS",
          "o.......z... c........... .h.h.h.h.h.h HxHxHxHxHxHx",
          toms="............ ........1.2. ...3...4.... ............", at=e0)
    # последний удар: бочка, тарелка, аккорд ми минор
    voice(0, "@hit o4 b2 r2 |", at=e0 + BAR, swing=False)
    voice(1, "@hit o4 g2 r2 |", at=e0 + BAR, swing=False)
    voice(2, "@hit o4 e2 r2 |", at=e0 + BAR, swing=False)
    drums("k........... ............ ............ ............",
          "s........... ............ ............ ............",
          "o........... ............ ............ ............", at=e0 + BAR)
    next_part(2)

    total = row[0]
    s.end_row = total
    for r, t in caps:
        s.text(r, t)
    s.harmony = hm
    return s


if __name__ == "__main__":
    s = song()
    s.build()
    print(s.stats)
    for t in s.texts:
        assert len(t) <= 64
    print("вне аккорда:", check_harmony(s, s.harmony, channels=(0, 1, 2, 3), every=RPB,
                                        label="сбивка"))
