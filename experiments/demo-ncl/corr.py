import os
import sys
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio")))
import numpy as np, render
rate, x = render.load_wav("demo.wav")
w = rate // 10
n = len(x) // w
e = np.sqrt(np.mean(x[:n*w].reshape(n, w)**2, axis=1))
e = 20*np.log10(e + 1e-9)
# где начинается звук и тишины
nz = np.nonzero(np.abs(x) > 0.002)[0]
print("первый звук %.2f с" % (nz[0]/rate))
q = np.nonzero(e < -45)[0]
print("тихие отрезки по 0.1 с:", [round(i/10.0,1) for i in q][:80])
a = e[150:900]
best = []
for lag in range(3000, n - 750 - 150):
    b = e[150+lag:900+lag]
    c = np.corrcoef(a, b)[0,1]
    best.append((c, lag/10.0))
best.sort(reverse=True)
print(best[:5])
