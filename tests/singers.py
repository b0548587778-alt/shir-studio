"""זמרים מלאכותיים לבדיקות האיכות: שירה מזויפת בכוונה בכמה אופנים, עם 'האמת' (מה היה צריך לצאת)."""
import numpy as np
from shir_studio.audio.fileio import SR

# ניגון בלה מינור (midi, פעמות); None = נשימה
NIGUN = [(69, 1), (71, 1), (72, 1), (74, 1), (76, 2), (76, 2),
         (77, 1), (76, 1), (74, 1), (72, 1), (71, 2), (69, 1), (None, 1),
         (72, 1), (74, 1), (76, 1), (77, 1), (76, 2), (74, 2),
         (72, 1), (71, 1), (68, 1), (71, 1), (69, 3), (None, 1)]
# שיר שבת ברה מז'ור
SHABBAT = [(62, 1), (66, 1), (69, 2), (71, 1), (69, 1), (66, 2),
           (67, 1), (66, 1), (64, 1), (62, 1), (64, 3), (None, 1),
           (66, 1), (67, 1), (69, 2), (74, 1), (73, 1), (71, 2),
           (69, 1), (67, 1), (66, 1), (64, 1), (62, 3), (None, 1)]
SONGS = {"nigun": (NIGUN, 9, "minor"), "shabbat": (SHABBAT, 2, "major")}


def sing(melody=NIGUN, bpm=100, repeats=2, seed=0, wobble=0.0, detune=0.0, drift=0.0, flat_high=0.0,
         slide=0.0, scoop=0.0, vibrato=0.35, rubato=0.0, noise=0.004):
    """wobble: טעות אקראית לכל תו (חצאי טונים) · detune: כל השיר לא מכוון · drift: ירידה לאורך השיר ·
    flat_high: הצלילים הגבוהים נמוכים מדי · slide: התו 'נוזל' למטה לאורך ההחזקה · scoop: כניסה מלמטה ·
    rubato: הקצב 'נושם' (0.2 = מאיץ ומאט ב-20%). מחזיר (קול, [(זמן, midi נכון, טעות)], זמני הפעמות)."""
    rng = np.random.default_rng(seed)
    seq = list(melody) * repeats
    top = max(m for m, _ in seq if m) ; low = min(m for m, _ in seq if m)
    nb = sum(b for _, b in seq)
    k = np.arange(int(nb) + 2)
    per = 60 / bpm * (1 + rubato * np.sin(2 * np.pi * k / 16.0))
    beats = 0.5 + np.concatenate([[0], np.cumsum(per)])
    at = lambda q: float(np.interp(q, np.arange(len(beats)), beats))
    total = at(nb) + 1.0
    n = int(total * SR)
    f = np.zeros(n); amp = np.zeros(n)
    truth, q = [], 0.0
    for m, b in seq:
        if m is None:
            q += b
            continue
        t0, t1 = at(q), at(q + b * 0.93)
        a, e = int(t0 * SR), int(t1 * SR)
        tt = np.arange(e - a) / SR
        err = rng.uniform(-wobble, wobble) + detune + drift * t0 / total - flat_high * (m - low) / max(1, top - low)
        p = m + err - slide * tt / max(tt[-1], 0.3) - scoop * np.exp(-tt / 0.06)
        vib = vibrato * np.sin(2 * np.pi * 5.5 * tt) * np.minimum(1, tt / 0.35)
        f[a:e] = 440 * 2 ** ((p + vib - 69) / 12)
        amp[a:e] = np.minimum(1, tt / 0.04) * np.minimum(1, tt[::-1] / 0.06)
        truth.append((t0, m, err, t1))
        q += b
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.zeros(n)
    for h in range(1, 25):
        fk = h * f
        g = np.exp(-((fk - 650) / 250) ** 2) + 0.6 * np.exp(-((fk - 1150) / 300) ** 2) + \
            0.25 * np.exp(-((fk - 2700) / 500) ** 2) + 0.03
        x += np.where(fk < 16000, g / h ** 0.7, 0) * np.sin(h * ph)
    x *= amp
    x = x / np.abs(x).max() * 0.5 + noise * rng.standard_normal(n)
    return x.astype(np.float32), truth, beats[: int(nb) + 1]


# הזמרים של בדיקת האיכות: שם -> (שיר, פרמטרים)
CASES = {
    "מדויק": ("nigun", dict(wobble=0.05)),
    "זיוף בינוני": ("nigun", dict(wobble=0.45, seed=3)),
    "זיוף חזק": ("nigun", dict(wobble=0.7, seed=3)),
    "זיוף חזק 2": ("shabbat", dict(wobble=0.7, seed=5)),
    "יורד לאורך השיר": ("shabbat", dict(wobble=0.3, drift=-1.2, seed=2)),
    "גבוהים נמוכים": ("nigun", dict(wobble=0.25, flat_high=0.8, seed=4)),
    "תווים נוזלים": ("shabbat", dict(wobble=0.3, slide=0.6, scoop=0.8, seed=6)),
    "לא מכוון + זיוף": ("nigun", dict(wobble=0.5, detune=0.4, seed=8)),
    "קצב נושם": ("shabbat", dict(wobble=0.3, rubato=0.15, seed=9)),
}
