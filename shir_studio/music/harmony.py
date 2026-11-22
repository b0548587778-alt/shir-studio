"""קול שני (הרמוניה): עותק של קול הזמר, מוזז לצליל שמתאים לאקורד - כמו מקהלה של זמר אחד."""
import numpy as np
from scipy.ndimage import gaussian_filter1d

from ..audio.pitch import FRAME_SEC
from .theory import MODES


def _scale7(tonic, mode):
    steps = [0, 2, 3, 5, 7, 8, 10] if mode == "minor" else MODES[mode][1]
    return {(tonic + d) % 12 for d in steps}


def _chord_at(chords, t):
    for s, e, c in chords:
        if s - 0.05 <= t < e:
            return c
    return chords[-1][2] if chords else None


def harmony_shift(a, mode="auto"):
    """מחזיר הזזה בחצאי טונים לכל פריים (מעבר לתיקון הרגיל) עבור הקול השני."""
    shift = np.full(len(a.f0), np.nan)
    scale = _scale7(a.tonic, a.mode)
    prev = 4.0
    for nt in a.notes:
        m = int(round(nt.pitch))
        ch = _chord_at(a.chords, (nt.start + nt.end) / 2)
        below = mode == "below" or (mode == "auto" and m + a.transpose > 76)
        cands = (-3, -4, -5) if below else (3, 4, 5)
        d = None
        if nt.end - nt.start < 0.15:
            d = prev                       # צלילים קצרים - ממשיכים את ההרמוניה הקודמת
        if d is None and ch is not None:
            for c in cands[:2] + cands[2:]:
                if (m + c) % 12 in ch["pcs"] and (m + c) % 12 in scale | set(ch["pcs"]):
                    d = c
                    break
        if d is None:
            for c in cands[:2]:
                if (m + c) % 12 in scale:
                    d = c
                    break
        if d is None:
            d = cands[0]
        prev = d
        i0, i1 = int(round(nt.start / FRAME_SEC)), int(round(nt.end / FRAME_SEC))
        shift[i0:i1] = d
    # מילוי פערים בערך הקרוב והחלקה
    idx = np.arange(len(shift))
    ok = ~np.isnan(shift)
    if not ok.any():
        return np.zeros(len(shift))
    shift = np.interp(idx, idx[ok], shift[ok])
    return gaussian_filter1d(shift, 4)
