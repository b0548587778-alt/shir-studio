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
    meter: int = 4                # פעמות בתיבה
    chords_per_bar: int = 2
    transpose: int = 0
    compound: bool = False        # משקל 6/8: שתי פעמות בתיבה, כל אחת מתחלקת לשלוש
    auto: dict = field(default_factory=dict)     # הערכים שזוהו אוטומטית
    note_edits: dict = None       # תיקון ידני לצליל: {מפתח הצליל: חצאי טונים מהיעד האוטומטי, או "off"}
    modulate_at: float = None     # עליית סולם: מאיזה רגע הליווי עולה (None = בלי)
    modulate_voice: float = None  # ...ומאיזה רגע הקול עולה (בהפסקה שלפני המשפט)


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
    # ממוצע על פני מחזור ויברטו אחד (כ-0.17 שניות): הוויברטו של הזמר 'מתבטל',
    # ומעבר אמיתי לצליל אחר עדיין בולט. בלי זה, ויברטו רחב נחתך להרבה 'צלילים' מדומים.
    w = max(3, int(round(0.17 / FRAME_SEC)))
    v = voiced.astype(float)
    num = uniform_filter1d(np.where(voiced, mc, 0.0), w)
    den = uniform_filter1d(v, w)
    sm = np.where(den > 0.3, num / np.maximum(den, 1e-6), np.where(voiced, mc, 0.0))
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


def note_key(nt):
    """מזהה קבוע של צליל (לפי רגע ההתחלה) - לשמירת תיקונים ידניים."""
    return str(int(round(nt.start * 100)))


def note_edit(edits, nt):
    if not edits:
        return None
    c = int(round(nt.start * 100))
    for d in (0, 1, -1, 2, -2):
        if str(c + d) in edits:
            return edits[str(c + d)]
    return None


def note_targets(a):
    """לגרף: (התחלה, סוף, מה שהושר, הצליל שאליו מתקנים, מפתח) לכל צליל."""
    scale = theory.scale_pcs(a.tonic, a.mode)
    out = []
    for nt in a.notes:
        ed = note_edit(a.note_edits, nt)
        auto = _snap(nt.pitch, scale)
        tgt = nt.pitch if ed == "off" else auto + (int(ed) if ed is not None else 0)
        out.append((nt.start, nt.end, nt.pitch, tgt, note_key(nt), auto))
    return out


def _targets(mc, voiced, notes, scale, strength, edits=None):
    """תיקון לכל צליל בשלמותו - שומר על הוויברטו והגלישות הטבעיות."""
    corr = np.zeros(len(mc))
    inside = np.zeros(len(mc), bool)
    for nt in notes:
        a, b = int(round(nt.start / FRAME_SEC)), int(round(nt.end / FRAME_SEC))
        target = _snap(nt.pitch, scale)
        dev = target - nt.pitch
        inside[a:b] = True                        # גם צליל מדויק (בלי תיקון) הוא 'עוגן' למעברים
        ed = note_edit(edits, nt)
        if ed == "off":                           # המשתמש ביקש: את הצליל הזה לא לתקן
            continue
        if ed is not None:                        # המשתמש גרר את הצליל - מתקנים בדיוק לשם
            corr[a:b] = target + int(ed) - nt.pitch
            continue
        if abs(dev) < 0.08:
            continue
        # צליל שנמצא בדיוק באמצע בין שני צלילים - לא בטוח מה התכוון הזמר, מתקנים פחות
        sure = float(np.clip((0.5 - abs(dev)) / 0.2, 0.3, 1.0))
        corr[a:b] = dev * strength * sure
    # מעברים טבעיים: בין שני צלילים מחוברים (לגאטו) התיקון עובר בהדרגה מהאחד לשני,
    # במקום לקפוץ לאפס באמצע הגלישה - כך הגלישה של הזמר נשמרת ונשמעת חלקה
    idx = np.arange(len(corr))
    if inside.any():
        filled = np.interp(idx, idx[inside], corr[inside])
        runs = np.cumsum(np.diff(np.concatenate([[0], voiced.astype(int)])) == 1)   # מספר רצף קולי
        gap = voiced & ~inside
        same = np.zeros(len(corr), bool)
        for r in np.unique(runs[gap]):
            sel = runs == r
            if (sel & inside).any():
                same |= sel & gap
        corr = np.where(same, filled, corr)
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
            env[k] += 0.3 + 0.3 * min(1.0, (nt.end - nt.start) / 0.5)
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
    tight = 30
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


