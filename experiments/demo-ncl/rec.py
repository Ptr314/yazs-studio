"""Звук демонстрации НКЛ с диска music-d.dsk: запуск по readme, запись WAV на скорости MAX"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio")))
import render  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 480

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
    'COMMAND sound.record("demo.wav")',
    "KEY 300,100,ret",
]
for s in range(0, SECS, 30):
    lines.append("WAIT 30000")
    lines.append('SCREEN "shot-%03d.png"' % (s + 30))
lines += ['COMMAND sound.record()', "LOGDEFS 8,16", "LOG yazs.irqs", "EXIT"]
print(render.run(lines, "demo", OUT, timeout=3000)[-500:])

rate, x = render.load_wav(os.path.join(OUT, "demo.wav"))
n = len(x) // rate
rms = [float(np.sqrt(np.mean(x[i * rate:(i + 1) * rate] ** 2))) for i in range(n)]
print("длина %.1f с, пик %.2f" % (len(x) / float(rate), float(np.max(np.abs(x)))))
line = []
for i, r in enumerate(rms):
    line.append("%3d" % int(round(-render.db(r))) if r > 0 else "  -")
    if len(line) == 20:
        print("  %3d-%3d с, -дБ: %s" % (i - 19, i, " ".join(line)))
        line = []
if line:
    print("  %3d-    с, -дБ: %s" % (n - len(line), " ".join(line)))
