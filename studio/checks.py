# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Все проверки проекта одним запуском:
1. партитуры собираются в те же байты, что записаны в tests/scores.md5 (правка
   compose.py или инструментов не должна молча менять мелодии);
2. test_v2: каждая партитура в v1 и в v2 с блоками дает в модели (pyplay) те же
   записи в ячейку;
3. процессор конвертера SID - тесты Дормана (sid/test_cpu.py, ~30 с);
4. плеер на 6502 в эмуляторе против модели (verify.py): test_fx (все команды
   и эффекты, v1) и блюз в v2 с паттернами в блоке. Нужен eCat3 (docs/ecat3.md).

    python studio/checks.py [--quick] [--update]
    --quick   только 1-2 (без эмулятора и тестов процессора)
    --update  записать новые суммы партитур (после намеренной правки)
"""

import glob
import hashlib
import os
import subprocess
import sys

import build
import render
import test_v2

HERE = os.path.dirname(os.path.abspath(__file__))
SUMS = os.path.join(build.ROOT, "tests", "scores.md5")


def modules():
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, "score", "*.py"))):
        m = os.path.splitext(os.path.basename(p))[0]
        if m not in ("common", "instruments") and not m.startswith("data_"):
            out.append(m)
    return out


def check_sums(update):
    got = {}
    for m in modules():
        got[m] = hashlib.md5(build.load_score(m).build()).hexdigest()
    if update or not os.path.exists(SUMS):
        os.makedirs(os.path.dirname(SUMS), exist_ok=True)
        with open(SUMS, "w", encoding="utf-8", newline="\n") as f:
            for m, h in got.items():
                f.write("%s  %s.yz\n" % (h, m))
        print("[1] суммы партитур записаны: %d" % len(got))
        return True
    want = {}
    for line in open(SUMS, encoding="utf-8"):
        h, name = line.split()
        want[name[:-3]] = h
    bad = [m for m in got if want.get(m) != got[m]]
    new = [m for m in got if m not in want]
    print("[1] партитуры: %d, изменились: %s%s" % (
        len(got), ", ".join(m for m in bad if m not in new) or "нет",
        ("; новые (нет в scores.md5): " + ", ".join(new)) if new else ""))
    return not [m for m in bad if m not in new]


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


def main():
    quick = "--quick" in sys.argv
    ok = check_sums("--update" in sys.argv)
    bad = sum(not test_v2.check(m) for m in modules())
    print("[2] v1/v2 на модели: расхождений %d" % bad)
    ok &= bad == 0
    if not quick:
        code, text = run([os.path.join("sid", "test_cpu.py")])
        print("[3] процессор SID:", "OK" if code == 0 else "ОШИБКА\n" + text)
        ok &= code == 0
        try:
            render.find_exe()
        except SystemExit as e:
            print("[4] пропущено:", e)
        else:
            out = os.path.join(render.OUT, "checks")
            os.makedirs(out, exist_ok=True)
            s = build.load_score("m4_blues")
            s.version, s.main_limit = 2, 300
            v2 = os.path.join(out, "blues_v2.yz")
            open(v2, "wb").write(s.build())
            for src in ("test_fx", v2):
                code, text = run(["verify.py", src, "60", "331"])
                last = [l for l in text.splitlines() if l.startswith("снимков")]
                print("[4] плеер против модели, %s: %s" % (os.path.basename(src), last[-1] if last else text[-500:]))
                ok &= code == 0
    print("ВСЕ ПРОВЕРКИ ПРОШЛИ" if ok else "ЕСТЬ ОШИБКИ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
