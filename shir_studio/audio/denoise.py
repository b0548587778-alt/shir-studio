"""ניקוי רעשי רקע בשיטת 'שער ספקטרלי' (Spectral gating) - כתוב כאן מאפס, ללא תלות ברישיונות נוספים."""
import numpy as np
from scipy.signal import stft, istft, butter, sosfiltfilt, iirnotch, tf2sos
from scipy.ndimage import uniform_filter

from .fileio import SR

NFFT = 2048
HOP = 512
MAX_CUT_DB = 24.0         # בכמה דציבלים הרעש מונמך לכל היותר


def _highpass(x, cutoff=70.0):
    sos = butter(4, cutoff, btype="highpass", fs=SR, output="sos")
    return sosfiltfilt(sos, x).astype(np.float32)


def hum_frequencies(x, limit=1000.0):
    """מוצא זמזום של רשת החשמל (50 או 60 הרץ וההרמוניות שלו): קו דק וקבוע בספקטרום,
    שנמצא שם גם ברגעים השקטים. מחזיר את רשימת התדרים שיש לסנן."""
    n = 32768                                             # דיוק של 1.3 הרץ
    if len(x) < 3 * n:
        return []
    hop = n // 2
    win = np.hanning(n).astype(np.float32)
    k = min(60, (len(x) - n) // hop + 1)                  # עד 60 קטעים, מפוזרים על כל השיר
    starts = np.linspace(0, len(x) - n, k).astype(int)
    spec = np.stack([np.abs(np.fft.rfft(x[s0:s0 + n] * win)) ** 2 for s0 in starts])
    floor = np.percentile(spec, 20, axis=0)               # מה שנשאר גם כשהזמר שותק
    df = SR / n
    best = []
    for base in (50.0, 60.0):
        found = []
        for h in range(1, int(limit / base) + 1):
            i = int(round(base * h / df))
            lo, hi = max(1, i - int(18 / df)), i + int(18 / df)
            around = np.median(np.concatenate([floor[lo:i - 3], floor[i + 4:hi]]))
            if floor[i - 1:i + 2].max() > 30 * around + 1e-12:        # בולט ב-15dB מעל הסביבה
                found.append(base * h)
        if found and (found[0] <= 3 * base) and (len(found) >= 2 or found[0] == base) and len(found) > len(best):
            best = found
    return best


def remove_hum(x):
    """מסנן את זמזום החשמל במסננים צרים מאוד (4 הרץ) - הקול כמעט לא מושפע."""
    freqs = hum_frequencies(x)
    y = np.asarray(x, dtype=np.float64)
    for f in freqs:
        b, a = iirnotch(f, f / 4.0, fs=SR)
        y = sosfiltfilt(tf2sos(b, a), y)
    return y.astype(np.float32), freqs


BLOCK = 20 * SR       # עיבוד בקטעים של 20 שניות - שיר ארוך לא ימלא את הזיכרון
MARGIN = SR           # שנייה של חפיפה בכל צד, כדי שלא יהיו 'תפרים'


def _blocks(n):
    for s0 in range(0, n, BLOCK):
        e0 = min(n, s0 + BLOCK)
        yield s0, e0, max(0, s0 - MARGIN), min(n, e0 + MARGIN)


def _spec(seg):
    _, _, Z = stft(seg, fs=SR, nperseg=NFFT, noverlap=NFFT - HOP)
    return Z.astype(np.complex64)


def denoise(x: np.ndarray, strength: float = 1.0, progress=None) -> np.ndarray:
    """strength: 0 (בלי ניקוי) עד 1 (ניקוי מלא)."""
    x, _ = remove_hum(x)
    x = _highpass(x)
    n = len(x)
    if progress:
        progress(10)
    # שלב 1: פרופיל הרעש = 15% מהפריימים השקטים ביותר בכל השיר
    cols, energies, total = [], [], 0
    for s0, e0, a0, a1 in _blocks(n):
        mag = np.abs(_spec(x[a0:a1]))
        k0, k1 = (s0 - a0) // HOP, (e0 - a0) // HOP + 1     # רק החלק המרכזי של הקטע
        mag = mag[:, k0:k1]
        en = np.mean(mag ** 2, axis=0)
        total += len(en)
        keep = np.argsort(en)[: max(5, int(0.3 * len(en)))]
        cols.append(mag[:, keep])
        energies.append(en[keep])
    cols = np.concatenate(cols, axis=1)
    energies = np.concatenate(energies)
    quiet = np.argsort(energies)[: max(5, int(0.15 * total))]
    qdb = 20 * np.log10(cols[:, quiet].astype(np.float64) + 1e-10)
    thresh = (qdb.mean(axis=1, keepdims=True) + 1.5 * qdb.std(axis=1, keepdims=True) + 6.0).astype(np.float32)
    del cols, qdb
    if progress:
        progress(40)
    # שלב 2: ניקוי כל קטע
    floor = 10 ** (-(MAX_CUT_DB * strength) / 20)  # ההנחתה המקסימלית של הרעש
    y = np.zeros(n, np.float32)
    for s0, e0, a0, a1 in _blocks(n):
        Z = _spec(x[a0:a1])
        mag = np.abs(Z)
        db = 20 * np.log10(mag + 1e-10)
        # מסכה רכה - מעבר הדרגתי ולא חד, כדי למנוע צלילים מתכתיים
        mask = 1.0 / (1.0 + np.exp(-(db - thresh) / 3.0))
        mask = uniform_filter(mask, size=(3, 5))
        gain = floor + (1 - floor) * mask
        gain = 1 - strength * (1 - gain)
        gain = gain * _dereverb_gain(mag, strength)
        _, seg = istft(Z * gain, fs=SR, nperseg=NFFT, noverlap=NFFT - HOP)
        seg = seg[: a1 - a0]
        y[s0:e0] = seg[s0 - a0: s0 - a0 + (e0 - s0)]
    if progress:
        progress(90)
    return normalize(y)


def _dereverb_gain(mag, strength, t60=0.3, delay_frames=4, amount=0.6):
    """הפחתת הד החדר (שיטת Lebart): ההד המאוחר = האנרגיה של לפני ~50ms, דועכת לפי זמן ההדהוד.
    צליל ארוך ויציב מקבל הנחתה אחידה (לא מורגשת), וזנב ההד אחרי שהצליל נגמר - מוחלש."""
    if strength <= 0:
        return 1.0
    p = uniform_filter(mag ** 2, size=(1, 3))
    dt = delay_frames * HOP / SR
    late = np.zeros_like(p)
    late[:, delay_frames:] = p[:, :-delay_frames] * np.exp(-2 * 6.9 * dt / (2 * t60))
    g = np.sqrt(np.clip(1 - amount * strength * late / (p + 1e-12), 0, 1))
    g = np.maximum(g, 10 ** (-10 / 20))         # לכל היותר 10dB - שלא יישמע 'מתכתי'
    return uniform_filter(g, size=(3, 3))


def normalize(y: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    peak = np.max(np.abs(y))
    if peak < 1e-6:
        return y
    return (y * (10 ** (peak_db / 20) / peak)).astype(np.float32)
