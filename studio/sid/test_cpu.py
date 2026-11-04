# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Проверка cpu6502.py тестами Клауса Дормана (third_party/6502-tests): функциональным
(как есть) и десятичным - собранным заново для NMOS 6502 (в репозитории он
собран для 65C02, а у NMOS другие флаги N, V, Z в десятичном режиме).

    python studio/sid/test_cpu.py        (~30 с)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sid import cpu6502  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
TESTS = os.path.join(ROOT, "third_party", "6502-tests")
AS65 = os.path.join(ROOT, "third_party", "as65", "as65.exe")


def run(hexpath, start, ok_pc, check=None):
    cpu = cpu6502.CPU6502()
    cpu6502.load_hex(hexpath, cpu.m)
    cpu.pc = start
    t0 = time.time()
    n = 0
    m, table, cyc = cpu.m, cpu.table, cpu.cyc
    while True:
        pc = cpu.pc
        op = m[pc]
        cpu.pc = (pc + 1) & 0xFFFF
        cpu.cycles += cyc[op]
        table[op]()
        n += 1
        if cpu.pc == pc:                 # ловушка: JMP * или переход на себя
            break
    good = cpu.pc == ok_pc and (check is None or check(cpu))
    print("%-26s %s: ловушка $%04X, %d команд, %.1f с" % (
        os.path.basename(hexpath), "OK" if good else "ОШИБКА", cpu.pc, n, time.time() - t0))
    return good


def nmos_decimal(tmp):
    """6502_decimal_test.a65 с cputype = 0 -> .hex; адрес ловушки DONE - из листинга"""
    src = os.path.join(tmp, "dec_nmos.a65")
    text = open(os.path.join(TESTS, "6502_decimal_test.a65"), encoding="latin-1").read()
    text = text.replace("cputype = 1 ", "cputype = 0 ", 1)
    open(src, "w", encoding="latin-1").write(text)
    subprocess.run([AS65, "-l", "-m", "-s2", "-w", "-h0", "dec_nmos.a65"], cwd=tmp,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    hexp = os.path.join(tmp, "dec_nmos.hex")
    if not os.path.exists(hexp):
        sys.exit("AS65 не собрал десятичный тест")
    done = None
    for line in open(os.path.join(tmp, "dec_nmos.lst"), encoding="latin-1"):
        if "jmp *" in line and ":" in line:
            done = int(line.split(":")[0].strip(), 16)
    return hexp, done


def main():
    tmp = tempfile.mkdtemp(prefix="cpu6502-")
    try:
        hexp, done = nmos_decimal(tmp)
        ok = run(hexp, 0x0200, done, lambda c: c.m[0x0B] == 0)       # ERROR = 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # функциональный: success - jmp * на $347D (листинг теста, success)
    ok &= run(os.path.join(TESTS, "6502_functional_test.hex"), 0x0400, 0x347D)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
