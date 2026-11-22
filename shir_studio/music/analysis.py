"""ניתוח השירה: כיוון, סולם, תיקון זיופים, תווים, קצב ואקורדים."""
from dataclasses import dataclass, field
import numpy as np
from scipy.ndimage import median_filter, uniform_filter1d, gaussian_filter1d

from ..audio.pitch import yin, hz_to_midi, FRAME_SEC
from ..audio.fileio import SR
from . import theory


@dataclass
class Note:
    start: float
    end: float
    pitch: float      # midi אחרי פיצוי כיוון (שלם = צליל נקי)


@dataclass
class Analysis:
    f0: np.ndarray
    midi_c: np.ndarray           # midi אחרי פיצוי סטייה (NaN = אין צליל)
    tuning: float                # סטייה קבועה מ-A440 בחצאי טונים
    tonic: int
    mode: str
    notes: list
    correction: np.ndarray       # חצאי טונים לכל פריים
    beats: np.ndarray            # זמני פעמות בשניות
    tempo: float
    steady: bool
    downbeat: int                # אינדקס הפעמה הראשונה בתיבה
    chords: list = field(default_factory=list)   # (start, end, chord dict)
    duration: float = 0.0
    keys: list = field(default_factory=list)     # סולמות חלופיים לפי סדר התאמה
    key_index: int = 0
    strength: float = 0.8
    curve_term: np.ndarray = None


def _tuning_curve(midi, voiced):
    """אומד סטייה קבועה + 'זליגה' איטית (זמרים בלי ליווי נוטים לרדת)."""
    dev = midi - np.round(midi)
    z = np.where(voiced, np.exp(2j * np.pi * dev), 0)
    win = int(20 / FRAME_SEC)
    num = uniform_filter1d(z.real, win) + 1j * uniform_filter1d(z.imag, win)
    den = uniform_filter1d(voiced.astype(float), win)
    glob = np.angle(np.sum(z)) / (2 * np.pi)
    loc = np.where(den > 0.05, np.angle(num) / (2 * np.pi), np.nan)
    # השלמת חורים ופריסה רציפה
    idx = np.arange(len(loc))
    ok = ~np.isnan(loc)
    if ok.sum() < 2:
        return np.full(len(midi), glob), glob
    ang = np.unwrap(np.interp(idx, idx[ok], loc[ok]) * 2 * np.pi) / (2 * np.pi)
    ang -= np.round(np.median(ang[voiced] - glob)) if voiced.any() else 0
    return ang, glob


def _segment_notes(mc, voiced):
    notes = []
    sm = median_filter(np.where(voiced, mc, 0), 7)
    n = len(mc)
    i = 0
    while i < n:
        if not voiced[i]:
            i += 1
            continue
        j = i
        cur = []
        while j < n and voiced[j]:
            cur.append(sm[j])
            if len(cur) > 6:
                center = np.median(cur[-30:-4]) if len(cur) > 10 else np.median(cur[:-1])
                recent = np.median(cur[-4:])
                if abs(recent - center) > 0.6:
                    end = j - 3
                    notes.append(Note(i * FRAME_SEC, end * FRAME_SEC, float(np.median(mc[i:end]))))
                    i = end
                    cur = list(sm[end:j + 1])
            j += 1
        if j - i >= 5:
            notes.append(Note(i * FRAME_SEC, j * FRAME_SEC, float(np.median(mc[i:j]))))
        i = j
    return [x for x in notes if x.end - x.start >= 0.06]


def _snap(center, scale):
    """הצליל הקרוב בסולם; צליל מחוץ לסולם שהזמר פגע בו בדיוק נשאר (כנראה בכוונה)."""
    near = round(center)
    if near % 12 in scale or abs(center - near) < 0.2:
        return near
    for d in (1, -1, 2, -2):
        c = near + d
        if c % 12 in scale and abs(center - c) < 0.8:
            return c
    return near


def _targets(mc, voiced, notes, scale, strength):
    """תיקון לכל צליל בשלמותו - שומר על הוויברטו והגלישות הטבעיות."""
    corr = np.zeros(len(mc))
    for nt in notes:
        a, b = int(round(nt.start / FRAME_SEC)), int(round(nt.end / FRAME_SEC))
        target = _snap(nt.pitch, scale)
        dev = target - nt.pitch
        if abs(dev) < 0.08:
            continue
        # צליל שנמצא בדיוק באמצע בין שני צלילים - לא בטוח מה התכוון הזמר, מתקנים פחות
        sure = float(np.clip((0.5 - abs(dev)) / 0.2, 0.3, 1.0))
        corr[a:b] = dev * strength * sure
    corr = np.where(voiced, corr, 0)
    return gaussian_filter1d(corr, 3)            # מעברים רכים (~30ms)


