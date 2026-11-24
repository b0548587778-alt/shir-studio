"""ציון דיוק לשירה: כמה קרוב הזמר לצלילים הנקיים. משמש את מצב התרגול (ציון לכל משפט)
ואת שילוב ההקלטות (באיזו הקלטה המשפט יצא נקי יותר)."""
import numpy as np
from scipy.ndimage import median_filter

from ..audio.pitch import FRAME_SEC, hz_to_midi
from .analysis import _snap

FULL_MISS = 0.5            # סטייה של רבע טון ומעלה = צליל שלא נחשב מדויק בכלל


def own_tuning(midi):
    """הסטייה הקבועה של הזמר מהכיוון התקני (בחצאי טונים, בין חצי- לחצי+).
    זמר ששר בלי ליווי לא חייב להיות מכוון ל-A440 - ואין סיבה להוריד לו על זה ציון."""
    midi = np.asarray(midi, dtype=float)
    if not len(midi):
        return 0.0
    return float(np.angle(np.sum(np.exp(2j * np.pi * (midi - np.round(midi))))) / (2 * np.pi))


def deviation(f0, scale=None):
    """לכל 10ms: הסטייה (בחצאי טונים, עם סימן) מהצליל הנקי הקרוב. NaN = אין שם צליל.
    הוויברטו מוחלק קודם, כך שנמדד מרכז הצליל ולא התנודה סביבו."""
    f0 = np.asarray(f0, dtype=float)
    voiced = f0 > 0
    out = np.full(len(f0), np.nan)
    if voiced.sum() < 5:
        return out
    midi = hz_to_midi(np.where(voiced, f0, 440.0))
    idx = np.arange(len(f0))
    filled = np.interp(idx, idx[voiced], midi[voiced])
    centre = median_filter(filled, 21, mode="nearest")           # חלון של 0.2 שניות = מחזור ויברטו שלם
    centre = centre - own_tuning(centre[voiced])
    scale = set(scale) if scale is not None else set(range(12))
    target = np.array([_snap(c, scale) for c in centre[voiced]], dtype=float)
    out[voiced] = centre[voiced] - target
    return out


def grade(dev):
    """ציון 0-100 לקטע: 100 = כל הצלילים במקומם, 0 = סטייה של רבע טון ומעלה בכל צליל.
    None כשאין בקטע מספיק שירה כדי לתת ציון."""
    d = np.asarray(dev, dtype=float)
    d = d[~np.isnan(d)]
    if len(d) < 8:
        return None
    return float(100.0 * (1.0 - np.mean(np.minimum(np.abs(d), FULL_MISS)) / FULL_MISS))


def frames(start, end):
    """טווח הפריימים (של 10ms) שמתאים לקטע בשניות."""
    return int(round(start / FRAME_SEC)), max(int(round(end / FRAME_SEC)), int(round(start / FRAME_SEC)) + 1)


def phrase_report(analysis, slots):
    """למצב התרגול: לכל משפט - ציון, נטייה (לרדת / לעלות) והצליל שהכי רחוק ממקומו.
    slots: [(התחלה, סוף, ...)] בשניות. נמדד לפי הצלילים שהתוכנה זיהתה, ביחס לכיוון של הזמר עצמו."""
    from . import theory
    scale = theory.scale_pcs(analysis.tonic, analysis.mode)
    out = []
    for sl in slots:
        s, e = sl[0], sl[1]
        notes = [nt for nt in analysis.notes if nt.end > s and nt.start < e]
        w = np.array([max(min(nt.end, e) - max(nt.start, s), 0.01) for nt in notes])
        dev = np.array([nt.pitch - _snap(nt.pitch, scale) for nt in notes])
        if not len(notes):
            out.append({"score": None, "cents": 0.0, "worst": None, "text": "לא זוהו צלילים"})
            continue
        score = 100.0 * (1.0 - float(np.average(np.minimum(np.abs(dev), FULL_MISS), weights=w)) / FULL_MISS)
        cents = 100.0 * float(np.average(dev, weights=w))
        k = int(np.argmax(np.abs(dev) * (w > 0.12)))             # צליל קצרצר לא נחשב 'הכי רחוק'
        worst = (notes[k].start, 100.0 * float(dev[k])) if abs(dev[k]) >= 0.2 else None
        out.append({"score": score, "cents": cents, "worst": worst, "text": _advice(score, cents)})
    return out


def _advice(score, cents):
    if score >= 88:
        text = "מדויק מאוד"
    elif score >= 72:
        text = "טוב"
    else:
        text = "כדאי לתרגל"
    if cents <= -12:
        text += " · נוטה לרדת"
    elif cents >= 12:
        text += " · נוטה לעלות"
    return text


def overall(report, slots):
    """הציון של השיר כולו (ממוצע לפי אורך המשפטים), או None."""
    pairs = [(r["score"], sl[1] - sl[0]) for r, sl in zip(report, slots) if r["score"] is not None]
    if not pairs:
        return None
    return float(np.average([p[0] for p in pairs], weights=[max(p[1], 0.1) for p in pairs]))
