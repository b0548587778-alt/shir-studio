"""עוצמה לפי התקן הבין-לאומי (ITU-R BS.1770, יחידות LUFS) - כמו ברדיו ובאתרי המוזיקה,
ושיא אמיתי (True Peak) - שהשיר לא 'ייחתך' גם אחרי המרה ל-MP3."""
from ..i18n import tx
import numpy as np
from scipy.signal import sosfilt, resample_poly

from .fileio import SR

# עוצמת השיר המוכן: רגיל = כמו באתרי המוזיקה, חזק = כמו דיסק, עדין = דינמי ושקט יותר
TARGETS = {"soft": -18.0, "normal": -14.0, "loud": -11.0}
NAMES = {"normal": tx("רגילה (כמו באתרי המוזיקה)"), "loud": tx("חזקה (כמו דיסק)"), "soft": tx("עדינה (דינמית יותר)")}
PEAK_DB = -1.0


def _k_weighting():
    """שני המסננים של התקן: הגבהת הגבוהים (כמו האוזן) וחיתוך הנמוכים מאוד - מחושבים לקצב הדגימה שלנו."""
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = np.tan(np.pi * f0 / SR)
    Vh = 10 ** (G / 20)
    Vb = Vh ** 0.4996667741545416
    a0 = 1 + K / Q + K * K
    shelf = [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0,
             1.0, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = np.tan(np.pi * f0 / SR)
    a0 = 1 + K / Q + K * K
    hp = [1.0, -2.0, 1.0, 1.0, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    return np.array([shelf, hp])


_SOS = _k_weighting()


def lufs(x):
    """העוצמה הכוללת של שיר (Integrated Loudness). מחזיר -inf כשאין מספיק צליל למדידה."""
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        x = x[:, None]
    hop = int(0.1 * SR)
    nseg = len(x) // hop
    if nseg < 4:
        return float("-inf")
    power = np.zeros(nseg)
    for c in range(x.shape[1]):                       # ערוץ אחרי ערוץ - חוסך זיכרון
        y = sosfilt(_SOS, x[: nseg * hop, c].astype(np.float64))
        power += np.mean(np.square(y).reshape(nseg, hop), axis=1)
    # בלוקים של 0.4 שנייה בחפיפה של 75%
    z = (power[:-3] + power[1:-2] + power[2:-1] + power[3:]) / 4
    loud = -0.691 + 10 * np.log10(z + 1e-12)
    z = z[loud > -70]
    if not len(z):
        return float("-inf")
    rel = -0.691 + 10 * np.log10(z.mean() + 1e-12) - 10
    z = z[-0.691 + 10 * np.log10(z + 1e-12) > rel]
    if not len(z):
        return float("-inf")
    return float(-0.691 + 10 * np.log10(z.mean() + 1e-12))


def true_peak(x, chunk=SR * 8):
    """השיא האמיתי של הגל, גם בין הדגימות (דגימת יתר פי 4)."""
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        x = x[:, None]
    pad = 64
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    for s in range(0, len(x), chunk):
        seg = x[max(0, s - pad): s + chunk + pad]
        for c in range(seg.shape[1]):
            peak = max(peak, float(np.max(np.abs(resample_poly(seg[:, c], 4, 1)))))
    return peak


def finalize(st, target="normal", limiter=None):
    """מביא את השיר לעוצמה המבוקשת ושומר על שיא אמיתי בטוח. מחזיר (שיר, פי כמה הוגבר)."""
    goal = TARGETS.get(target, TARGETS["normal"]) if isinstance(target, str) else float(target)
    total = 1.0
    for _ in range(12):                # עיבוד עם שיא גדול (תזמורת שמתפתחת) צריך כמה סיבובים של הגבלה
        cur = lufs(st)
        if not np.isfinite(cur):
            break
        diff = float(np.clip(goal - cur, -24, 12))
        if abs(diff) < 0.25:
            break
        g = np.float32(10 ** (diff / 20))
        st = st * g
        total *= float(g)
        if g > 1 and limiter is not None:
            st = limiter(st)
    ceiling = 10 ** (PEAK_DB / 20)
    if limiter is not None:
        # שיא אמיתי גבוה מדי: מגבילים רק את השיאים עצמם (ולא מנמיכים את כל השיר) - כך העוצמה שהושגה נשמרת
        for _ in range(4):
            tp = true_peak(st)
            if tp <= ceiling:
                break
            st = limiter(st, float(np.max(np.abs(st)) * ceiling / tp * 0.985))
    tp = true_peak(st)
    if tp > ceiling:
        g = np.float32(ceiling / tp)
        st = st * g
        total *= float(g)
    return st.astype(np.float32), total