def _onset_env(x, notes):
    hop = 441
    n = len(x) // hop
    fr = x[: n * hop].reshape(n, hop)
    e = np.log1p(100 * np.sqrt(np.mean(fr ** 2, axis=1)))
    flux = np.maximum(np.diff(e, prepend=e[0]), 0)
    env = flux / (flux.max() + 1e-9)
    for nt in notes:
        k = int(nt.start * 100)
        if 0 <= k < n:
            env[k] += 0.6 + 0.6 * min(1.0, (nt.end - nt.start) / 0.5)
    return gaussian_filter1d(env, 1.5)


def _tempo_beats(env):
    fps = 100
    env = env - uniform_filter1d(env, 100)
    env = np.maximum(env, 0)
    ac = np.correlate(env, env, "full")[len(env) - 1:]
    ac /= ac[0] + 1e-9
    lags = np.arange(len(ac))
    bpm_range = (lags >= fps * 60 / 190) & (lags <= fps * 60 / 55)
    bpm = 60 * fps / np.maximum(lags, 1)
    prior = np.exp(-0.5 * (np.log2(bpm / 115) / 0.6) ** 2)
    score = np.where(bpm_range, ac * prior, -1)
    lag = int(np.argmax(score))
    clarity = float(ac[lag])
    tempo = 60 * fps / lag
    # מעקב פעמות בתכנות דינמי (Ellis 2007)
    n = len(env)
    cum = env.copy()
    back = np.full(n, -1)
    lo, hi = int(lag * 0.8), int(lag * 1.25)
    tight = 100
    for i in range(hi, n):
        prev = np.arange(i - hi, i - lo + 1)
        pen = -tight * np.log((i - prev) / lag) ** 2
        cand = cum[prev] + pen
        j = int(np.argmax(cand))
        cum[i] = env[i] + cand[j]
        back[i] = prev[j]
    i = int(np.argmax(cum[-hi:])) + n - hi if n > hi else n - 1
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    beats = np.array(beats[::-1]) / fps
    return tempo, beats, clarity


def _downbeat(beats, notes):
    """בוחר באיזו פעמה מתחילה תיבה (4 פעמות): שם מתחילים צלילים ארוכים."""
    sc = np.zeros(4)
    for nt in notes:
        k = int(np.argmin(np.abs(beats - nt.start)))
        if abs(beats[k] - nt.start) < 0.12:
            sc[k % 4] += nt.end - nt.start
    return int(np.argmax(sc))


def _choose_chords(segments, notes, chords, tonic_index=0):
    """Viterbi על אקורדים: מתאים לצלילי המנגינה, מעדיף מעברים טבעיים."""
    if not segments:
        return []
    K = len(chords)
    T = len(segments)
    em = np.zeros((T, K))
    for t, (a, b) in enumerate(segments):
        for nt in notes:
            ov = min(b, nt.end) - max(a, nt.start)
            if ov <= 0:
                continue
            w = ov * (1.5 if abs(nt.start - a) < 0.15 else 1.0)
            pc = int(round(nt.pitch)) % 12
            for k, ch in enumerate(chords):
                if pc == ch["pcs"][0]:
                    em[t, k] += 1.0 * w
                elif pc in ch["pcs"]:
                    em[t, k] += 0.8 * w
                else:
                    em[t, k] -= 0.5 * w
        em[t] /= max(1e-3, b - a)
    prior = np.array([0.35 if i == 0 else (0.2 if ch["degree"] in ("IV", "iv", "V") else 0)
                      for i, ch in enumerate(chords)])
    trans = np.full((K, K), -0.15)
    np.fill_diagonal(trans, 0.1)
    for i, ci in enumerate(chords):
        for j, cj in enumerate(chords):
            if ci["degree"] in ("V", "VII", "II") and j == 0:
                trans[i, j] = 0.25
    score = em[0] + prior
    back = np.zeros((T, K), int)
    for t in range(1, T):
        tot = score[:, None] + trans
        back[t] = np.argmax(tot, axis=0)
        score = tot[back[t], np.arange(K)] + em[t] + prior
    score[0] += 0.5                      # סיום בטוניקה
    k = int(np.argmax(score))
    path = [k]
    for t in range(T - 1, 0, -1):
        k = back[t, k]
        path.append(k)
    path = path[::-1]
    return [(a, b, chords[k]) for (a, b), k in zip(segments, path)]


