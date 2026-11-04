import os
import sys, subprocess, wave
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio")))
import numpy as np, render
rate, x = render.load_wav("demo.wav")
print("выше 0.89: %.4f%%, выше 0.99: %.4f%%" % (100*np.mean(np.abs(x) > 0.89), 100*np.mean(np.abs(x) > 0.99)))
a = int(395*rate); b = int(403*rate)
seg = np.abs(x[a:b]) > 0.002
idx = np.nonzero(seg)[0]
# последний звук перед тишиной ~401 с
gaps = np.nonzero(np.diff(idx) > rate//4)[0]
end = (a + idx[gaps[0]]) / rate if len(gaps) else 401.0
start = np.nonzero(np.abs(x) > 0.002)[0][0] / rate - 0.05
print("start %.2f end %.2f len %.1f" % (start, end, end - start))
ff = r"C:\DEV\ffmpeg-n9.0-latest-win64-lgpl-9.0\bin\ffmpeg.exe"
subprocess.run([ff, "-y", "-loglevel", "error", "-ss", "%.2f" % start, "-to", "%.2f" % (end + 0.3), "-i", "demo.wav",
                "-codec:a", "libmp3lame", "-b:a", "192k",
                "-metadata", "title=Демонстрация НКЛ (music-d.dsk)", "-metadata", "artist=eCat3, Агат-9 + ЯЗС 5/2",
                "music-d-demo.mp3"], check=True)
