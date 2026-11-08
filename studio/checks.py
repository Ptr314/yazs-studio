# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Все проверки проекта одним запуском:
1. партитуры собираются в те же байты, что записаны в tests/scores.md5 (правка
   compose.py или инструментов не должна молча менять мелодии); текстовый вид
   (yztext.py): каждая .YZ -> текст -> .YZ байт в байт, и блюз в v2 с блоками;
2. test_v2: каждая партитура в v1 и в v2 с блоками дает в модели (pyplay) те же
   записи в ячейку;
3. процессор конвертера SID - тесты Дормана (sid/test_cpu.py, ~30 с);
4. плеер на 6502 в эмуляторе против модели (verify.py): test_fx (все команды
   и эффекты, v1) и блюз в v2 с паттернами в блоке. Нужен eCat3 (docs/ecat3.md);
5. запуск плеера из «Быстропускалки» и по BRUN из ДОС, выход к запустившему
   (brun.py). Нужен еще системный диск ИКП из eCat3;
6. встраиваемый плеер (yz2asm.py): наборы мелодий score/test_embed.py с разными
   возможностями плеера собираются AS65 и играют на 6502 против модели (без
   eCat3; идет и с --quick).

    python studio/checks.py [--quick] [--update]
    --quick   только 1, 2 и 6 (без эмулятора и тестов процессора)
    --update  записать новые суммы партитур (после намеренной правки)
"""

import hashlib
import os
import subprocess
import sys

import build
import render
import test_v2
import yztext

HERE = os.path.dirname(os.path.abspath(__file__))
SUMS = os.path.join(build.ROOT, "tests", "scores.md5")
modules = yztext.score_modules


def check_text(datas):
    """Текстовый вид: .YZ -> текст -> .YZ байт в байт"""
    s = build.load_score("m4_blues")
    s.version, s.main_limit = 2, 300
    files = dict(datas, **{"m4_blues (v2, блоки)": s.build()})
    bad = []
    for m, data in files.items():
        err = yztext.roundtrip(data)
        if err:
            bad.append("%s: %s" % (m, err))
    print("[1] текстовый вид: %d файлов туда и обратно, расхождений %d" % (len(files), len(bad)))
    for line in bad:
        print("    " + line)
    return not bad


def check_sums(update, datas):
    """datas - {партитура: байты .YZ}"""
    got = {m: hashlib.md5(d).hexdigest() for m, d in datas.items()}
    if update or not os.path.exists(SUMS):
        os.makedirs(os.path.dirname(SUMS), exist_ok=True)
        with open(SUMS, "w", encoding="utf-8") as f:
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


def check_embed():
    """Встраиваемый плеер (yz2asm.py): наборы из score/test_embed.py, у каждого -
    свои возможности плеера (шаблон player/yzplay.a65 собирается по-разному);
    каждый набор собирает AS65 и проигрывает на 6502 против модели"""
    import importlib.util
    out = os.path.join(render.OUT, "checks", "embed")
    os.makedirs(out, exist_ok=True)
    sys.path.insert(0, os.path.join(HERE, "score"))
    spec = importlib.util.spec_from_file_location("test_embed", os.path.join(HERE, "score", "test_embed.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    f = {}
    for name in ("song", "boom", "blip", "slide", "vib"):
        f[name] = os.path.join(out, name + ".yz")
        with open(f[name], "wb") as fh:
            fh.write(getattr(mod, name)().build())
    sets = [
        (["song", "boom", "blip", "slide"], ["--key", "--save-zp"]),     # все возможности
        (["song"], ["--no-tail", "--plain"]),
        (["boom"], ["--save-zp", "--zp", "$D0", "--org", "$8000"]),   # только ударные; как из Бейсика
        (["blip"], ["--no-phrases"]),                      # один тоновый канал
        (["slide"], []),                                   # лиги и период без TEMPO
        (["vib"], ["--no-tail"]),                          # период каждый тик
    ]
    bad = []
    for names, keys in sets:
        dst = os.path.join(out, "_".join(names) + ".a65")
        code, text = run(["yz2asm.py"] + [f[n] for n in names] + ["-o", dst] + keys)
        if code != 0 or "проверка на 6502: все" not in text:
            bad.append("%s %s: %s" % ("+".join(names), " ".join(keys), text.strip().splitlines()[-1:]))
    print("[6] встраиваемый плеер (yz2asm): наборов %d, ошибок %d" % (len(sets), len(bad)))
    for line in bad:
        print("    " + line)
    return not bad


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


def main():
    quick = "--quick" in sys.argv
    datas = {m: build.load_score(m).build() for m in modules()}
    ok = check_sums("--update" in sys.argv, datas)
    ok &= check_text(datas)
    bad = sum(not test_v2.check(m) for m in modules())
    print("[2] v1/v2 на модели: расхождений %d" % bad)
    ok &= bad == 0
    ok &= check_embed()
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
            import brun
            if not os.path.exists(brun.IKP):
                print("[5] пропущено: нет системного диска ИКП", brun.IKP)
            else:
                code, text = run(["brun.py"])
                bad = [l.strip() for l in text.splitlines() if "ОШИБКА" in l]
                last = [l for l in text.splitlines() if l.startswith("запуск и выход")]
                print("[5] %s" % (last[-1] if last else "запуск и выход: " + text[-500:]))
                for l in bad:
                    print("    " + l)
                ok &= code == 0
    print("ВСЕ ПРОВЕРКИ ПРОШЛИ" if ok else "ЕСТЬ ОШИБКИ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
