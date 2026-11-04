import os
import subprocess
import wave

S = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(S, "final")
parts = ["m1_toccata", "m2_adagio", "m3_scherzo", "m4_blues", "m5_synth", "m6_finale"]
frames = []
params = None
for p in parts:
    with wave.open(os.path.join(D, p + ".wav"), "rb") as w:
        if params is None:
            params = w.getparams()
        assert w.getframerate() == params.framerate and w.getnchannels() == params.nchannels
        frames.append(w.readframes(w.getnframes()))
gap = b"\x00" * (params.sampwidth * params.nchannels * params.framerate * 2)
out = os.path.join(D, "symphony.wav")
with wave.open(out, "wb") as w:
    w.setparams(params)
    for i, f in enumerate(frames):
        if i:
            w.writeframes(gap)
        w.writeframes(f)
ff = r"C:\DEV\ffmpeg-n9.0-latest-win64-lgpl-9.0\bin\ffmpeg.exe"
mp3 = os.path.join(D, "symphony-agat.mp3")
subprocess.run([ff, "-y", "-loglevel", "error", "-i", out, "-codec:a", "libmp3lame", "-b:a", "192k",
                "-metadata", "title=Симфония А-Г-А-Т для ЯЗС 5/2",
                "-metadata", "artist=eCat3, Агат-9 + ЯЗС 5/2", mp3], check=True)
with wave.open(out, "rb") as w:
    secs = w.getnframes() / float(w.getframerate())
print(mp3, "%.0f:%02.0f" % (secs // 60, secs % 60), os.path.getsize(mp3))
