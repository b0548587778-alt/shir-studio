"""זיהוי גובה הצליל (YIN) - מימוש עצמי."""
import numpy as np
from scipy.signal import resample_poly, medfilt

from .fileio import SR

ASR = 16000          # קצב דגימה לניתוח
HOP = 160            # 10ms
FRAME = 1024
FMIN, FMAX = 65.0, 1000.0
FRAME_SEC = HOP / ASR


def yin(x: np.ndarray):
    """מחזיר (f0 בהרץ לכל 10ms, 0 = אין צליל, ביטחון 0..1)."""
    y = resample_poly(x, 160, 441).astype(np.float64)
    tau_max = int(ASR / FMIN) + 2
    tau_min = int(ASR / FMAX)
    W = FRAME - tau_max
    n_frames = max(1, 1 + (len(y) - FRAME) // HOP)
    pad = np.pad(y, (0, FRAME))
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n_frames)[:, None]
    fr = pad[idx]                                    # (n, FRAME)
    out_f0 = np.zeros(n_frames)
    out_conf = np.zeros(n_frames)
    rms = np.sqrt(np.mean(fr[:, :W] ** 2, axis=1))
    gate = np.max(rms) * 10 ** (-40 / 20)
    B = 2048
    for s in range(0, n_frames, B):
        f = fr[s:s + B]
        F = np.fft.rfft(f, 2 * FRAME)
        Fw = np.fft.rfft(f[:, :W], 2 * FRAME)
        r = np.fft.irfft(np.conj(Fw) * F, 2 * FRAME)[:, :tau_max]   # sum x[j] x[j+tau], j<W
        sq = np.cumsum(f ** 2, axis=1)
        sq = np.concatenate([np.zeros((len(f), 1)), sq], axis=1)
        e0 = sq[:, W][:, None]
        taus = np.arange(tau_max)
        e_tau = sq[:, taus + W] - sq[:, taus]
        d = e0 + e_tau - 2 * r
        d[:, 0] = 0
        cs = np.cumsum(d[:, 1:], axis=1) / np.arange(1, tau_max)
        cm = np.ones_like(d)
        cm[:, 1:] = d[:, 1:] / np.maximum(cs, 1e-12)
        for i in range(len(f)):
            c = cm[i]
            below = np.where(c[tau_min:] < 0.15)[0]
            if len(below):
                t = below[0] + tau_min
                while t + 1 < tau_max and c[t + 1] < c[t]:
                    t += 1
            else:
                t = tau_min + int(np.argmin(c[tau_min:]))
            conf = 1 - c[t]
            if 1 <= t < tau_max - 1:
                a, b, cc = c[t - 1], c[t], c[t + 1]
                den = a - 2 * b + cc
                tt = t + (0.5 * (a - cc) / den if abs(den) > 1e-12 else 0)
            else:
                tt = t
            fi = s + i
            out_conf[fi] = conf
            if c[t] < 0.3 and rms[fi] > gate:
                out_f0[fi] = ASR / tt
    out_f0 = _clean(out_f0)
    return out_f0, out_conf


def _clean(f0):
    """מסלק קפיצות אוקטבה ונקודות בודדות."""
    f0 = f0.copy()
    voiced = f0 > 0
    if voiced.sum() < 5:
        return f0
    m = np.log2(np.where(voiced, f0, 1))
    ref = medfilt(np.where(voiced, m, np.median(m[voiced])), 31)
    for k in (-1, 1):
        fix = voiced & (np.abs(m - ref - k) < 0.25)
        m[fix] -= k
    f0 = np.where(voiced, 2 ** m, 0)
    # הסרת קטעי צליל קצרים מ-40ms
    v = f0 > 0
    i = 0
    n = len(v)
    while i < n:
        if v[i]:
            j = i
            while j < n and v[j]:
                j += 1
            if j - i < 4:
                f0[i:j] = 0
            i = j
        else:
            i += 1
    return f0


def hz_to_midi(f):
    return 69 + 12 * np.log2(np.maximum(f, 1e-6) / 440.0)


def midi_to_hz(m):
    return 440.0 * 2 ** ((np.asarray(m) - 69) / 12)
