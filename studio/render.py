# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Прогон eCat3-headless над сгенерированным сценарием .ecat: звук пишется в WAV
(COMMAND sound.record) на скорости MAX, так что минуты музыки считаются за
секунды, а LOG и снимки дают состояние машины.

Эмулятор - eCat3 (https://github.com/Ptr314/ecat3), его рабочая копия лежит рядом
(../eCat3) или задается переменной ECAT3_DIR; консольная сборка ищется в
src/cmake-build-*, другую задает ECAT3_HEADLESS (docs/ecat3.md).

Эмулятор запускается в своем рабочем каталоге (--workdir): там ссылки на
deploy/computers, data, software eCat3 и копия deploy/.ecat.ini, так что рабочий
deploy/ecat.ini разработчика не читается и не переписывается.

Оконный eCat3 (find_gui, launch_gui) - для живой работы с плеером (play.py):
сборка из src/cmake-build-* или отдельный выпуск, у которого все рядом с exe.
"""

import math
import os
import re
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))           # yazs-studio
OUT = os.path.join(ROOT, "out")
ECAT3 = os.path.normpath(os.environ.get("ECAT3_DIR") or os.path.join(ROOT, "..", "eCat3"))
DEPLOY = os.path.join(ECAT3, "deploy")


def find_exe():
    exe = os.environ.get("ECAT3_HEADLESS")
    if exe and os.path.isfile(exe):
        return exe
    for d in ("cmake-build-headless", "cmake-build-mcp", "cmake-build-headless-mcp"):
        p = os.path.join(ECAT3, "src", d, "eCat3-headless.exe" if os.name == "nt" else "eCat3-headless")
        if os.path.isfile(p):
            return p
    sys.exit("eCat3-headless не найден в %s: соберите его или задайте ECAT3_DIR / ECAT3_HEADLESS"
             " (docs/ecat3.md)" % ECAT3)


def find_gui():
    """Оконный eCat3: (exe, каталог с computers/). Порядок поиска: ECAT3_EXE (как
    в .mcp.json); выпуск в ECAT3_DIR (eCat3.exe рядом с computers/); сборки
    src/cmake-build-mcp, затем остальные src/cmake-build-* - свежая первой"""
    name = "eCat3.exe" if os.name == "nt" else "eCat3"
    cands = []
    if os.environ.get("ECAT3_EXE"):
        cands.append(os.environ["ECAT3_EXE"])
    cands += [os.path.join(ECAT3, name), os.path.join(DEPLOY, name),
              os.path.join(ECAT3, "src", "cmake-build-mcp", name)]
    builds = os.path.join(ECAT3, "src")
    if os.path.isdir(builds):
        more = [os.path.join(builds, d, name) for d in os.listdir(builds) if d.startswith("cmake-build-")]
        cands += sorted((p for p in more if os.path.isfile(p)), key=os.path.getmtime, reverse=True)
    for exe in cands:
        if os.path.isfile(exe):
            here = os.path.dirname(os.path.abspath(exe))
            deploy = here if os.path.isdir(os.path.join(here, "computers")) else DEPLOY
            if not os.path.isdir(os.path.join(deploy, "computers")):
                sys.exit("у eCat3 %s нет каталога computers/ ни рядом, ни в %s" % (exe, DEPLOY))
            return exe, deploy
    sys.exit("оконный eCat3 не найден: задайте ECAT3_EXE (путь к eCat3.exe) или ECAT3_DIR "
             "(docs/ecat3.md)")


def environment(exe):
    """PATH с рантаймом компилятора и Qt, как в tests/run_tests.py. Отдельному
    выпуску ничего не нужно: у него все рядом с exe, CMakeCache.txt нет"""
    env = dict(os.environ)
    if os.name != "nt":
        return env
    cache = os.path.join(os.path.dirname(exe), "CMakeCache.txt")
    extra = []
    if os.path.isfile(cache):
        text = open(cache, encoding="utf-8", errors="replace").read()
        m = re.search(r"^CMAKE_CXX_COMPILER:(?:FILEPATH|STRING)=(.+)$", text, re.M)
        if m:
            extra.append(os.path.dirname(m.group(1)).replace("/", os.sep))
        # Оконной сборке - еще DLL Qt: .../lib/cmake/Qt6 -> .../bin
        m = re.search(r"^Qt[56]_DIR:PATH=(.+)$", text, re.M)
        if m:
            extra.append(os.path.normpath(os.path.join(m.group(1), "..", "..", "..", "bin")))
    extra = [p for p in extra if os.path.isdir(p)]
    if extra:
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    return env


def workdir(base, deploy=None, keep_ini=False):
    """Рабочий каталог эмулятора: ссылки на каталоги deploy и свой ecat.ini.
    keep_ini - не перезаписывать ecat.ini, если он уже есть (оконный eCat3
    хранит в нем окно, громкость и пр.)"""
    deploy = deploy or DEPLOY
    wd = os.path.join(os.path.normpath(os.path.abspath(base)), "work")
    os.makedirs(wd, exist_ok=True)
    for name in ("computers", "data", "software"):
        link = os.path.join(wd, name)
        target = os.path.join(deploy, name)
        if os.path.exists(link) or not os.path.isdir(target):
            continue
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                           check=True, stdout=subprocess.DEVNULL)
        else:
            os.symlink(target, link)
    ini = os.path.join(wd, "ecat.ini")
    src = os.path.join(deploy, ".ecat.ini")
    if os.path.isfile(src) and not (keep_ini and os.path.isfile(ini)):
        with open(src, "rb") as f:
            data = f.read()
        with open(ini, "wb") as f:
            f.write(data)
    return wd


def launch_gui(lines, name, outdir, wait=False):
    """Пишет outdir/name.ecat и открывает его в оконном eCat3. Сценарий кончается,
    машина остается работать: дальше - клавиатура человека"""
    outdir = os.path.normpath(os.path.abspath(outdir))
    os.makedirs(outdir, exist_ok=True)
    exe, deploy = find_gui()
    path = os.path.join(outdir, name + ".ecat")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    wd = workdir(outdir, deploy, keep_ini=True)
    proc = subprocess.Popen([exe, "--workdir", wd, "--script", path], env=environment(exe),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if wait:
        proc.wait()
    return exe


def run(lines, name, outdir, timeout=900, exe=None):
    """Пишет outdir/name.ecat, гонит его и возвращает напечатанное"""
    outdir = os.path.normpath(os.path.abspath(outdir))
    os.makedirs(outdir, exist_ok=True)
    exe = exe or find_exe()
    path = os.path.join(outdir, name + ".ecat")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    wd = workdir(outdir)
    stamped = re.compile(re.escape(name) + r"-\d{4}(-\d{2}){5}\.log$")
    for f in os.listdir(outdir):
        if stamped.match(f):
            os.remove(os.path.join(outdir, f))
    proc = subprocess.run([exe, "--no-sound", "--workdir", wd, "--script", path],
                          env=environment(exe), timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 or err:
        sys.stderr.write(out[-3000:] + "\n" + err + "\n")
        raise RuntimeError("%s: код %d" % (name, proc.returncode))
    # LOG пишется в лог сценария: имя-дата.log рядом с ним
    for f in sorted(os.listdir(outdir)):
        if stamped.match(f):
            with open(os.path.join(outdir, f), encoding="utf-8", errors="replace") as lf:
                out += lf.read()
    return out


def load_wav(path):
    """(частота, отсчеты float в -1..1)"""
    import numpy as np
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0]
    return rate, data


def db(x):
    return 20 * math.log10(max(float(x), 1e-9))