def note_onsets(x, notes):
    """הרגע שבו כל צליל באמת נשמע (לפי עוצמת הקול), בדיוק של אלפית שנייה.
    זמני הצלילים מזיהוי גובה הצליל מדויקים רק עד כמה מאיות שנייה - לא מספיק לסינכרון של ליווי."""
    hop = int(0.002 * SR)
    dt = hop / SR
    n = len(x) // hop
    env = np.sqrt(np.mean(np.asarray(x[: n * hop], dtype=np.float64).reshape(n, hop) ** 2, axis=1))
    env = uniform_filter1d(env, 3)
    out = []
    for nt in notes:
        if nt.end - nt.start <= 0.1:
            continue
        a, b = int((nt.start - 0.06) / dt), int((nt.start + 0.14) / dt)
        a, b = max(a, 0), min(b, n)
        seg = env[a:b]
        if len(seg) < 10:
            continue
        lo_i = int(np.argmin(seg[: max(2, len(seg) // 2)]))
        peak = float(seg[lo_i:].max())
        if peak > 2.5 * seg[lo_i] + 1e-6:
            # יש התקפה ברורה (הקול עלה משקט): הרגע שבו הוא עובר רבע מהעוצמה
            above = np.where(seg[lo_i:] >= seg[lo_i] + 0.25 * (peak - seg[lo_i]))[0]
            out.append((a + lo_i + int(above[0])) * dt)
        else:
            out.append(nt.start + 0.028)          # צליל מחובר (לגאטו): מרכז חלון הניתוח
    return np.array(out)


def refine_beats(beats, onsets, rounds=6):
    """סינכרון עדין: מצמיד את רשת הפעמות לתחילות הצלילים של הזמר.
    מעקב הפעמות מדויק רק עד מאית שנייה ומפגר כשהזמר מאיץ או מאט; כאן כל פעמה זזה אל הצלילים
    שהזמר שר סביבה (בהחלקה על פני כמה פעמות - כדי שהליווי ילך עם הזמר ולא יקפוץ אחרי כל צליל)."""
    b = np.asarray(beats, dtype=float).copy()
    ons = np.asarray(onsets, dtype=float)
    if len(b) < 6 or len(ons) < 4:
        return b
    for _ in range(rounds):
        period = np.diff(b)
        per = np.concatenate([period, period[-1:]])
        num, den = np.zeros(len(b)), np.zeros(len(b))
        for t in ons:
            k = int(np.clip(np.searchsorted(b, t) - 1, 0, len(b) - 2))
            frac = (t - b[k]) / (b[k + 1] - b[k])
            if not -0.3 < frac < 1.3:
                continue
            sub = round(frac * 2) / 2                       # הפעמה או חצי הפעמה הקרובה
            off = (frac - sub) * (b[k + 1] - b[k])
            if abs(off) > 0.2 * per[k]:
                continue                                    # צליל שלא יושב על הרשת (קישוט) - לא מושך
            w = 1.0 if sub in (0.0, 1.0) else 0.6
            i = k + (1 if sub >= 1.0 else 0)
            num[i] += w * off
            den[i] += w
            if sub == 0.5:                                  # חצי פעמה מושכת את שתי השכנות
                num[k + 1] += w * off
                den[k + 1] += w
        if den.sum() < 3:
            break
        # ממוצע משוקלל מוחלק: פעמה בלי צלילים מקבלת את התיקון של שכנותיה
        sm_num = gaussian_filter1d(num, 2.0, mode="nearest")
        sm_den = gaussian_filter1d(den, 2.0, mode="nearest")
        shift = np.where(sm_den > 1e-3, sm_num / np.maximum(sm_den, 1e-3), 0.0)
        b = b + shift
        if np.max(np.abs(shift)) < 0.002:
            break
    # פעמות שאין סביבן צלילים (צליל ארוך בסוף, הפסקה ארוכה): ממשיכות בקצב המקומי של הזמר ולא בקצב הממוצע
    near = np.array([np.any(np.abs(ons - t) < 1.5 * np.median(np.diff(b))) for t in b])
    idx = np.where(near)[0]
    if len(idx) >= 6:
        first, last = idx[0], idx[-1]
        if last < len(b) - 1:
            loc = float(np.median(np.diff(b[max(first, last - 6): last + 1])))
            b[last + 1:] = b[last] + loc * np.arange(1, len(b) - last)
        if first > 0:
            loc = float(np.median(np.diff(b[first: min(last, first + 6) + 1])))
            b[:first] = b[first] - loc * np.arange(first, 0, -1)
        for i0, i1 in zip(idx[:-1], idx[1:]):               # הפסקה באמצע: פעמות שוות בין שני הקצוות
            if i1 - i0 > 1:
                b[i0:i1 + 1] = np.linspace(b[i0], b[i1], i1 - i0 + 1)
    if np.any(np.diff(b) <= 0.05):                          # הגנה: הרשת חייבת להישאר עולה
        return np.asarray(beats, dtype=float)
    return b


def _downbeat(beats, notes, meter=4):
    """בוחר באיזו פעמה מתחילה תיבה: שם מתחילים צלילים ארוכים."""
    sc = np.zeros(meter)
    for nt in notes:
        k = int(np.argmin(np.abs(beats - nt.start)))
        if abs(beats[k] - nt.start) < 0.12:
            sc[k % meter] += nt.end - nt.start
    return int(np.argmax(sc))


# משקלים שנבחרו בבדיקה על הקלטות אמיתיות: האקורד מתאים יותר למנגינה ופחות "תקוע" על הטוניקה
CHORD_W = {"tonic": 0.15, "main": 0.15, "stay": 0.1, "change": -0.15, "resolve": 0.25, "out": 0.8}


def _choose_chords(segments, notes, chords, tonic_index=0, w=None):
    """Viterbi על אקורדים: מתאים לצלילי המנגינה, מעדיף מעברים טבעיים."""
    if not segments:
        return []
    w = w or CHORD_W
    K = len(chords)
    T = len(segments)
    em = np.zeros((T, K))
    for t, (a, b) in enumerate(segments):
        for nt in notes:
            ov = min(b, nt.end) - max(a, nt.start)
            if ov <= 0:
                continue
            wt = ov * (1.5 if abs(nt.start - a) < 0.15 else 1.0)
            pc = int(round(nt.pitch)) % 12
            for k, ch in enumerate(chords):
                if pc == ch["pcs"][0]:
                    em[t, k] += 1.0 * wt
                elif pc in ch["pcs"]:
                    em[t, k] += 0.8 * wt
                else:
                    em[t, k] -= w["out"] * wt
        em[t] /= max(1e-3, b - a)
    prior = np.array([w["tonic"] if i == 0 else (w["main"] if ch["degree"] in ("IV", "iv", "V") else 0)
                      for i, ch in enumerate(chords)])
    trans = np.full((K, K), w["change"])
    np.fill_diagonal(trans, w["stay"])
    for i, ci in enumerate(chords):
        for j, cj in enumerate(chords):
            if ci["degree"] in ("V", "VII", "II") and j == 0:
                trans[i, j] = w["resolve"]
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
    # הערכת הכיוון לפי הגובה הממוצע על פני מחזור ויברטו (ויברטו רחב מבלבל את ההערכה)
    wv = max(3, int(round(0.17 / FRAME_SEC)))
    num = uniform_filter1d(np.where(voiced, np.nan_to_num(midi), 0.0), wv)
    den = uniform_filter1d(voiced.astype(float), wv)
    midi_s = np.where(voiced & (den > 0.3), num / np.maximum(den, 1e-6), np.nan_to_num(midi))
    curve, glob = _tuning_curve(midi_s, voiced)
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
    # קצב קבוע? בודקים כמה תחילות צלילים נופלות על רשת שמיניות של הפעמות
    ons = [nt.start for nt in notes if nt.end - nt.start > 0.12]
    if len(beats) >= 8 and ons:
        grid = np.sort(np.concatenate([beats, (beats[:-1] + beats[1:]) / 2]))
        on8 = float(np.mean([np.min(np.abs(grid - t)) < 0.06 for t in ons]))
    else:
        on8 = 0.0
    steady = bool(clarity > 0.18 and on8 > 0.4)
    if steady:
        beats = refine_beats(beats, note_onsets(x, notes))
    a = Analysis(f0=f0, midi_c=mc0, tuning=glob, tonic=ranked[0][0], mode=ranked[0][1], notes=notes,
                 correction=None, beats=beats, tempo=tempo, steady=steady,
                 downbeat=0, duration=duration, keys=_distinct(ranked[:1] + theory.rank_keys(w, None)), strength=strength,
                 curve_term=(curve - glob))
    if steady:
        a.downbeat = _downbeat(beats, notes)
    a.auto = {"beats": beats, "tempo": tempo, "steady": steady, "keys": list(a.keys)}
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
    a.correction = correction_for(a, a.strength)
    chords = theory.chords_for(a.tonic, a.mode)
    a.chords = _merge(_choose_chords(chord_segments(a), a.notes, chords))
    return a


def correction_for(a, strength):
    """תיקון הקול (חצאי טונים לכל פריים) בעוצמה נתונה, כולל התיקונים הידניים."""
    voiced = a.f0 > 0
    scale = theory.scale_pcs(a.tonic, a.mode)
    corr = _targets(np.nan_to_num(a.midi_c), voiced, a.notes, scale, strength, a.note_edits)
    total = np.where(voiced, corr - a.curve_term * strength, 0)
    return gaussian_filter1d(total, 2)


def use_grid(a, beats, tempo, steady):
    """קובע את הפעמות מבחוץ - כשהזמר שר על ליווי קיים, הקצב כבר ידוע בדיוק."""
    a.auto.update(beats=np.asarray(beats, float), tempo=float(tempo), steady=bool(steady))
    a.beats, a.tempo, a.steady = a.auto["beats"], a.auto["tempo"], a.auto["steady"]
    if a.steady:
        a.downbeat = _downbeat(a.beats, a.notes, a.meter)
    set_key(a, a.key_index)


def chord_segments(a):
    """הקטעים שלכל אחד מהם אקורד: חלק מתיבה (בקצב קבוע) או ~2 שניות (בקצב חופשי)."""
    if a.steady:
        step = max(1, a.meter // a.chords_per_bar)
        b = a.beats[a.downbeat::step]
        return [(b[i], b[i + 1]) for i in range(len(b) - 1)]
    return _free_segments(a.notes, a.duration)


def manual_grid(a, bpm):
    """רשת פעמות בקצב שהמשתמש קבע, מיושרת לתחילת הצלילים."""
    period = 60.0 / bpm
    onsets = np.array([nt.start for nt in a.notes if nt.end - nt.start > 0.12] or [0.0])
    best, best_sc = 0.0, -1
    for ph in np.linspace(0, period, 40, endpoint=False):
        d = np.abs(((onsets - ph) + period / 2) % period - period / 2)
        sc = np.sum(np.exp(-(d / 0.05) ** 2))
        if sc > best_sc:
            best, best_sc = ph, sc
    start = best - period * np.ceil(best / period)
    return np.arange(start if start >= 0 else start + period, a.duration + period, period)


def vocal_range(a):
    """המנעד של הזמר בשיר (midi): הנמוך, הגבוה והאמצע - לפי משך הצלילים."""
    notes = [nt for nt in a.notes if nt.end - nt.start > 0.1] or list(a.notes)
    if not notes:
        return None
    ps = np.array([nt.pitch for nt in notes])
    w = np.array([nt.end - nt.start for nt in notes])
    order = np.argsort(ps)
    cw = np.cumsum(w[order]) / w.sum()
    q = lambda f: float(ps[order][min(len(ps) - 1, int(np.searchsorted(cw, f)))])
    return q(0.03), q(0.97), q(0.5)


def suggest_transpose(a):
    """המלצה לטרנספוזיציה לפי גובה הקול: קול גברי נוח סביב רה-לה (קטנה), קול אישה/ילד אוקטבה מעל.
    מחזיר מספר חצאי טונים (0 = השיר כבר בגובה נוח)."""
    r = vocal_range(a)
    if r is None:
        return 0
    mid = r[2]
    lo_c, hi_c = (50.0, 57.0) if mid < 59.5 else (62.0, 69.0)
    if mid < lo_c:
        d = lo_c - mid
    elif mid > hi_c:
        d = hi_c - mid
    else:
        return 0
    return int(np.clip(round(d), -4, 4))            # מעבר לזה הקול כבר נשמע לא טבעי


def apply_settings(a, st):
    """מחיל הגדרות מתקדמות של המשתמש על הניתוח האוטומטי."""
    a.compound = st.meter == 6                 # 6/8: שתי פעמות (מנוקדות) בתיבה
    a.meter = 2 if a.compound else st.meter
    a.chords_per_bar = st.chords_per_bar if st.meter in (4, 6) else 1
    a.transpose = st.transpose
    a.strength = st.tune / 100
    a.note_edits = getattr(st, "note_edits", None) or None
    # קצב
    if st.tempo_mode == "free":
        a.steady = False
    elif st.tempo_mode == "manual" and st.bpm:
        a.steady, a.beats, a.tempo = True, manual_grid(a, st.bpm), float(st.bpm)
    else:
        a.steady, a.beats, a.tempo = a.auto["steady"], a.auto["beats"], a.auto["tempo"]
    if a.steady:
        a.downbeat = _downbeat(a.beats, a.notes, a.meter)
    # סולם
    keys = list(a.auto["keys"])
    if st.key is not None:
        keys = [(st.key[0], st.key[1], 1.0)] + [k for k in keys if (k[0], k[1]) != tuple(st.key)]
    a.keys = keys
    set_key(a, 0 if st.key is not None else a.key_index)
    # אקורדים שהמשתמש כתב
    if st.chords_text and st.chords_text.strip():
        a.chords = parse_chords(st.chords_text, chord_bars(a))
    return a


def chord_bars(a):
    """גבולות התיבות (או הקטעים בקצב חופשי)."""
    if a.steady:
        b = a.beats[a.downbeat::a.meter]
        return [(b[i], b[i + 1]) for i in range(len(b) - 1)]
    return _free_segments(a.notes, a.duration)


LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def parse_chord(sym):
    sym = sym.strip()
    if not sym or sym[0].upper() not in LETTERS:
        raise ValueError(sym)
    root = LETTERS[sym[0].upper()]
    rest = sym[1:]
    if rest.startswith(("#", "♯")):
        root, rest = (root + 1) % 12, rest[1:]
    elif rest.startswith(("b", "♭")):
        root, rest = (root - 1) % 12, rest[1:]
    minor = rest.startswith("m") and not rest.startswith("maj")
    q = "min" if minor else "maj"
    seventh = 11 if "maj7" in rest else (10 if "7" in rest else None)
    return {"degree": sym, "index": -1, "root": root, "quality": q, "seventh": seventh,
            "pcs": [(root + d) % 12 for d in theory.QUALITY[q]]}


def parse_chords(text, bars):
    """טקסט כמו 'Am | Dm E | Am' - תיבות מופרדות ב-|, כמה אקורדים בתיבה מחלקים אותה שווה."""
    out = []
    groups = [g.split() for g in text.replace("\n", "|").split("|")]
    groups = [g for g in groups if g]
    if not groups:
        return out
    prev = None
    for i, (s, e) in enumerate(bars):
        g = groups[i] if i < len(groups) else [groups[-1][-1]]
        step = (e - s) / len(g)
        for j, sym in enumerate(g):
            ch = prev if sym in ("-", "%", "/") else parse_chord(sym)
            if ch is None:
                continue
            out.append((s + j * step, s + (j + 1) * step, ch))
            prev = ch
    return _merge_same(out)


def _merge_same(raw):
    out = []
    for s, e, c in raw:
        if out and out[-1][2]["root"] == c["root"] and out[-1][2]["quality"] == c["quality"]:
            out[-1] = (out[-1][0], e, out[-1][2])
        else:
            out.append((s, e, c))
    return out


NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def chords_as_text(a):
    """האקורדים שזוהו, בכתיב של מוזיקאים, תיבה אחרי תיבה."""
    bars = chord_bars(a)
    parts = []
    for s, e in bars:
        inside = []
        for cs, ce, c in a.chords:
            if cs < e - 0.05 and ce > s + 0.05:
                name = NAMES[c["root"]] + ("m" if c["quality"] == "min" else "")
                if not inside or inside[-1] != name:
                    inside.append(name)
        parts.append(" ".join(inside[:4]) or "-")
    return " | ".join(parts)


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
