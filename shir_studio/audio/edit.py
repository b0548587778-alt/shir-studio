"""עריכת ההקלטה לפי משפטים: הקלטה מחדש של משפט אחד, שכפול משפט (חזרה) ומחיקת משפט."""
import numpy as np

from .fileio import SR

FADE = int(0.015 * SR)


def regions(a, n_samples):
    """מחלק את ההקלטה למשפטים. לכל משפט: החלק המושר (start, end) והאזור כולו כולל ההפסקות (a, b), בשניות.
    הגבולות בין המשפטים באמצע ההפסקה, ובשיר בקצב קבוע - על פעמה (כדי שחזרה או מחיקה לא ישברו את הקצב)."""
    from ..music.analysis import voice_phrases
    ph = voice_phrases(a)
    total = n_samples / SR
    if not ph:
        return []
    cuts = [0.0]
    for (_, e1), (s2, _) in zip(ph, ph[1:]):
        c = (e1 + s2) / 2
        if a.steady and len(a.beats):
            inside = [b for b in a.beats if e1 + 0.03 < b < s2 - 0.03]
            if inside:
                c = min(inside, key=lambda b: abs(b - c))
        cuts.append(float(c))
    cuts.append(total)
    return [{"start": s, "end": min(e, total), "a": cuts[i], "b": cuts[i + 1]} for i, (s, e) in enumerate(ph)]


def trim(x, db=-32.0, margin=0.03):
    """מסיר שקט בהתחלה ובסוף של הקלטה."""
    x = np.asarray(x, dtype=np.float32)
    hop = 441
    n = len(x) // hop
    if n < 3:
        return x
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))
    loud = np.where(rms > rms.max() * 10 ** (db / 20))[0]
    if not len(loud):
        return x
    m = int(margin * SR)
    return x[max(0, loud[0] * hop - m): min(len(x), (loud[-1] + 1) * hop + m)]


def _fade(x):
    x = np.array(x, dtype=np.float32)
    k = min(FADE, len(x) // 2)
    if k > 0:
        r = np.linspace(0, 1, k, dtype=np.float32)
        x[:k] *= r
        x[-k:] *= r[::-1]
    return x


def _rms(x):
    x = np.asarray(x, dtype=np.float64)
    if not len(x):
        return 0.0
    loud = np.abs(x) > np.abs(x).max() * 0.05
    return float(np.sqrt(np.mean(x[loud] ** 2))) if loud.any() else 0.0


def replace_phrase(raw, region, take):
    """מחליף משפט בהקלטה חדשה. אורך השיר לא משתנה, כדי שהקצב והליווי יישארו במקום:
    ההקלטה החדשה מתחילה ברגע שבו התחיל המשפט המקורי, ואם היא ארוכה מדי - נחתכת בעדינות."""
    raw = np.array(raw, dtype=np.float32)
    take = trim(take)
    i0 = int(region["a"] * SR)
    i1 = min(len(raw), int(region["b"] * SR))
    s = min(max(i0, int(region["start"] * SR) - int(0.03 * SR)), i1)
    old = raw[s:int(region["end"] * SR)]
    g = _rms(old) / _rms(take) if _rms(take) > 1e-6 and _rms(old) > 1e-6 else 1.0
    take = _fade(take[: max(0, i1 - s)] * float(np.clip(g, 0.1, 10.0)))
    e = min(i1, max(int(region["end"] * SR) + int(0.03 * SR), s + len(take)))
    # מעמעמים את השירה הישנה (מעבר רך בקצוות) ומניחים במקומה את החדשה
    k = min(FADE, (e - s) // 2)
    w = np.zeros(e - s, dtype=np.float32)
    if k > 0:
        w[:k] = np.linspace(1, 0, k)
        w[-k:] = np.linspace(0, 1, k)
    raw[s:e] *= w
    raw[s:s + len(take)] += take
    return raw


def duplicate_phrase(raw, region):
    """שר את המשפט פעם נוספת מיד אחריו (חזרה)."""
    raw = np.asarray(raw, dtype=np.float32)
    i0, i1 = int(region["a"] * SR), min(len(raw), int(region["b"] * SR))
    seg = _fade(raw[i0:i1])
    return np.concatenate([raw[:i0], seg, seg, _fade(raw[i1:]) if i1 < len(raw) else raw[i1:]])


def delete_phrase(raw, region):
    """מוחק משפט מההקלטה."""
    raw = np.asarray(raw, dtype=np.float32)
    i0, i1 = int(region["a"] * SR), min(len(raw), int(region["b"] * SR))
    head = _fade(raw[:i0]) if i0 else raw[:i0]
    tail = _fade(raw[i1:]) if i1 < len(raw) else raw[i1:]
    return np.concatenate([head, tail])
