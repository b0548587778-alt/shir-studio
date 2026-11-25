"""ליטוש הקול: הסרת 'קליקים', ריכוך פיצוצי פ' ו-ב' מול המיקרופון, ואופי הקול (חם / בהיר / רדיו)."""
from ..i18n import tx
import numpy as np
from scipy.signal import butter, sosfiltfilt
from scipy.interpolate import CubicSpline
from scipy.ndimage import uniform_filter1d, maximum_filter1d

from .fileio import SR

TONES = {"natural": tx("טבעי"), "warm": tx("חם ורך"), "bright": tx("בהיר וצלול"), "radio": tx("רדיו (חד וקרוב)")}


def declick(v, sensitivity=9.0):
    """מסיר 'קליקים' קצרים (רעשי פה, נגיעה במיקרופון, חיבור רופף): קפיצה חדה של עד 2 אלפיות שנייה
    מוחלפת בקו חלק. מחזיר (קול, כמה קליקים תוקנו)."""
    v = np.asarray(v, dtype=np.float32)
    if len(v) < SR // 10:
        return v, 0
    d = np.zeros(len(v), np.float32)
    d[1:-1] = np.abs(v[2:] - 2 * v[1:-1] + v[:-2])           # 'חדות' הגל בכל נקודה
    # הרקע: החדות הרגילה סביב הנקודה (30 אלפיות שנייה) - שריקות ועיצורים מעלים אותו, קליק בודד לא
    around = uniform_filter1d(d, int(0.03 * SR)) + 1e-7
    floor = np.percentile(d, 99) * 0.25
    bad = (d > sensitivity * around) & (d > floor)
    if not bad.any():
        return v, 0
    w = 3
    bad = maximum_filter1d(bad.astype(np.uint8), 2 * w + 1).astype(bool)
    edges = np.diff(np.concatenate([[0], bad.astype(np.int8), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    out = v.copy()
    fixed = 0
    for s, e in zip(starts, ends):
        if e - s > int(0.002 * SR) or s < 8 or e > len(v) - 8:     # ארוך מדי = לא קליק אלא צליל אמיתי
            continue
        # קו חלק (ספליין) דרך הדגימות התקינות משני הצדדים - ממשיך את הגל במקום לחתוך אותו
        xs = np.concatenate([np.arange(s - 6, s), np.arange(e, e + 6)])
        out[s:e] = CubicSpline(xs, out[xs])(np.arange(s, e))
        fixed += 1
    return out, fixed


def deplosive(v, cutoff=120.0, ratio=2.5):
    """מרכך 'פיצוצים' של פ' ו-ב' (משב אוויר על המיקרופון): פרץ של צליל נמוך מאוד שאין מולו שירה -
    רק הנמוכים מונמכים, ורק ברגע הפיצוץ."""
    v = np.asarray(v, dtype=np.float32)
    if len(v) < SR // 5:
        return v
    lo = sosfiltfilt(butter(2, cutoff, fs=SR, output="sos"), v).astype(np.float32)
    mid = sosfiltfilt(butter(2, [cutoff * 1.5, 1200], btype="band", fs=SR, output="sos"), v).astype(np.float32)
    w = int(0.015 * SR)
    e_lo = np.sqrt(uniform_filter1d(lo ** 2, w) + 1e-12)
    e_mid = np.sqrt(uniform_filter1d(mid ** 2, w) + 1e-12)
    strong = e_lo > np.percentile(e_lo, 95) * 0.5                 # רק פרצים חזקים באמת
    g = np.where(strong, np.clip(ratio * e_mid / e_lo, 0.2, 1.0), 1.0)
    g = uniform_filter1d(g.astype(np.float32), int(0.01 * SR))
    return (v - lo + lo * g).astype(np.float32)


def clean_up(v):
    """ליטוש ההקלטה אחרי ניקוי הרעשים."""
    v, _ = declick(v)
    return deplosive(v)


def tone(v, kind="natural"):
    """אופי הקול - צביעה עדינה באקולייזר, מעל העיבוד הרגיל."""
    if kind in (None, "natural") or kind not in TONES:
        return v
    from .mix import _peaking
    f32 = lambda z: np.asarray(z, dtype=np.float32)
    if kind == "warm":
        v = f32(_peaking(v, 190, 2.5, 0.8))
        v = f32(_peaking(v, 3600, -1.5, 0.9))
        v = f32(_peaking(v, 9500, -2.5, 0.7))
    elif kind == "bright":
        v = f32(_peaking(v, 260, -1.5, 0.9))
        v = f32(_peaking(v, 4800, 2.5, 0.8))
        v = f32(_peaking(v, 11500, 3.0, 0.7))
    elif kind == "radio":
        v = f32(sosfiltfilt(butter(2, 140, btype="high", fs=SR, output="sos"), v))
        v = f32(_peaking(v, 320, -3.0, 0.9))
        v = f32(_peaking(v, 2600, 4.0, 0.8))
        v = f32(_peaking(v, 7500, 1.5, 0.8))
    return v
