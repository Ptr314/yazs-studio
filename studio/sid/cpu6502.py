# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""NMOS 6502 для прогона музыкальных драйверов C64 (проверка - test_cpu.py).

Документированные команды, десятичный режим NMOS (N, V, Z как у 6502), ходовые
недокументированные (SLO RLA SRE RRA SAX LAX DCP ISC ANC ALR ARR SBX LXA ANE LAS
SHA SHX SHY TAS, NOP-ы); JAM останавливает. Такты - по таблице, с +1 за пересечение
страницы у чтений и переходов: для оценки стоимости play, не для точной эмуляции.

Чтение и запись в $D000-$DFFF идут через io_read/io_write, если они заданы и
io_visible() истинно; остальное - ОЗУ.
"""


class Halt(Exception):
    pass


class Timeout(Exception):
    pass


# (код, мнемоника, режим, такты)
OPS = """
69 ADC imm 2|65 ADC zp 3|75 ADC zpx 4|6D ADC abs 4|7D ADC absx 4|79 ADC absy 4|61 ADC indx 6|71 ADC indy 5
29 AND imm 2|25 AND zp 3|35 AND zpx 4|2D AND abs 4|3D AND absx 4|39 AND absy 4|21 AND indx 6|31 AND indy 5
0A ASL acc 2|06 ASL zp 5|16 ASL zpx 6|0E ASL abs 6|1E ASL absx 7
90 BCC rel 2|B0 BCS rel 2|F0 BEQ rel 2|30 BMI rel 2|D0 BNE rel 2|10 BPL rel 2|50 BVC rel 2|70 BVS rel 2
24 BIT zp 3|2C BIT abs 4|00 BRK imp 7
18 CLC imp 2|D8 CLD imp 2|58 CLI imp 2|B8 CLV imp 2
C9 CMP imm 2|C5 CMP zp 3|D5 CMP zpx 4|CD CMP abs 4|DD CMP absx 4|D9 CMP absy 4|C1 CMP indx 6|D1 CMP indy 5
E0 CPX imm 2|E4 CPX zp 3|EC CPX abs 4|C0 CPY imm 2|C4 CPY zp 3|CC CPY abs 4
C6 DEC zp 5|D6 DEC zpx 6|CE DEC abs 6|DE DEC absx 7|CA DEX imp 2|88 DEY imp 2
49 EOR imm 2|45 EOR zp 3|55 EOR zpx 4|4D EOR abs 4|5D EOR absx 4|59 EOR absy 4|41 EOR indx 6|51 EOR indy 5
E6 INC zp 5|F6 INC zpx 6|EE INC abs 6|FE INC absx 7|E8 INX imp 2|C8 INY imp 2
4C JMP abs 3|6C JMP ind 5|20 JSR abs 6
A9 LDA imm 2|A5 LDA zp 3|B5 LDA zpx 4|AD LDA abs 4|BD LDA absx 4|B9 LDA absy 4|A1 LDA indx 6|B1 LDA indy 5
A2 LDX imm 2|A6 LDX zp 3|B6 LDX zpy 4|AE LDX abs 4|BE LDX absy 4
A0 LDY imm 2|A4 LDY zp 3|B4 LDY zpx 4|AC LDY abs 4|BC LDY absx 4
4A LSR acc 2|46 LSR zp 5|56 LSR zpx 6|4E LSR abs 6|5E LSR absx 7
EA NOP imp 2
09 ORA imm 2|05 ORA zp 3|15 ORA zpx 4|0D ORA abs 4|1D ORA absx 4|19 ORA absy 4|01 ORA indx 6|11 ORA indy 5
48 PHA imp 3|08 PHP imp 3|68 PLA imp 4|28 PLP imp 4
2A ROL acc 2|26 ROL zp 5|36 ROL zpx 6|2E ROL abs 6|3E ROL absx 7
6A ROR acc 2|66 ROR zp 5|76 ROR zpx 6|6E ROR abs 6|7E ROR absx 7
40 RTI imp 6|60 RTS imp 6
E9 SBC imm 2|E5 SBC zp 3|F5 SBC zpx 4|ED SBC abs 4|FD SBC absx 4|F9 SBC absy 4|E1 SBC indx 6|F1 SBC indy 5
38 SEC imp 2|F8 SED imp 2|78 SEI imp 2
85 STA zp 3|95 STA zpx 4|8D STA abs 4|9D STA absx 5|99 STA absy 5|81 STA indx 6|91 STA indy 6
86 STX zp 3|96 STX zpy 4|8E STX abs 4|84 STY zp 3|94 STY zpx 4|8C STY abs 4
AA TAX imp 2|A8 TAY imp 2|BA TSX imp 2|8A TXA imp 2|9A TXS imp 2|98 TYA imp 2
07 SLO zp 5|17 SLO zpx 6|03 SLO indx 8|13 SLO indy 8|0F SLO abs 6|1F SLO absx 7|1B SLO absy 7
27 RLA zp 5|37 RLA zpx 6|23 RLA indx 8|33 RLA indy 8|2F RLA abs 6|3F RLA absx 7|3B RLA absy 7
47 SRE zp 5|57 SRE zpx 6|43 SRE indx 8|53 SRE indy 8|4F SRE abs 6|5F SRE absx 7|5B SRE absy 7
67 RRA zp 5|77 RRA zpx 6|63 RRA indx 8|73 RRA indy 8|6F RRA abs 6|7F RRA absx 7|7B RRA absy 7
87 SAX zp 3|97 SAX zpy 4|83 SAX indx 6|8F SAX abs 4
A7 LAX zp 3|B7 LAX zpy 4|A3 LAX indx 6|B3 LAX indy 5|AF LAX abs 4|BF LAX absy 4|AB LXA imm 2
C7 DCP zp 5|D7 DCP zpx 6|C3 DCP indx 8|D3 DCP indy 8|CF DCP abs 6|DF DCP absx 7|DB DCP absy 7
E7 ISC zp 5|F7 ISC zpx 6|E3 ISC indx 8|F3 ISC indy 8|EF ISC abs 6|FF ISC absx 7|FB ISC absy 7
0B ANC imm 2|2B ANC imm 2|4B ALR imm 2|6B ARR imm 2|CB SBX imm 2|EB SBC imm 2|8B ANE imm 2
BB LAS absy 4|9F SHA absy 5|93 SHA indy 6|9E SHX absy 5|9C SHY absx 5|9B TAS absy 5
1A NOP imp 2|3A NOP imp 2|5A NOP imp 2|7A NOP imp 2|DA NOP imp 2|FA NOP imp 2
80 NOP imm 2|82 NOP imm 2|89 NOP imm 2|C2 NOP imm 2|E2 NOP imm 2
04 NOP zp 3|44 NOP zp 3|64 NOP zp 3|14 NOP zpx 4|34 NOP zpx 4|54 NOP zpx 4|74 NOP zpx 4|D4 NOP zpx 4|F4 NOP zpx 4
0C NOP abs 4|1C NOP absx 4|3C NOP absx 4|5C NOP absx 4|7C NOP absx 4|DC NOP absx 4|FC NOP absx 4
02 JAM imp 2|12 JAM imp 2|22 JAM imp 2|32 JAM imp 2|42 JAM imp 2|52 JAM imp 2|62 JAM imp 2|72 JAM imp 2
92 JAM imp 2|B2 JAM imp 2|D2 JAM imp 2|F2 JAM imp 2
"""

# Чтения, которым пересечение страницы стоит такт
READS = {"ADC", "AND", "CMP", "EOR", "LDA", "LDX", "LDY", "ORA", "SBC", "LAX", "NOP", "LAS"}
UNDOC = {"SLO", "RLA", "SRE", "RRA", "SAX", "LAX", "LXA", "DCP", "ISC", "ANC", "ALR", "ARR",
         "SBX", "ANE", "LAS", "SHA", "SHX", "SHY", "TAS", "JAM"}


class CPU6502(object):
    def __init__(self, mem=None):
        self.m = mem if mem is not None else bytearray(65536)
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.pc = 0
        self.c = self.z = self.d = self.v = self.n = 0
        self.i = 1
        self.cycles = 0
        self.io_read = None
        self.io_write = None
        self.io_visible = lambda: True
        self.undoc_used = {}
        self.cyc = [2] * 256
        self.table = [None] * 256
        self.names = ["???"] * 256
        for item in OPS.replace("\n", "|").split("|"):
            item = item.strip()
            if not item:
                continue
            code, mn, mode, cyc = item.split()
            code = int(code, 16)
            self.cyc[code] = int(cyc)
            self.names[code] = mn
            self.table[code] = self._make(mn, mode, code)
        assert all(t is not None for t in self.table), [i for i, t in enumerate(self.table) if t is None]

    # --- память ---

    def rd(self, a):
        if 0xD000 <= a <= 0xDFFF and self.io_read is not None and self.io_visible():
            return self.io_read(a)
        return self.m[a]

    def wr(self, a, v):
        if 0xD000 <= a <= 0xDFFF and self.io_write is not None and self.io_visible():
            self.io_write(a, v)
            return
        self.m[a] = v

    def push(self, v):
        self.m[0x100 + self.sp] = v
        self.sp = (self.sp - 1) & 0xFF

    def pull(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.m[0x100 + self.sp]

    def get_p(self, b=1):
        return (self.n << 7) | (self.v << 6) | 0x20 | (b << 4) | (self.d << 3) | (self.i << 2) | \
            (self.z << 1) | self.c

    def set_p(self, p):
        self.n = (p >> 7) & 1
        self.v = (p >> 6) & 1
        self.d = (p >> 3) & 1
        self.i = (p >> 2) & 1
        self.z = (p >> 1) & 1
        self.c = p & 1

    # --- режимы адресации: возвращают адрес ---

    def am_imm(self):
        a = self.pc
        self.pc = (a + 1) & 0xFFFF
        return a

    def am_zp(self):
        a = self.m[self.pc]
        self.pc = (self.pc + 1) & 0xFFFF
        return a

    def am_zpx(self):
        a = (self.m[self.pc] + self.x) & 0xFF
        self.pc = (self.pc + 1) & 0xFFFF
        return a

    def am_zpy(self):
        a = (self.m[self.pc] + self.y) & 0xFF
        self.pc = (self.pc + 1) & 0xFFFF
        return a

    def am_abs(self):
        m, pc = self.m, self.pc
        self.pc = (pc + 2) & 0xFFFF
        return m[pc] | (m[(pc + 1) & 0xFFFF] << 8)

    def _absi(self, i, rd):
        m, pc = self.m, self.pc
        self.pc = (pc + 2) & 0xFFFF
        base = m[pc] | (m[(pc + 1) & 0xFFFF] << 8)
        a = (base + i) & 0xFFFF
        if rd and (a ^ base) & 0xFF00:
            self.cycles += 1
        return a

    def am_absx(self):
        return self._absi(self.x, False)

    def am_absy(self):
        return self._absi(self.y, False)

    def am_absxr(self):
        return self._absi(self.x, True)

    def am_absyr(self):
        return self._absi(self.y, True)

    def am_indx(self):
        m = self.m
        z = (m[self.pc] + self.x) & 0xFF
        self.pc = (self.pc + 1) & 0xFFFF
        return m[z] | (m[(z + 1) & 0xFF] << 8)

    def _indy(self, rd):
        m = self.m
        z = m[self.pc]
        self.pc = (self.pc + 1) & 0xFFFF
        base = m[z] | (m[(z + 1) & 0xFF] << 8)
        a = (base + self.y) & 0xFFFF
        if rd and (a ^ base) & 0xFF00:
            self.cycles += 1
        return a

    def am_indy(self):
        return self._indy(False)

    def am_indyr(self):
        return self._indy(True)

    def am_ind(self):
        m, pc = self.m, self.pc
        p = m[pc] | (m[(pc + 1) & 0xFFFF] << 8)
        self.pc = (pc + 2) & 0xFFFF
        # ошибка NMOS: старший байт берется из той же страницы
        return m[p] | (m[(p & 0xFF00) | ((p + 1) & 0xFF)] << 8)

    # --- построение таблицы ---

    def _make(self, mn, mode, code):
        if mode in ("absx", "absy", "indy") and mn in READS:
            mode += "r"
        if mn in UNDOC:
            count = self.undoc_used

            def mark(f, code=code):
                def g(*a):
                    count[code] = count.get(code, 0) + 1
                    return f(*a)
                return g
        else:
            def mark(f):
                return f
        if mode == "rel":
            flag, val = {"BCC": ("c", 0), "BCS": ("c", 1), "BEQ": ("z", 1), "BNE": ("z", 0),
                         "BMI": ("n", 1), "BPL": ("n", 0), "BVC": ("v", 0), "BVS": ("v", 1)}[mn]

            def br():
                off = self.m[self.pc]
                pc = (self.pc + 1) & 0xFFFF
                if getattr(self, flag) == val:
                    t = (pc + (off - 256 if off & 0x80 else off)) & 0xFFFF
                    self.cycles += 2 if (t ^ pc) & 0xFF00 else 1
                    pc = t
                self.pc = pc
            return br
        if mode == "imp":
            return mark(getattr(self, "op_" + mn.lower()))
        if mode == "acc":
            return getattr(self, "op_" + mn.lower() + "_a")
        am = getattr(self, "am_" + mode)
        fn = getattr(self, "op_" + mn.lower())
        if mn == "JMP":
            def jmp():
                self.pc = am()
            return jmp
        if mn == "JSR":
            def jsr():
                t = am()
                r = (self.pc - 1) & 0xFFFF
                self.push(r >> 8)
                self.push(r & 0xFF)
                self.pc = t
            return jsr
        return mark(lambda: fn(am()))

    # --- выполнение ---

    def step(self):
        op = self.m[self.pc]
        self.pc = (self.pc + 1) & 0xFFFF
        self.cycles += self.cyc[op]
        self.table[op]()

    def call(self, addr, a=0, limit=2000000):
        """JSR addr с A = a; вернуться, когда RTS дойдет до верхнего уровня"""
        self.a = a & 0xFF
        self.x = self.y = 0
        self.push(0xFF)              # возврат в $0000: туда код C64 не попадает
        self.push(0xFF)
        self.pc = addr
        start = self.cycles
        m, table, cyc = self.m, self.table, self.cyc
        while self.pc != 0:
            op = m[self.pc]
            self.pc = (self.pc + 1) & 0xFFFF
            self.cycles += cyc[op]
            table[op]()
            if self.cycles - start > limit:
                raise Timeout("$%04X: %d тактов" % (addr, limit))
        return self.cycles - start

    # --- флаги ---

    def nz(self, v):
        self.z = 1 if v == 0 else 0
        self.n = v >> 7
        return v

    # --- команды: загрузка, запись, пересылки ---

    def op_lda(self, a):
        self.a = self.nz(self.rd(a))

    def op_ldx(self, a):
        self.x = self.nz(self.rd(a))

    def op_ldy(self, a):
        self.y = self.nz(self.rd(a))

    def op_sta(self, a):
        self.wr(a, self.a)

    def op_stx(self, a):
        self.wr(a, self.x)

    def op_sty(self, a):
        self.wr(a, self.y)

    def op_tax(self):
        self.x = self.nz(self.a)

    def op_tay(self):
        self.y = self.nz(self.a)

    def op_txa(self):
        self.a = self.nz(self.x)

    def op_tya(self):
        self.a = self.nz(self.y)

    def op_tsx(self):
        self.x = self.nz(self.sp)

    def op_txs(self):
        self.sp = self.x

    def op_pha(self):
        self.push(self.a)

    def op_php(self):
        self.push(self.get_p(1))

    def op_pla(self):
        self.a = self.nz(self.pull())

    def op_plp(self):
        self.set_p(self.pull())

    # --- арифметика ---

    def adc(self, m):
        a, c = self.a, self.c
        if self.d:
            al = (a & 0x0F) + (m & 0x0F) + c
            if al >= 0x0A:
                al = ((al + 0x06) & 0x0F) + 0x10
            s = (a & 0xF0) + (m & 0xF0) + al
            sa = (a & 0xF0) - 0x100 if a & 0x80 else (a & 0xF0)
            sm = (m & 0xF0) - 0x100 if m & 0x80 else (m & 0xF0)
            sv = sa + sm + al
            self.n = 1 if sv & 0x80 else 0
            self.v = 1 if sv < -128 or sv > 127 else 0
            self.z = 1 if (a + m + c) & 0xFF == 0 else 0
            if s >= 0xA0:
                s += 0x60
            self.c = 1 if s >= 0x100 else 0
            self.a = s & 0xFF
        else:
            s = a + m + c
            self.v = 1 if (~(a ^ m) & (a ^ s) & 0x80) else 0
            self.c = s >> 8
            self.a = self.nz(s & 0xFF)

    def sbc(self, m):
        a, c = self.a, self.c
        s = a - m - (1 - c)
        self.v = 1 if ((a ^ m) & (a ^ s) & 0x80) else 0
        self.c = 1 if s >= 0 else 0
        self.nz(s & 0xFF)
        if self.d:
            al = (a & 0x0F) - (m & 0x0F) + c - 1
            if al < 0:
                al = ((al - 0x06) & 0x0F) - 0x10
            r = (a & 0xF0) - (m & 0xF0) + al
            if r < 0:
                r -= 0x60
            self.a = r & 0xFF
        else:
            self.a = s & 0xFF

    def cmp(self, r, m):
        t = r - m
        self.c = 1 if t >= 0 else 0
        self.nz(t & 0xFF)

    def op_adc(self, a):
        self.adc(self.rd(a))

    def op_sbc(self, a):
        self.sbc(self.rd(a))

    def op_cmp(self, a):
        self.cmp(self.a, self.rd(a))

    def op_cpx(self, a):
        self.cmp(self.x, self.rd(a))

    def op_cpy(self, a):
        self.cmp(self.y, self.rd(a))

    def op_and(self, a):
        self.a = self.nz(self.a & self.rd(a))

    def op_ora(self, a):
        self.a = self.nz(self.a | self.rd(a))

    def op_eor(self, a):
        self.a = self.nz(self.a ^ self.rd(a))

    def op_bit(self, a):
        v = self.rd(a)
        self.z = 1 if self.a & v == 0 else 0
        self.n = v >> 7
        self.v = (v >> 6) & 1

    def op_inc(self, a):
        self.wr(a, self.nz((self.rd(a) + 1) & 0xFF))

    def op_dec(self, a):
        self.wr(a, self.nz((self.rd(a) - 1) & 0xFF))

    def op_inx(self):
        self.x = self.nz((self.x + 1) & 0xFF)

    def op_iny(self):
        self.y = self.nz((self.y + 1) & 0xFF)

    def op_dex(self):
        self.x = self.nz((self.x - 1) & 0xFF)

    def op_dey(self):
        self.y = self.nz((self.y - 1) & 0xFF)

    # --- сдвиги ---

    def asl(self, v):
        self.c = v >> 7
        return self.nz((v << 1) & 0xFF)

    def lsr(self, v):
        self.c = v & 1
        return self.nz(v >> 1)

    def rol(self, v):
        r = ((v << 1) | self.c) & 0xFF
        self.c = v >> 7
        return self.nz(r)

    def ror(self, v):
        r = (v >> 1) | (self.c << 7)
        self.c = v & 1
        return self.nz(r)

    def op_asl(self, a):
        self.wr(a, self.asl(self.rd(a)))

    def op_lsr(self, a):
        self.wr(a, self.lsr(self.rd(a)))

    def op_rol(self, a):
        self.wr(a, self.rol(self.rd(a)))

    def op_ror(self, a):
        self.wr(a, self.ror(self.rd(a)))

    def op_asl_a(self):
        self.a = self.asl(self.a)

    def op_lsr_a(self):
        self.a = self.lsr(self.a)

    def op_rol_a(self):
        self.a = self.rol(self.a)

    def op_ror_a(self):
        self.a = self.ror(self.a)

    # --- флаги и переходы ---

    def op_clc(self):
        self.c = 0

    def op_sec(self):
        self.c = 1

    def op_cli(self):
        self.i = 0

    def op_sei(self):
        self.i = 1

    def op_cld(self):
        self.d = 0

    def op_sed(self):
        self.d = 1

    def op_clv(self):
        self.v = 0

    def op_nop(self, a=None):
        if a is not None:
            self.rd(a)

    def op_jmp(self, a):
        self.pc = a

    def op_jsr(self, a):
        pass

    def op_rts(self):
        lo = self.pull()
        self.pc = (((self.pull() << 8) | lo) + 1) & 0xFFFF

    def op_rti(self):
        self.set_p(self.pull())
        lo = self.pull()
        self.pc = (self.pull() << 8) | lo

    def op_brk(self):
        r = (self.pc + 1) & 0xFFFF
        self.push(r >> 8)
        self.push(r & 0xFF)
        self.push(self.get_p(1))
        self.i = 1
        self.pc = self.m[0xFFFE] | (self.m[0xFFFF] << 8)

    def op_jam(self):
        raise Halt("JAM $%02X в $%04X" % (self.m[(self.pc - 1) & 0xFFFF], (self.pc - 1) & 0xFFFF))

    # --- недокументированные ---

    def op_slo(self, a):
        v = self.asl(self.rd(a))
        self.wr(a, v)
        self.a = self.nz(self.a | v)

    def op_rla(self, a):
        v = self.rol(self.rd(a))
        self.wr(a, v)
        self.a = self.nz(self.a & v)

    def op_sre(self, a):
        v = self.lsr(self.rd(a))
        self.wr(a, v)
        self.a = self.nz(self.a ^ v)

    def op_rra(self, a):
        v = self.ror(self.rd(a))
        self.wr(a, v)
        self.adc(v)

    def op_sax(self, a):
        self.wr(a, self.a & self.x)

    def op_lax(self, a):
        self.a = self.x = self.nz(self.rd(a))

    def op_lxa(self, a):
        self.a = self.x = self.nz((self.a | 0xEE) & self.rd(a))

    def op_ane(self, a):
        self.a = self.nz((self.a | 0xEE) & self.x & self.rd(a))

    def op_dcp(self, a):
        v = (self.rd(a) - 1) & 0xFF
        self.wr(a, v)
        self.cmp(self.a, v)

    def op_isc(self, a):
        v = (self.rd(a) + 1) & 0xFF
        self.wr(a, v)
        self.sbc(v)

    def op_anc(self, a):
        self.a = self.nz(self.a & self.rd(a))
        self.c = self.n

    def op_alr(self, a):
        self.a = self.lsr(self.a & self.rd(a))

    def op_arr(self, a):
        v = self.a & self.rd(a)
        r = (v >> 1) | (self.c << 7)
        self.a = self.nz(r)
        self.c = (r >> 6) & 1
        self.v = ((r >> 6) ^ (r >> 5)) & 1

    def op_sbx(self, a):
        t = (self.a & self.x) - self.rd(a)
        self.c = 1 if t >= 0 else 0
        self.x = self.nz(t & 0xFF)

    def op_las(self, a):
        v = self.rd(a) & self.sp
        self.a = self.x = self.sp = self.nz(v)

    def op_sha(self, a):
        self.wr(a, self.a & self.x & (((a >> 8) + 1) & 0xFF))

    def op_shx(self, a):
        self.wr(a, self.x & (((a >> 8) + 1) & 0xFF))

    def op_shy(self, a):
        self.wr(a, self.y & (((a >> 8) + 1) & 0xFF))

    def op_tas(self, a):
        self.sp = self.a & self.x
        self.wr(a, self.sp & (((a >> 8) + 1) & 0xFF))


def load_hex(path, mem):
    """Intel HEX в память"""
    for line in open(path):
        line = line.strip()
        if not line.startswith(":"):
            continue
        b = bytes.fromhex(line[1:])
        n, addr, typ = b[0], (b[1] << 8) | b[2], b[3]
        if typ == 0:
            mem[addr:addr + n] = b[4:4 + n]
