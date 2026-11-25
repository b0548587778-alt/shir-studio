"""שילוב הקלטות: שרים את השיר שוב על אותו ליווי, והתוכנה בוחרת לכל משפט את הביצוע הנקי יותר.
שתי ההקלטות מיושרות בזמן (שתיהן מול אותו ליווי), ולכן אפשר להחליף משפט במשפט."""
from ..i18n import tx
import numpy as np
from scipy.ndimage import uniform_filter1d

from .fileio import SR, AudioError
from . import edit
from .pitch import yin

MARGIN = 3.0               # בכמה נקודות ההקלטה החדשה צריכה להיות טובה יותר כדי להחליף (שלא יהיו תפרים סתם)
MIN_VOICE = 0.6            # המשפט בהקלטה החדשה חייב להכיל לפחות 60% מהשירה שבמשפט המקורי
CLIP = 0.985


def _fit(x, n):
    x = np.asarray(x, dtype=np.float32)
    return x[:n] if len(x) >= n else np.concatenate([x, np.zeros(n - len(x), np.float32)])


def _env(x):
    """עוצמה לכל 10ms, ביחס לקטעים החזקים של אותה הקלטה."""
    n = len(x) // edit.HOP
    e = np.sqrt(np.mean(x[: n * edit.HOP].reshape(n, edit.HOP) ** 2, axis=1)) if n else np.zeros(0)
    return e / max(float(np.percentile(e, 95)) if n else 0.0, 1e-6)


def boundaries(old, new):
    """נקודות החיתוך בין המשפטים (בדגימות): בכל הפסקה - הרגע השקט ביותר בשתי ההקלטות יחד,
    כך שאף אחת מהן לא נחתכת באמצע צליל גם אם הזמר נכנס קצת מוקדם או מאוחר."""
    ph = edit.voice_phrases(old)
    if not ph:
        raise AudioError(tx("לא זיהיתי משפטים בהקלטה.\nאי אפשר לשלב בין ההקלטות."))
    quiet = _env(old) + _env(new)
    cuts = [0]
    for (_, e), (s, _) in zip(ph[:-1], ph[1:]):
        a, b = int(e * 100), max(int(s * 100), int(e * 100) + 1)
        a, b = min(a, len(quiet) - 1), min(b, len(quiet))
        cuts.append((a + int(np.argmin(quiet[a:b]))) * edit.HOP if b > a else a * edit.HOP)
    cuts.append(len(old))
    return cuts


def _loud_share(x):
    return float(np.mean(np.abs(x) >= CLIP)) if len(x) else 0.0


def best_of(old, new, scale=None, f0_old=None, progress=None):
    """old: ההקלטה שעובדים עליה. new: הקלטה נוספת של אותו שיר, מיושרת לאותו זמן.
    מחזיר (ההקלטה המשולבת, רשימה לכל משפט: {start, end, pick: 'old'/'new', old, new})."""
    from ..music.score import deviation, grade, frames
    rep = progress or (lambda p, m=None: None)
    old = np.asarray(old, dtype=np.float32)
    new = _fit(new, len(old))
    cuts = boundaries(old, new)
    rep(10, tx("מקשיב לשתי ההקלטות..."))
    if f0_old is None:
        f0_old = yin(old)[0]
    rep(40, None)
    f0_new = yin(new)[0]
    rep(80, tx("בוחר את הביצוע הנקי לכל משפט..."))
    d_old, d_new = deviation(f0_old, scale), deviation(f0_new, scale)
    # עוצמה אחת לכל ההקלטה החדשה (ולא לכל משפט) - כך הדינמיקה של הזמר נשמרת
    r_old, r_new = edit._active_rms(old), edit._active_rms(new)
    gain = np.float32(np.clip(r_old / r_new, 0.4, 2.5)) if (r_old > 0 and r_new > 0) else np.float32(1.0)
    picks, mask = [], np.zeros(len(old), dtype=np.float32)
    for a, b in zip(cuts[:-1], cuts[1:]):
        fa, fb = frames(a / SR, b / SR)
        so, sn = grade(d_old[fa:fb]), grade(d_new[fa:fb])
        sung_old = int(np.sum(~np.isnan(d_old[fa:fb])))
        sung_new = int(np.sum(~np.isnan(d_new[fa:fb])))
        if sn is not None:
            sn -= 400.0 * min(_loud_share(new[a:b]), 0.05)        # הקלטה 'שרופה' (חזקה מדי) מאבדת נקודות
        if so is not None:
            so -= 400.0 * min(_loud_share(old[a:b]), 0.05)
        take_new = sn is not None and sung_new >= MIN_VOICE * sung_old and (so is None or sn > so + MARGIN)
        if take_new:
            mask[a:b] = 1.0
        picks.append({"start": a / SR, "end": b / SR, "pick": "new" if take_new else "old", "old": so, "new": sn})
    if not mask.any():
        return old.copy(), picks
    mask = uniform_filter1d(mask, int(0.03 * SR), mode="nearest")   # מעבר רך של 30 אלפיות שנייה, בתוך השקט
    out = old * (1.0 - mask) + new * gain * mask
    rep(100, None)
    return np.ascontiguousarray(out, dtype=np.float32), picks


def summary(picks):
    """(כמה משפטים נלקחו מההקלטה החדשה, כמה נשארו מהקודמת)."""
    n = sum(1 for p in picks if p["pick"] == "new")
    return n, len(picks) - n
