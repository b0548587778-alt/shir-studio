"""שינוי גובה צליל בשיטת TD-PSOLA - שומר על צבע הקול הטבעי. מימוש עצמי."""
from functools import lru_cache

import numpy as np
from scipy.signal import butter, sosfiltfilt

from .fileio import SR
from .pitch import FRAME_SEC

UNVOICED_P = int(0.005 * SR)


@lru_cache(maxsize=4096)
def _hann(L):
    """חלון לכל אורך מחזור - מחושב פעם אחת (אותו אורך חוזר אלפי פעמים בשיר)."""
    w = np.hanning(L)
    w.setflags(write=False)
    return w


def _per_sample(track, n):
    t_frames = np.arange(len(track)) * FRAME_SEC * SR
    return np.interp(np.arange(n), t_frames, track)


def analysis_marks(x, f0):
    """מיקומי מחזורים (pitch marks) והמחזור בכל אחד."""
    n = len(x)
    f = _per_sample(f0, n)
    voiced_frames = f0 > 0
    v = _per_sample(voiced_frames.astype(float), n) > 0.5
    sos = butter(2, 900, fs=SR, output="sos")
    lp = sosfiltfilt(sos, x)
    marks, periods = [], []
    t = 0
    while t < n:
        if v[t] and f[t] > 0:
            P = SR / f[t]
            # כיוון לשיא המקומי לעקביות בין מחזורים
            r = int(P * 0.15)
            if marks and v[marks[-1]]:
                lo, hi = max(0, t - r), min(n, t + r + 1)
                t = lo + int(np.argmax(lp[lo:hi]))
            else:
                hi = min(n, t + int(P))
                t = t + int(np.argmax(lp[t:hi])) if hi > t else t
            marks.append(t)
            periods.append(P)
            t = int(round(t + P))
        else:
            marks.append(t)
            periods.append(UNVOICED_P)
            t += UNVOICED_P
    return np.array(marks), np.array(periods), v


TAPS = 16                 # אורך מסנן ההזזה (דגימות)
PHASES = 64               # דיוק ההזזה: 1/64 של דגימה


@lru_cache(maxsize=1)
def _frac_filters():
    """מסננים להזזת קטע בשבר של דגימה (sinc עם חלון קייזר). בלי זה כל מחזור ממוקם בדיוק של דגימה שלמה,
    וה'רעידה' הזעירה הזו נשמעת כצרידות - שכבת רעש מתחת לקול."""
    j = TAPS // 2 - np.arange(TAPS)                               # המרחק של כל דגימה מהנקודה המבוקשת
    out = np.zeros((PHASES, TAPS))
    for p in range(PHASES):
        t = j - p / PHASES
        k = np.sinc(t) * np.kaiser(2 * TAPS + 1, 8.0)[np.clip(np.round(t + TAPS).astype(int), 0, 2 * TAPS)]
        out[p] = k / k.sum()
    out.setflags(write=False)
    return out


def shift(x: np.ndarray, f0: np.ndarray, semitones: np.ndarray) -> np.ndarray:
    """semitones: תיקון בחצאי טונים לכל פריים של 10ms (0 = ללא שינוי).
    המרווח בין המחזורים בפלט נגזר מהמרווח האמיתי שנמדד בהקלטה (ולא מהערכה), וכל מחזור ממוקם בדיוק
    של שבר דגימה. כך קטע שלא מתוקן יוצא זהה למקור, וקטע שמתוקן נשאר נקי - בלי צרידות."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    marks, periods, v = analysis_marks(x, f0)
    ratio = 2 ** (_per_sample(semitones, n) / 12)
    filt = _frac_filters()
    half = TAPS // 2
    xp = np.concatenate([np.zeros(half), x, np.zeros(half + 1)])   # שוליים למסנן ההזזה
    out = np.zeros(n + 4 * SR // 100)
    wsum = np.zeros_like(out)
    s = float(marks[0])
    k = 0
    nm = len(marks)
    was_voiced = False
    while s < n:
        while k + 1 < nm and abs(marks[k + 1] - s) < abs(marks[k] - s):
            k += 1
        a = marks[k]
        P = periods[k]
        voiced = v[min(a, n - 1)] and P != UNVOICED_P
        Pi = int(P)
        L = 2 * Pi + 1
        lo = a - Pi
        if not voiced or not was_voiced:
            s = float(a)                    # מה שאינו צליל (עיצורים, נשימה, שקט) ותחילת כל צליל - בדיוק במקומם
        was_voiced = voiced
        si = int(np.floor(s))
        ph = int(round((s - si) * PHASES))
        if ph == PHASES:
            si, ph = si + 1, 0
        s0, s1 = max(0, lo), min(n, lo + L)
        if ph == 0:                         # מיקום בדגימה שלמה - הקטע מועתק כמו שהוא
            seg = np.zeros(L)
            seg[s0 - lo:s1 - lo] = x[s0:s1]
        elif lo >= 0 and lo + L <= n:       # הזזה בשבר דגימה: seg[i] = x(lo + i - ph/PHASES)
            seg = np.correlate(xp[lo: lo + L + TAPS - 1], filt[ph], "valid")
        else:
            ext = np.zeros(L + TAPS - 1)
            e0, e1 = max(0, lo - half), min(n, lo + L + half - 1)
            ext[e0 - (lo - half): e1 - (lo - half)] = x[e0:e1]
            seg = np.correlate(ext, filt[ph], "valid")
        w = _hann(L)
        o = si - Pi
        d0, d1 = max(0, o), min(len(out), o + L)
        if d1 > d0:
            out[d0:d1] += (seg * w)[d0 - o:d1 - o]
            wsum[d0:d1] += w[d0 - o:d1 - o]
        if voiced:
            # המרחק עד המחזור הבא כפי שנמדד בהקלטה עצמה; בסוף צליל - לפי גובה הצליל שזוהה
            nxt = marks[k + 1] - a if (k + 1 < nm and periods[k + 1] != UNVOICED_P) else P
            if not 0.7 * P <= nxt <= 1.4 * P:
                nxt = P
            step = nxt / ratio[min(max(si, 0), n - 1)]
        else:
            step = P
        s += max(step, 8)
    out = out[:n] / np.maximum(wsum[:n], 0.25) * np.minimum(wsum[:n] / 0.25, 1)
    return out.astype(np.float32)
