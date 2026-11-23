"""קול סינתטי לבדיקות: מנגינה בסולם ידוע, עם זיופים, זליגה וקצב."""
import numpy as np
from shir_studio.audio.fileio import SR

MELODY = [  # (midi, beats)  - ניגון בלה מינור
    (69, 1), (71, 1), (72, 1), (74, 1), (76, 2), (76, 2),
    (77, 1), (76, 1), (74, 1), (72, 1), (71, 2), (69, 2),
    (72, 1), (74, 1), (76, 1), (77, 1), (76, 2), (74, 2),
    (72, 1), (71, 1), (68, 1), (71, 1), (69, 4),
]


def sing(bpm=120, detune=0.0, drift=0.0, wobble=0.25, seed=0, repeats=2, vibrato=0.0):
    """vibrato: עומק ויברטו בחצאי טונים (זמר מקצועי: 0.5-1)."""
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    seq = MELODY * repeats
    total = sum(b for _, b in seq) * beat + 1.0
    n = int(total * SR)
    f = np.zeros(n)
    amp = np.zeros(n)
    t0 = 0.5
    truth = []
    for m, b in seq:
        if m is None:                       # הפסקה (נשימה בין משפטים)
            t0 += b * beat
            continue
        a, e = int(t0 * SR), int((t0 + b * beat * 0.92) * SR)
        err = rng.uniform(-wobble, wobble)
        tt = np.arange(e - a) / SR
        p = m + detune + err + drift * (t0 / total)
        vib = vibrato * np.sin(2 * np.pi * 5.5 * tt) * np.minimum(1, tt / 0.3)   # ויברטו שמתחיל אחרי רגע
        f[a:e] = 440 * 2 ** ((p + vib - 69) / 12) * (1 + 0.003 * np.sin(2 * np.pi * 5.5 * tt))
        env = np.minimum(1, tt / 0.04) * np.minimum(1, (tt[::-1]) / 0.05)
        amp[a:e] = env
        truth.append((t0, m, err))
        t0 += b * beat
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.zeros(n)
    for k in range(1, 25):
        fk = k * f
        g = np.exp(-((fk - 750) / 250) ** 2) + 0.6 * np.exp(-((fk - 1150) / 300) ** 2) + \
            0.2 * np.exp(-((fk - 2800) / 500) ** 2) + 0.03
        x += np.where(fk < 16000, g / k ** 0.7, 0) * np.sin(k * ph)
    x *= amp
    x = x / np.abs(x).max() * 0.5 + 0.004 * rng.standard_normal(n)
    return x.astype(np.float32), truth
