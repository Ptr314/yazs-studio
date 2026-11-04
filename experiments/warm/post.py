"""Симфония целиком, A/B-сравнение по частям и мерки теплой версии"""
import os
import subprocess
import sys
import wave

import numpy as np

S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(S, "demo"))
import compare  # noqa: E402

FINAL = os.path.join(S, "final")
W = os.path.join(S, "warm", "listen")
OUT = os.path.join(S, "warm")
FF = r"C:\DEV\ffmpeg-n9.0-latest-win64-lgpl-9.0\bin\ffmpeg.exe"
PARTS = ["m1_toccata", "m2_adagio", "m3_scherzo", "m4_blues", "m5_synth", "m6_finale"]


def read(path):
    with wave.open(path, "rb") as w:
        return w.getparams(), w.readframes(w.getnframes())


def mp3(wav, out, title):
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", wav, "-codec:a", "libmp3lame", "-b:a", "192k",
                    "-metadata", "title=" + title, "-metadata", "artist=eCat3, Агат-9 + ЯЗС 5/2", out], check=True)


def main():
    params = None
    full = []
    ab = []
    for p in PARTS:
        pa, warm = read(os.path.join(W, p + ".wav"))
        pb, orig = read(os.path.join(FINAL, p + ".wav"))
        assert pa.framerate == pb.framerate and pa.nchannels == pb.nchannels and pa.sampwidth == pb.sampwidth
        params = pa
        fb = pa.sampwidth * pa.nchannels
        sec = pa.framerate * fb
        full.append(warm)
        # A/B: 30 с основной версии, пауза 1 с, те же 30 с теплой, пауза 2 с
        ab.append(orig[:30 * sec] + b"\x00" * sec + warm[:30 * sec] + b"\x00" * (2 * sec))
    gap = b"\x00" * (2 * params.framerate * params.sampwidth * params.nchannels)
    for name, chunks, sep, title in (("symphony-warm", full, gap, "Симфония А-Г-А-Т, теплая версия"),
                                     ("ab-compare", ab, b"", "Основная / теплая версия по 30 с")):
        wav = os.path.join(OUT, name + ".wav")
        with wave.open(wav, "wb") as w:
            w.setparams(params)
            for i, c in enumerate(chunks):
                if i:
                    w.writeframes(sep)
                w.writeframes(c)
        mp3(wav, os.path.join(OUT, name + ".mp3"), title)
        with wave.open(wav, "rb") as w:
            secs = w.getnframes() / float(w.getframerate())
        print(name, "%d:%02d" % (secs // 60, secs % 60))

    tot = None
    for p in PARTS:
        R, C = compare.song_series(os.path.join(W, p + ".yz"))
        compare.show(p + " (теплая)", compare.metrics(R, C), compare.audio(os.path.join(W, p + ".wav")))
        tot = (R, C) if tot is None else (np.r_[tot[0], R], np.r_[tot[1], C])
    compare.show("ТЕПЛАЯ СИМФОНИЯ целиком", compare.metrics(*tot),
                 compare.audio(os.path.join(OUT, "symphony-warm.wav")))


main()
