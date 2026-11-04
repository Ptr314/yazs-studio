import sys
rows = [l.split(" | ") for l in open(sys.argv[1])]
R = [[int(v, 16) for v in a.split()] for a, b in rows]
C = [[int(v, 16) for v in b.split()] for a, b in rows]
step = float(sys.argv[2])
# моменты изменения: регистры тонов, ударных, счетчики
import collections
ev = collections.defaultdict(list)
for i in range(1, len(R)):
    for k in range(16):
        if R[i][k] != R[i-1][k]:
            ev["r%X" % k].append(i * step)
    for k in range(6):
        if C[i][k] != C[i-1][k]:
            ev["c%d" % k].append(i * step)
allt = sorted(set(t for v in ev.values() for t in v))
d = collections.Counter(round(b - a, 1) for a, b in zip(allt, allt[1:]))
print("интервалы между изменениями, мс:", d.most_common(12))
for k in sorted(ev):
    print(k, len(ev[k]), ev[k][:12])
