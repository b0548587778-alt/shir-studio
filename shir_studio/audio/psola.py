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


def shift(x: np.ndarray, f0: np.ndarray, semitones: np.ndarray) -> np.ndarray:
    """semitones: תיקון בחצאי טונים לכל פריים של 10ms (0 = ללא שינוי)."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    marks, periods, v = analysis_marks(x, f0)
    ratio = 2 ** (_per_sample(semitones, n) / 12)
    out = np.zeros(n + 4 * SR // 100)
    wsum = np.zeros_like(out)
    s = float(marks[0])
    k = 0
    nm = len(marks)
    while s < n:
        si = int(s)
        while k + 1 < nm and abs(marks[k + 1] - si) < abs(marks[k] - si):
            k += 1
        a = marks[k]
        P = periods[k]
        voiced = v[min(a, n - 1)] and P != UNVOICED_P
        Pi = int(P)
        L = 2 * Pi + 1
        lo = a - Pi
        seg = np.zeros(L)
        s0, s1 = max(0, lo), min(n, lo + L)
        seg[s0 - lo:s1 - lo] = x[s0:s1]
        w = _hann(L)
        o = si - Pi
        d0, d1 = max(0, o), min(len(out), o + L)
        out[d0:d1] += (seg * w)[d0 - o:d1 - o]
        wsum[d0:d1] += w[d0 - o:d1 - o]
        step = P / ratio[si] if voiced else P
        s += max(step, 8)
    out = out[:n] / np.maximum(wsum[:n], 0.25) * np.minimum(wsum[:n] / 0.25, 1)
    # שמירת מעטפת העוצמה המקורית בערך
    return out.astype(np.float32)
