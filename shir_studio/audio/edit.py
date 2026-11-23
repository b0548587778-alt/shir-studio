"""עריכת ההקלטה לפני העיבוד: חיתוך שקט, גזירת קטע, והחלפת משפט אחד בהקלטה חדשה."""
import numpy as np

from .fileio import SR, AudioError

HOP = SR // 100            # 10ms


def _mask(x):
    """לכל 10ms: האם יש שם קול (ולא רק רעש רקע)."""
    x = np.asarray(x, dtype=np.float32)
    n = len(x) // HOP
    if n < 4:
        return np.zeros(max(n, 0), bool)
    e = np.sqrt(np.mean(x[: n * HOP].reshape(n, HOP) ** 2, axis=1))
    e = np.maximum(e, np.concatenate([e[1:], e[-1:]]))                # חלון של 20ms
    ref, floor = np.percentile(e, 95), np.percentile(e, 10)
    if ref < 1e-5:
        return np.zeros(n, bool)
    m = e > max(ref * 0.06, min(floor * 3, ref * 0.3))
    return _clean(m, fill=15, drop=8)


def _runs(m):
    d = np.diff(np.concatenate([[0], m.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def _clean(m, fill, drop):
    """סוגר הפסקות קצרצרות ומוחק 'נקישות' קצרות."""
    m = m.copy()
    for s, e in _runs(~m):
        if e - s < fill and s > 0 and e < len(m):
            m[s:e] = True
    for s, e in _runs(m):
        if e - s < drop:
            m[s:e] = False
    return m


def voice_phrases(x, min_gap=0.35, min_len=0.3):
    """משפטי השירה: [(התחלה, סוף)] בשניות - קטעי קול שביניהם שקט."""
    m = _clean(_mask(x), fill=int(min_gap * 100), drop=int(min_len * 100))
    return [(s / 100, e / 100) for s, e in _runs(m)]


def auto_trim_range(x, margin=0.3):
    """(התחלה, סוף) בשניות: בלי השקט שלפני השירה ואחריה."""
    dur = len(x) / SR
    ph = voice_phrases(x, min_len=0.15)
    if not ph:
        return 0.0, dur
    return max(0.0, ph[0][0] - margin), min(dur, ph[-1][1] + margin)


def _fade(x, sec=0.012):
    k = min(int(sec * SR), len(x) // 2)
    if k > 0:
        x[:k] *= np.linspace(0, 1, k, dtype=np.float32)
        x[-k:] *= np.linspace(1, 0, k, dtype=np.float32)
    return x


def cut(x, start, end):
    """גוזר קטע מההקלטה (בשניות), עם כניסה ויציאה רכות."""
    a, b = max(0, int(start * SR)), min(len(x), int(end * SR))
    if b - a < 2 * SR:
        raise AudioError("הקטע שנבחר קצר מדי.\nצריך לפחות שתי שניות של שירה.")
    return _fade(np.array(x[a:b], dtype=np.float32))


def phrase_slots(x):
    """לכל משפט: (התחלה, סוף, תחילת המקום, סוף המקום). 'המקום' = מה שמוחלף בהקלטה מחדש,
    כולל השקט שאחרי המשפט - כדי שהקלטה קצת ארוכה יותר לא תיחתך."""
    ph = voice_phrases(x)
    dur = len(x) / SR
    out = []
    for i, (s, e) in enumerate(ph):
        lo = max(ph[i - 1][1] + 0.05 if i else 0.0, s - 0.15)
        hi = ph[i + 1][0] - 0.1 if i + 1 < len(ph) else dur
        out.append((s, e, lo, max(hi, e)))
    return out


def _active_rms(x):
    m = _mask(x)
    if not m.any():
        return 0.0
    sel = np.repeat(m, HOP)
    return float(np.sqrt(np.mean(x[: len(sel)][sel] ** 2)))


def splice_take(raw, slot_start, slot_end, take):
    """מחליף משפט אחד בהקלטה חדשה. ההקלטה החדשה מיושרת לפי תחילת השירה,
    כך ששאר השיר נשאר בדיוק במקומו (אותו אורך, אותו קצב)."""
    raw = np.asarray(raw, dtype=np.float32)
    take = np.asarray(take, dtype=np.float32)
    i0, i1 = max(0, int(slot_start * SR)), min(len(raw), int(slot_end * SR))
    ph = voice_phrases(take, min_len=0.15)
    if i1 - i0 < SR // 4 or not ph:
        raise AudioError("לא שמעתי שירה בהקלטה החדשה.\nנסה שוב, קרוב יותר למיקרופון.")
    pad = int(0.08 * SR)
    seg = np.array(take[max(0, int(ph[0][0] * SR) - pad): int(ph[-1][1] * SR) + pad], dtype=np.float32)
    old = raw[i0:i1]
    old_ph = voice_phrases(old, min_len=0.15)
    on_old = int(old_ph[0][0] * SR) if old_ph else pad
    pos = max(i0, i0 + on_old - pad)
    seg = seg[: max(0, i1 - pos)]
    # אותה עוצמה כמו המשפט המקורי - שלא יורגש 'תפר'
    r_new, r_old = _active_rms(seg), _active_rms(old)
    if r_new > 0 and r_old > 0:
        seg *= np.float32(np.clip(r_old / r_new, 0.3, 3.0))
    out = raw.copy()
    hole = np.ones(i1 - i0, dtype=np.float32)
    k = min(int(0.02 * SR), len(hole) // 2)
    hole[:k], hole[-k:] = np.linspace(1, 0, k), np.linspace(0, 1, k)
    hole[k:-k] = 0
    out[i0:i1] *= hole
    out[pos:pos + len(seg)] += _fade(seg, 0.02)
    return out