def analyze(x: np.ndarray, strength: float = 0.8, progress=None):
    duration = len(x) / SR
    f0, conf = yin(x)
    if progress:
        progress(25)
    voiced = f0 > 0
    if voiced.sum() < 50:
        from ..audio.fileio import AudioError
        raise AudioError("לא זיהיתי שירה בהקלטה.\nשיר קרוב יותר למיקרופון ונסה שוב.")
    midi = np.where(voiced, hz_to_midi(np.where(voiced, f0, 1)), np.nan)
    curve, glob = _tuning_curve(np.nan_to_num(midi), voiced)
    # מתקנים 'זליגה' רק כשהיא ממשית; אחרת כיוון קבוע (יציב יותר)
    if np.ptp(curve[voiced]) < 0.3:
        curve = np.full(len(curve), glob)
    mc = np.where(voiced, midi - curve + glob, np.nan)   # כמו מכוון קבוע ב-glob
    mc0 = np.where(voiced, mc - glob, np.nan)            # ביחס לרשת חצאי הטונים
    notes = _segment_notes(np.nan_to_num(mc0), voiced)
    w = np.zeros(12)
    for nt in notes:
        w[int(round(nt.pitch)) % 12] += min(nt.end - nt.start, 2.0)
    longs = [nt for nt in notes if nt.end - nt.start > 0.25] or notes
    final_pc = int(round(longs[-1].pitch)) % 12 if longs else None
    ranked = theory.rank_keys(w, final_pc)
    env = _onset_env(x, notes)
    tempo, beats, clarity = _tempo_beats(env)
    if progress:
        progress(45)
    on_beat = 0
    long_notes = [nt for nt in notes if nt.end - nt.start > 0.12]
    for nt in long_notes:
        if len(beats) and np.min(np.abs(beats - nt.start)) < 0.09:
            on_beat += 1
    ratio = on_beat / max(1, len(long_notes))
    steady = bool(clarity > 0.25 and ratio > 0.45 and len(beats) >= 8)
    a = Analysis(f0=f0, midi_c=mc0, tuning=glob, tonic=ranked[0][0], mode=ranked[0][1], notes=notes,
                 correction=None, beats=beats, tempo=tempo, steady=steady,
                 downbeat=0, duration=duration, keys=_distinct(ranked[:1] + theory.rank_keys(w, None)), strength=strength,
                 curve_term=(curve - glob))
    if steady:
        a.downbeat = _downbeat(beats, notes)
    set_key(a, 0)
    if progress:
        progress(55)
    return a


def _distinct(ranked, n=4):
    """המועמדים הטובים - בלי שניים שנותנים כמעט אותו ליווי."""
    out = []
    for t, m, c in ranked:
        if len(out) >= n:
            break
        if (t, m) in [(o[0], o[1]) for o in out]:
            continue
        out.append((t, m, c))
    return out


def set_key(a, index):
    """קובע סולם (לפי מספר מועמד) ומחשב מחדש את תיקון הקול והאקורדים."""
    index = index % len(a.keys)
    a.key_index = index
    a.tonic, a.mode = a.keys[index][0], a.keys[index][1]
    voiced = a.f0 > 0
    scale = theory.scale_pcs(a.tonic, a.mode)
    corr = _targets(np.nan_to_num(a.midi_c), voiced, a.notes, scale, a.strength)
    total = np.where(voiced, corr - a.curve_term * a.strength, 0)
    a.correction = gaussian_filter1d(total, 2)
    chords = theory.chords_for(a.tonic, a.mode)
    if a.steady:
        bars = a.beats[a.downbeat::2]          # אקורד כל חצי תיבה
        segs = [(bars[i], bars[i + 1]) for i in range(len(bars) - 1)]
        a.chords = _merge(_choose_chords(segs, a.notes, chords))
    else:
        a.chords = _merge(_choose_chords(_free_segments(a.notes, a.duration), a.notes, chords))
    return a


def _merge(raw):
    out = []
    for s, e, c in raw:
        if out and out[-1][2] is c:
            out[-1] = (out[-1][0], e, c)
        else:
            out.append((s, e, c))
    return out


def _free_segments(notes, duration):
    """לשירה בקצב חופשי: קטעים של כ-2 שניות שמתחילים בתחילת צליל."""
    if not notes:
        return [(0, duration)]
    bounds = [notes[0].start]
    for nt in notes:
        if nt.start - bounds[-1] >= 2.0:
            bounds.append(nt.start)
    bounds.append(max(notes[-1].end, bounds[-1] + 0.5))
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
