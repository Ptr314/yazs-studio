import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio")))
import render  # noqa: E402

S = os.path.dirname(os.path.abspath(__file__))
module = sys.argv[1] if len(sys.argv) > 1 else "m1_toccata"
secs = int(sys.argv[2]) if len(sys.argv) > 2 else 132
disk = os.path.join(S, "listen", module + ".dsk").replace("\\", "/")
lines = ['MACHINE "agat/Agat-9-yazs.ext"', 'COMMAND fdd0.load("%s")' % disk, "RESET cold",
         "SPEED MAX", "WAIT 12000", "LOGDEFS 16,10", "KEY 100,100,ret", "WAIT 700"]
if len(sys.argv) > 3:
    lines += ["KEY 50,50,ret", "WAIT 300"]
for i in range(secs):
    lines += ["LOG yazs.irqs", "LOG ram.value($1E,$1F)", "LOG ram.value($14,$14)", "WAIT 1000"]
lines.append("EXIT")
out = render.run(lines, "lost", os.path.join(S, "lost"))
irq, tc, fr = [], [], []
for l in out.splitlines():
    if l.startswith("[yazs.irqs]"):
        irq.append(int(l.split()[-1]))
    elif l.startswith("[ram.value] 30:"):
        v = l.split(":")[1].split()
        tc.append(int(v[0]) + 256 * int(v[1]))
    elif l.startswith("[ram.value] 20:"):
        fr.append(int(l.split(":")[1].split()[0]))
base = irq[0] - tc[0]
prev = 0
for i in range(len(tc)):
    d = irq[i] - tc[i] - base
    if d != prev:
        print("t=%3d с кадр %2d потеряно всего %d (+%d)" % (i, fr[i], d, d - prev))
        prev = d
print("итого", prev)
