"""Регистры и счетчики ЯЗС в демонстрации НКЛ по времени: LOG каждые STEP мс"""
import os
import re
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio")))
import render  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
T0 = int(sys.argv[1])        # с от ВВОДА после [RUN DEMO
SECS = int(sys.argv[2])
STEP = int(sys.argv[3])      # мс
NAME = sys.argv[4]

lines = [
    'MACHINE "agat/Agat-9-yazs.ext"',
    "SPEED MAX",
    "WAIT 9000",
    "KEY 300,100,up,up,up",
    "KEY 300,100,ret",
    "WAIT 6000",
    "KEY 300,100,esc",
    "WAIT 3000",
    "KEY 300,100,down,down,down,down",
    "KEY 300,100,ret",
    "WAIT 2000",
    'TYPE "[RUN DEMO"',
    "KEY 300,100,ret",
    "LOGDEFS 8,16",
]
if T0:
    lines.append("WAIT %d" % (T0 * 1000))
for i in range(SECS * 1000 // STEP):
    lines.append("WAIT %d" % STEP)
    lines.append("LOG yazs.regs")
    lines.append("LOG yazs.counters")
lines += ["LOG yazs.irqs", "EXIT"]
if len(sys.argv) > 5:
    import glob
    out = open(sorted(glob.glob(os.path.join(OUT, NAME + "-2*.log")))[-1], encoding="utf-8").read()
else:
    out = render.run(lines, NAME, OUT, timeout=3000)

regs = []
cnts = []
for ln in out.splitlines():
    m = re.match(r"\[yazs\.regs\]\s*(.*)", ln)
    if m:
        regs.append([int(v.strip("$"), 16) for v in m.group(1).split() if not v.endswith(":")])
        continue
    m = re.match(r"\[yazs\.counters\]\s*(.*)", ln)
    if m:
        cnts.append([int(v.strip("$"), 16) for v in m.group(1).split()])
with open(os.path.join(OUT, NAME + ".txt"), "w") as f:
    for r, c in zip(regs, cnts):
        f.write(" ".join("%02X" % v for v in r) + " | " + " ".join("%04X" % v for v in c) + "\n")
print(len(regs), len(cnts))
print(out[-200:])
