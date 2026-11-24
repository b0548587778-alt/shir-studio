"""בניית הליווי לפי ניתוח השיר וסגנון שנבחר."""
import numpy as np

from ..audio.fileio import SR
from . import synth
from .theory import chords_for, scale_pcs

BASS = {"bass", "acoustic_bass"}
LEAD_PREF = ("violin", "clarinet", "flute", "trumpet", "accordion", "guitar", "piano")
BRASS = {"brass", "trumpet", "horn"}                # כלי נשיפה ממתכת
STRUMMED = {"piano", "guitar", "steel_guitar", "harp"}      # כלים שאקורד הסיום שלהם 'נפרט' מלמטה למעלה
PHRASE = 8            # תיבות במשפט
MOD_UP = 1            # עליית סולם בפזמון האחרון: חצי טון


def _note_for(spec, chord, octave):
    base = 12 * (octave + 1)
    root = base + chord["root"]
    third = root + (chord["pcs"][1] - chord["root"]) % 12
    fifth = root + (chord["pcs"][2] - chord["root"]) % 12
    table = {
        "root": [root], "root_low": [root - 12], "third": [third], "fifth": [fifth],
        "fifth_low": [fifth - 12], "octave": [root + 12], "third_hi": [third + 12],
        "fifth_hi": [fifth + 12],
    }
    if spec == "chord":
        center = base + 7
        pcs = list(chord["pcs"]) + ([(chord["root"] + chord["seventh"]) % 12] if chord.get("seventh") else [])
        return sorted(center - 6 + (pc - (center - 6)) % 12 for pc in pcs)
    return table.get(spec, [root])


def voice_lead(notes, prev):
    """בוחר היפוך של האקורד שהכי קרוב לאקורד הקודם - מעבר חלק כמו של נגן אמיתי."""
    if not prev or len(notes) < 2:
        return notes
    cands = []
    for inv in range(len(notes)):
        v = sorted(notes[inv:] + [n + 12 for n in notes[:inv]])
        for sh in (-12, 0, 12):
            cands.append([n + sh for n in v])
    lo, hi = min(notes) - 7, max(notes) + 7                     # לא לברוח רחוק מהמנעד של הסגנון
    cands = [c for c in cands if c[0] >= lo and c[-1] <= hi] or [notes]
    cost = lambda c: sum(min(abs(n - q) for q in prev) for n in c)
    return min(cands, key=cost)


def enrich(chord, mode, rich=False):
    """אקורדים עשירים: ספטאקורד על הדרגה החמישית (תמיד), ובסגנון 'עשיר' גם על אקורדי מינור."""
    c = dict(chord)
    if c.get("seventh") is not None:
        return c
    if c.get("degree") == "V" and mode in ("major", "minor"):
        c["seventh"] = 10                        # ספטאקורד דומיננטי - מושך חזרה לטוניקה
    elif rich and c.get("quality") == "min":
        c["seventh"] = 10                        # מינור 7 - צבע רך
    elif rich and c.get("degree") in ("IV", "VI"):
        c["seventh"] = 11                        # מז'ור 7
    return c


def sections(a, tl, last_voice):
    """עוצמה לכל משפט (8 תיבות): 0 = בית (רגוע), 1 = פזמון (מלא).
    פזמון = משפט שהמנגינה בו גבוהה מהרגיל - כך זה ברוב השירים. המשתמש יכול לקבוע ידנית."""
    bar_sec = tl.period * tl.meter
    t0 = tl.beat_time(tl.bar0 + tl.intro_bars * tl.meter) - tl.lead        # תחילת השירה
    n = max(1, int(np.ceil((last_voice - t0) / (PHRASE * bar_sec))))
    means = []
    for p in range(n):
        a0, a1 = t0 + p * PHRASE * bar_sec, t0 + (p + 1) * PHRASE * bar_sec
        ps = [nt.pitch for nt in a.notes if a0 <= nt.start < a1 and nt.end - nt.start > 0.1]
        means.append(np.mean(ps) if ps else np.nan)
    m = np.array(means)
    levels = [0] * n
    if n >= 2 and np.isfinite(m).sum() >= 2:
        med = np.nanmedian(m)
        levels = [1 if (np.isfinite(x) and x > med + 0.7) else 0 for x in m]
        if not any(levels[1:]):                     # אין פזמון ברור - בונים בהדרגה
            levels = [0] + [1] * (n - 1)
        levels[-1] = 1                              # המשפט האחרון תמיד מלא
    manual = getattr(a, "sections_override", None)
    if manual:
        levels = [int(manual[i]) if i < len(manual) else levels[i] for i in range(n)]
    return levels


def phrase_times(a, tl, last_voice):
    """(התחלה, סוף) של כל משפט בזמן השירה - לתצוגה במסך העריכה."""
    bar_sec = tl.period * tl.meter
    t0 = tl.beat_time(tl.bar0 + tl.intro_bars * tl.meter) - tl.lead
    n = max(1, int(np.ceil((last_voice - t0) / (PHRASE * bar_sec))))
    return [(max(0.0, t0 + p * PHRASE * bar_sec), t0 + (p + 1) * PHRASE * bar_sec) for p in range(n)]


def modulation(a):
    """עליית סולם בפזמון האחרון: (מתי הליווי עולה, מתי הקול עולה) בזמן השירה, או None.
    הליווי עולה בתחילת המשפט האחרון; הקול - בהפסקה שלפני הצליל הראשון של אותו משפט."""
    if not a.steady or not a.notes:
        return None
    tl = Timeline(a)
    last_voice = max(nt.end for nt in a.notes)
    times = phrase_times(a, tl, last_voice)
    bar_sec = tl.period * tl.meter
    k = len(times) - 1
    if k >= 1 and last_voice - times[k][0] < 2 * bar_sec:      # משפט אחרון קצרצר - עולים משפט קודם
        k -= 1
    if k < 2:
        return None                                            # שיר קצר מדי לעלייה
    t_acc = times[k][0]
    new = [nt for nt in a.notes if nt.start >= t_acc - 0.6 * tl.period]
    if not new:
        return None
    before = [nt.end for nt in a.notes if nt.start < new[0].start]
    prev_end = max(before) if before else 0.0
    return t_acc, max((prev_end + new[0].start) / 2, new[0].start - 0.25)


def to_compound(events):
    """הופך תבנית של 4/4 לתבנית של 6/8: כל חצי תיבה (2 פעמות) הופך לפעמה אחת שמתחלקת לשלוש.
    הפעמה הראשונה נשארת, הפעמה השנייה עוברת לשליש השני, וה'אוף-ביט' שאחריה לשליש השלישי."""
    out = []
    for ev in events:
        p, u = divmod(float(ev["t"]), 2.0)
        if p > 1 or (0 < u < 1):
            continue
        t = p + (0.0 if u == 0 else (1 / 3 if u < 1.5 else 2 / 3))
        e = dict(ev, t=t)
        if isinstance(ev.get("d"), (int, float)):
            e["d"] = max(0.3, ev["d"] / 2) if ev["d"] >= 2 else min(ev["d"], 0.33)
        out.append(e)
    return out


def snap_melody(a, notes):
    scale = set(scale_pcs(a.tonic, a.mode))
    out = []
    for s0, e0, p in notes:
        m = int(round(p))
        if m % 12 not in scale:
            m = min((m + d for d in (-1, 1)), key=lambda q: (q % 12 not in scale, abs(q - p)))
        out.append((s0, e0, m))
    return out


def intro_melody(a, tl, bars):
    """תחילת המנגינה (כמה תיבות), לנגינה בכלי לפני שהזמר נכנס - כמו בהקלטה מקצועית."""
    bar_sec = tl.period * tl.meter
    s0 = tl.beat_time(tl.bar0 + tl.intro_bars * tl.meter) - tl.lead
    first = min(nt.start for nt in a.notes)
    notes = [(nt.start, nt.end, nt.pitch) for nt in a.notes
             if s0 - 0.05 <= nt.start < s0 + bars * bar_sec and nt.end - nt.start > 0.08]
    notes = snap_melody(a, notes)
    if not notes:
        return []
    med = np.median([m for _, _, m in notes])
    sh = 12 * round((69 - med) / 12)
    off = bars * bar_sec
    # מסיימים לפני שהזמר נכנס (גם אם הוא נכנס עם 'קדם-פעמה')
    stop = first - 0.12
    return [(st - off, min(en - off, stop), m + sh) for st, en, m in notes if st - off < stop - 0.1]


def counter_melody(a, tl, chord_at, rng, start_min, end_max):
    """מנגינות נגד: בהפסקות בין המשפטים של הזמר, כלי מנגן קו קצר מצלילי האקורד."""
    beat = tl.period
    notes = sorted((nt.start, nt.end) for nt in a.notes if nt.end - nt.start > 0.08)
    out = []
    for (s1, e1), (s2, _) in zip(notes, notes[1:]):
        gap = s2 - e1
        if gap < 2.2 * beat or e1 < start_min or s2 > end_max:
            continue
        t = e1 + 0.5 * beat
        ch = chord_at(t)
        tones = sorted({60 + (pc - 60) % 12 + 12 for pc in ch["pcs"]})    # אוקטבה גבוהה, מעל הזמר
        k = int(min(4, (gap - beat) // (0.5 * beat)))
        if k < 2:
            continue
        seq = tones[::-1] if rng.random() < 0.5 else tones
        seq = (seq * 2)[:k]
        for j, m in enumerate(seq):
            st = t + j * 0.5 * beat
            if st + 0.5 * beat > s2 - 0.15:
                break
            out.append((st, 0.5 * beat * (1.6 if j == len(seq) - 1 else 0.95), m, 0.55 - 0.05 * j))
    return out


def brass_voice(inst, m):
    """כל צליל של כלי הנשיפה מנוגן בכלי שמתאים לגובה שלו: למעלה חצוצרה, למטה טרומבון -
    כך הם נשמעים כמו קבוצת נשיפה אמיתית ולא כמו כלי אחד שנמתח מחוץ למנעד שלו."""
    from . import sampler
    if inst == "brass" and m > 64 and sampler.has("trumpet"):
        return "trumpet"
    if inst == "trumpet" and m < 53 and sampler.has("brass"):
        return "brass"
    return inst


def third_below(m, scale):
    """הצליל שנמצא שתי מדרגות מתחת בסולם (טרצה) - לקול שני מתחת למנגינה."""
    q, steps = m, 0
    while steps < 2:
        q -= 1
        if q % 12 in scale:
            steps += 1
    return q


def step_below(m, scale):
    """הצליל הקרוב בסולם שמתחת ל-m."""
    q = m - 1
    while q % 12 not in scale:
        q -= 1
    return q


def free_plan(a, style, tonic_chord):
    """פתיח וסיום לשיר בקצב חופשי (בלי תופים):
    פתיח - הכלי המוביל מנגן את המשפט הראשון של המנגינה לפני שהזמר נכנס;
    סיום - הכלי 'עונה' לזמר במשפט האחרון, ואחריו אקורד סיום ארוך.
    מחזיר dict: lead (שניות לפני השירה), segs (אקורדים), notes (צלילי הכלי המוביל), final (זמן, אורך)."""
    chords = list(a.chords) or [(0.0, a.duration, tonic_chord)]
    mel = snap_melody(a, [(nt.start, nt.end, nt.pitch) for nt in a.notes if nt.end - nt.start > 0.08])
    plan = {"lead": 1.5, "notes": [], "final": None}
    segs = list(chords)
    last_voice = max([e for _, e, _ in mel] + [chords[-1][1]])
    dominant = next((c for c in chords_for(a.tonic, a.mode) if c["degree"] == "V"), None)

    def chords_between(t0, t1, shift):
        out = [(max(s, t0) + shift, min(e, t1) + shift, c) for s, e, c in chords if s < t1 and e > t0]
        return out or [(t0 + shift, t1 + shift, tonic_chord)]

    def register(notes):
        med = np.median([m for _, _, m in notes])
        return 12 * round((69 - med) / 12)

    first_seg = None
    if mel and style.get("intro", True):
        f0 = mel[0][0]
        end = None
        for (s1, e1, _), (s2, _, _) in zip(mel, mel[1:]):
            if e1 - f0 >= 1.5 and (s2 - e1 >= 0.35 or e1 - f0 >= 4.5):
                end = e1
                break
        if end is None and mel[-1][1] - f0 <= 6:
            end = None                                       # שיר קצרצר - בלי פתיח מנוגן
        if end is not None and last_voice - f0 > 2.5 * (end - f0):
            breath = 0.7                                      # נשימה בין הפתיח לכניסה של הזמר
            shift = -(end - f0 + breath)
            ph = [n for n in mel if n[0] < end - 0.05]
            sh = register(ph)
            plan["notes"] += [(s + shift, (e - s) * 0.95, m + sh, 0.62) for s, e, m in ph]
            plan["lead"] = max(1.5, -(f0 + shift) + 0.8)
            intro = chords_between(f0, end, shift)
            intro[0] = (intro[0][0] - 0.5, intro[0][1], intro[0][2])
            turn = dominant is not None and chords[0][2].get("root") == tonic_chord["root"]
            wait = dict(dominant, seventh=10) if turn else chords[0][2]      # אקורד 'מזמין' לפני הכניסה
            first_seg = intro + [(f0 - breath, chords[0][0], wait)]
    segs = (first_seg or [(-1.2, chords[0][0], chords[0][2])]) + segs
    end_t = segs[-1][1]
    if mel and style.get("solo", True) and last_voice - mel[0][0] > 8:
        start = None
        for (s1, e1, _), (s2, _, _) in zip(mel, mel[1:]):
            if s2 - e1 >= 0.35 and 1.2 <= last_voice - s2 <= 5.0:
                start = s2                                    # תחילת המשפט האחרון
        if start is None:
            start = last_voice - 3.0
        ph = [n for n in mel if n[0] >= start - 0.02]
        if ph:
            shift = (last_voice - start) + 0.5
            sh = register(ph)
            plan["notes"] += [(s + shift, (e - s) * 0.95, m + sh, 0.58) for s, e, m in ph]
            echo = chords_between(start, last_voice, shift)
            echo[0] = (min(end_t, echo[0][0]), echo[0][1], echo[0][2])
            segs += echo
            end_t = max(end_t, last_voice + shift) + 0.15
    plan["final"] = (end_t, 3.6)
    segs.append((end_t, end_t + 3.6, tonic_chord))
    plan["segs"] = segs
    plan["extra"] = max(0.0, end_t - a.duration)
    return plan


def brass_hits(a, tl, levels, IB, chord_at, last_voice, compound=False):
    """תשובות של קבוצת הנשיפה: 'הרמה' של שני צלילים אל תוך כל פזמון, ו'דקירות' קצרות באמצע הפזמון.
    מחזיר [(מיקום בפעמות, אורך בפעמות, [צלילים], עוצמה)]."""
    meter = tl.meter
    off = (2 / 3) if compound else 0.5
    out = []

    def tones(ch, lo=60):
        return sorted(lo + (pc - lo) % 12 for pc in ch["pcs"])

    def lvl(p):
        return levels[p] if 0 <= p < len(levels) else 0

    bar_sec = tl.period * meter
    n_bars = int((last_voice - (tl.beat_time(tl.bar0 + IB * meter) - tl.lead)) / bar_sec) + 1
    for pb in range(n_bars):
        pos0 = tl.bar0 + (IB + pb) * meter
        if pos0 + 2 * meter >= len(tl.beats) - 1:
            break
        ph, inbar = divmod(pb, PHRASE)
        t_bar = tl.beat_time(pos0) - tl.lead
        if inbar == PHRASE - 1 and lvl(ph + 1) == 1 and (lvl(ph) == 0 or ph + 1 == len(levels) - 1) \
                and t_bar + bar_sec < last_voice:
            # הרמה אל הפזמון: שני צלילים עולים בסוף התיבה, ואקורד מודגש על הפעמה הראשונה של הפזמון
            cur = tones(chord_at(t_bar + bar_sec * 0.8))
            nxt = tones(chord_at(t_bar + bar_sec + 0.05))
            out.append((pos0 + meter - 1, off * 0.9, [cur[0]], 0.6))
            out.append((pos0 + meter - 1 + off, (1 - off) * 0.9, [cur[1]], 0.68))
            out.append((pos0 + meter, 1.6, [nxt[0], nxt[-1] if nxt[-1] != nxt[0] else nxt[0] + 12], 0.8))
        elif lvl(ph) == 1 and inbar == 3 and t_bar + bar_sec < last_voice:
            # דקירות באמצע הפזמון: שני אקורדים קצרצרים בסוף התיבה הרביעית
            ch = tones(chord_at(t_bar + bar_sec * 0.8))
            for k, v in ((meter - 1, 0.6), (meter - 1 + off, 0.7)):
                out.append((pos0 + k, 0.3, [ch[0], ch[-1]], v))
    return out


def _lead_instrument(style):
    if style.get("lead"):
        return style["lead"]
    insts = [tr["instrument"] for tr in style.get("tracks", [])]
    for i in LEAD_PREF:
        if i in insts:
            return i
    return "piano"


def outro_melody(a, tl, last_voice, bars=4):
    """המשפט האחרון של המנגינה, מנוגן בכלי אחרי שהשירה נגמרת (כמו סולו בהקלטה מקצועית)."""
    bar_sec = tl.period * tl.meter
    start = last_voice - bars * bar_sec
    scale = set(scale_pcs(a.tonic, a.mode))
    out = []
    for nt in a.notes:
        if nt.start >= start - 0.05 and nt.end - nt.start > 0.08:
            m = int(round(nt.pitch))
            if m % 12 not in scale:                  # צליל שזויף - מצמידים לסולם
                m = min((m + d for d in (-1, 1)), key=lambda q: (q % 12 not in scale, abs(q - nt.pitch)))
            out.append((nt.start, nt.end, m))
    if not out:
        return [], 0.0
    med = np.median([m for _, _, m in out])
    shift = 12 * round((69 - med) / 12)              # מנעד נוח לכלי
    return [(s, e, m + shift) for s, e, m in out], out[0][0]


class _Track:
    def __init__(self, n):
        self.buf = np.zeros(n, dtype=np.float32)
        self.events = []          # (זמן, midi או שם תוף, אורך, עוצמה) - לייצוא MIDI

    def add(self, x, t, ev=None):
        if ev is not None:
            self.events.append((t,) + ev)
        i = int(t * SR)
        if i < 0:
            x = x[-i:]
            i = 0
        if x.ndim == 2 and self.buf.ndim == 1:          # הגיע צליל סטריאו - הערוץ עובר לסטריאו
            self.buf = np.stack([self.buf, self.buf], axis=1)
        e = min(len(self.buf), i + len(x))
        if e > i:
            if self.buf.ndim == 2 and x.ndim == 1:
                self.buf[i:e] += x[:e - i, None]
            else:
                self.buf[i:e] += x[:e - i]


class Timeline:
    """פעמות מורחבות קדימה ואחורה, כולל מבוא."""

    def __init__(self, a, intro_bars=2):
        self.meter = getattr(a, "meter", 4)
        self.intro_bars = intro_bars
        if a.steady:
            b = np.asarray(a.beats, float)
            period = float(np.median(np.diff(b)))
            pre = intro_bars * self.meter
            back = b[0] - period * np.arange(pre, 0, -1)
            last_needed = a.duration + 3 * self.meter * period
            fwd = []
            t = b[-1]
            while t < last_needed:
                t += period
                fwd.append(t)
            self.beats = np.concatenate([back, b, fwd])
            self.bar0 = a.downbeat          # = תחילת תיבת המבוא הראשונה ברשימה המורחבת
            self.period = period
            self.lead = max(0.0, -self.beats[0]) + 0.3
        else:
            self.period = 1.0
            self.lead = 1.5
            self.beats = None

    def beat_time(self, pos):
        b = self.beats
        i = int(np.floor(pos))
        frac = pos - i
        i = min(max(i, 0), len(b) - 2)
        return b[i] + frac * (b[i + 1] - b[i]) + self.lead


def _chord_at(a, t, default):
    for s, e, c in a.chords:
        if s - 0.05 <= t < e:
            return c
    if a.chords and t < a.chords[0][0]:
        return a.chords[0][2]
    return default


def render(a, style, progress=None, rng_seed=7):
    rng = np.random.default_rng(rng_seed)
    last_voice = max([nt.end for nt in a.notes] + [1.0])
    # מבוא אמיתי: כשהשיר ארוך מספיק, כלי מנגן את 4 התיבות הראשונות של המנגינה לפני שהזמר נכנס
    INTRO_MEL = 4 if (a.steady and style.get("intro", True) and a.notes) else 0
    tl = Timeline(a)
    if INTRO_MEL and last_voice > 3 * INTRO_MEL * tl.period * tl.meter:
        tl = Timeline(a, intro_bars=2 + INTRO_MEL)
    else:
        INTRO_MEL = 0
    IB = tl.intro_bars
    meter = tl.meter
    free = None
    if not a.steady:
        free = free_plan(a, style, chords_for(a.tonic, a.mode)[0])
        tl.lead = free["lead"]
    tp = getattr(a, "transpose", 0)
    compound = bool(getattr(a, "compound", False))
    sub = 3 if compound else 2                       # חלוקת הפעמה
    tonic_chord = chords_for(a.tonic, a.mode)[0]
    rich = style.get("rich_chords", False)
    total = tl.lead + a.duration + 8.0 + (free["extra"] if free else 0.0)
    n = int(total * SR)
    tracks = []
    tun = a.tuning
    specs = style["tracks"] if a.steady else style.get("free", style["tracks"])
    levels = sections(a, tl, last_voice) if a.steady else [1]
    bar_sec = tl.period * meter if a.steady else 1.0
    # סולו בסוף: המשפט האחרון של המנגינה מנוגן בכלי, ורק אחריו אקורד הסיום
    solo, solo_from = (outro_melody(a, tl, last_voice) if a.steady and style.get("solo", True)
                       else ([], 0.0))
    outro_bars = 0
    if solo:
        outro_bars = int(np.ceil((last_voice - solo_from) / bar_sec + 0.25))
        n = int((total + outro_bars * bar_sec) * SR)
    end_voice = last_voice + outro_bars * bar_sec
    if a.steady:
        # רשת הפעמות חייבת להמשיך עד אחרי הסולו ואקורד הסיום
        need = end_voice + 4 * bar_sec
        extra = []
        t = tl.beats[-1]
        while t < need:
            t += tl.period
            extra.append(t)
        if extra:
            tl.beats = np.concatenate([tl.beats, extra])
        n = max(n, int((tl.lead + need + 2 * bar_sec) * SR))
    warp = lambda t: t                               # שינוי זמן בסיום (האטה)
    if a.steady and style.get("ritardando", True):
        # האטה בסיום (ריטרדנדו): שתי התיבות האחרונות לפני אקורד הסיום מואטות בהדרגה, כמו בהופעה חיה
        old = tl.beats.copy()
        rel = old - (end_voice + 0.3 - 2 * bar_sec)
        k0 = int(np.searchsorted(rel, 0))
        if 0 < k0 < len(old) - 1:
            gaps = np.diff(old)
            K = 2 * meter
            for j in range(k0, len(gaps)):
                x = min(1.0, (j - k0 + 1) / K)
                gaps[j] *= 1 + 0.45 * x * x
            new = np.concatenate([[old[0]], old[0] + np.cumsum(gaps)])
            tl.beats = new
            n = int((total + outro_bars * bar_sec + 3 * bar_sec) * SR)
            warp = lambda t, o=old + tl.lead, w=new + tl.lead: float(np.interp(t, o, w)) if t > o[k0] else t

    sing0 = (tl.beat_time(tl.bar0 + IB * tl.meter) - tl.lead) if a.steady else 0.0
    intro_off = INTRO_MEL * bar_sec               # במבוא - האקורדים של תחילת השיר

    # פתיח: בפעמה האחרונה לפני שהזמר נכנס הליווי עובר לדרגה החמישית - 'מזמין' את הכניסה
    dominant = next((c for c in chords_for(a.tonic, a.mode) if c["degree"] == "V"), None)
    first_chord = _chord_at(a, 0.05, tonic_chord)
    turn = (a.steady and dominant is not None and style.get("intro", True)
            and first_chord.get("root") == tonic_chord["root"])

    def chord_at(tv):
        if turn and sing0 - tl.period * 1.02 <= tv < sing0 - 0.01:
            return dict(dominant, seventh=10)
        if INTRO_MEL and sing0 - intro_off <= tv < sing0 - 0.01:
            tv += intro_off
        return enrich(_chord_at(a, tv, tonic_chord), a.mode, rich)

    def level_at(phrase_bar):
        if phrase_bar < 0:
            return 0
        p = phrase_bar // PHRASE
        return levels[p] if p < len(levels) else 1

    mod_t = getattr(a, "modulate_at", None)

    final = {}                       # אקורד הסיום: זמן ואורך - לכלי הסולו ולקבוצת הנשיפה

    def play(out, inst, m, d, v, t, section=False):
        up = tp + (MOD_UP if mod_t is not None and t - tl.lead >= mod_t - 0.03 else 0)
        if inst in BRASS:
            inst = brass_voice(inst, m + up)
        if section and inst in BRASS and d >= 0.25:
            # קבוצת נשיפה: שני נגנים על כל צליל - השני נכנס רגע אחרי ומכוון מעט אחרת
            out.add(synth.render_note(inst, m + up, d, v, tun) * np.float32(0.78), t, (m + up, d, v))
            out.add(synth.render_note(inst, m + up, d, v * 0.85, tun + 0.07) * np.float32(0.6), t + 0.014)
            return
        out.add(synth.render_note(inst, m + up, d, v, tun), t, (m + up, d, v))

    for ti, tr in enumerate(specs):
        out = _Track(n)
        inst = tr["instrument"]
        oct_ = tr.get("octave", 3)
        prev_voicing = None
        layer = tr.get("enter", 0) >= 8          # כלי 'שכבה' - מנגן רק בפזמונים
        if a.steady:
            bar_events = to_compound(tr["bar"]) if compound else [ev for ev in tr["bar"] if ev["t"] < meter]
            fill_events = to_compound(tr["fill"]) if (compound and tr.get("fill")) else tr.get("fill")
            nb = len(tl.beats)
            bar = 0
            while True:
                pos0 = tl.bar0 + bar * meter
                if pos0 + meter >= nb - 1:
                    break
                t_bar = tl.beat_time(pos0) - tl.lead      # בזמן השירה
                if t_bar > end_voice + 0.3:
                    # תיבת סיום: אקורד טוניקה ארוך
                    t = tl.beat_time(pos0)
                    dur = (tl.beat_time(pos0 + 1) - tl.beat_time(pos0)) * meter * 1.4   # אקורד ארוך
                    final.update(t=t, dur=dur)
                    if inst == "drums":
                        for dn, dv in (("crash", 0.85), ("kick", 1.0)):
                            out.add(synth.render_drum(dn, dv), t, (dn, 0.3, dv))
                    else:
                        # אקורד סיום מלא: הצליל של הכלי + האקורד כולו + שורש נמוך
                        fin = enrich(tonic_chord, a.mode, rich)
                        fin = dict(fin, seventh=None) if not rich else fin
                        ns = set(_note_for(tr["bar"][0]["n"], fin, oct_))
                        if inst in BASS:
                            low = min(ns) - 12
                            if low + tp >= 28:
                                ns.add(low)                       # הבס מסיים גם באוקטבה הנמוכה - סיום 'מלא'
                        else:
                            ns |= set(_note_for("chord", fin, oct_))
                        # פסנתר, גיטרה ונבל 'פורטים' את אקורד הסיום מלמטה למעלה, כמו נגן אמיתי
                        roll = 0.035 if inst in STRUMMED else 0.0
                        for k, m in enumerate(sorted(ns)):
                            play(out, inst, m, dur, 0.62 if inst not in BRASS else 0.75, t + k * roll,
                                 section=True)
                    break
                # מבנה: מבוא (2 תיבות), כלים שנכנסים בהדרגה, מילוי תופים בסוף כל משפט
                phrase_bar = bar - IB
                lvl = level_at(phrase_bar)
                last_phrase = len(levels) >= 3 and phrase_bar // PHRASE == len(levels) - 1
                in_outro = t_bar > last_voice + 0.3
                if bar >= IB and phrase_bar < tr.get("enter", 0) and not in_outro:
                    bar += 1
                    continue
                if layer and lvl == 0 and not in_outro:
                    bar += 1
                    continue
                evs = bar_events
                end_of_phrase = bar == IB - 1 or (bar >= IB and phrase_bar % PHRASE == PHRASE - 1)
                next_lvl = level_at(phrase_bar + 1)
                if inst == "drums" and end_of_phrase and tr.get("fill"):
                    fill = fill_events or [{"t": meter - 1, "n": "snare", "v": 0.6}]
                    f0 = min(e["t"] for e in fill)
                    if next_lvl > lvl and synth.has_drum("tom_hi"):
                        # כניסה לפזמון: מילוי טומים שיורד מגבוה לנמוך
                        fill = [{"t": meter - 1, "n": "tom_hi", "v": 0.75},
                                {"t": meter - 1 + 1 / sub, "n": "tom_hi", "v": 0.7},
                                {"t": meter - 1 + (2 / 3 if compound else 0.75), "n": "tom_low", "v": 0.85}]
                        f0 = meter - 1
                    elif synth.has_drum("tom_hi") and phrase_bar >= 0:
                        # מילויים מתחלפים - כל משפט נגמר קצת אחרת
                        k = (phrase_bar // PHRASE) % 3
                        if k == 1:
                            fill = [{"t": meter - 1 + j / (3 if compound else 4), "n": "snare",
                                     "v": 0.45 + 0.12 * j} for j in range(3 if compound else 4)]
                            f0 = meter - 1
                        elif k == 2:
                            fill = [{"t": meter - 1, "n": "snare", "v": 0.7},
                                    {"t": meter - 1 + 1 / sub, "n": "tom_hi", "v": 0.7},
                                    {"t": meter - 1 + (2 / 3 if compound else 0.75), "n": "tom_low", "v": 0.8}]
                            f0 = meter - 1
                    evs = [e for e in bar_events if e["t"] < f0] + [e for e in fill if e["t"] < meter]
                new_phrase = bar >= IB and phrase_bar % PHRASE == 0
                if inst == "drums" and new_phrase and (tr.get("crash_on_phrase") or lvl > level_at(phrase_bar - 1)):
                    t = tl.beat_time(pos0)
                    cv = 0.7 if lvl else 0.5
                    out.add(synth.render_drum("crash", cv), t, ("crash", 0.3, cv))
                if inst == "drums" and last_phrase and not in_outro:
                    # פזמון אחרון: יותר אנרגיה - מצילה סגורה בשמיניות
                    have = {(e["t"], e["n"]) for e in evs}
                    evs = evs + [{"t": k / sub, "n": "hat", "v": 0.35 + 0.1 * (k % sub == 0)}
                                 for k in range(sub * meter) if (k / sub, "hat") not in have]
                if inst == "drums" and lvl == 0 and bar >= IB:
                    # בבית: בלי מצילות פתוחות וטמבורין - נשמע רגוע יותר
                    evs = [e for e in evs if e["n"] not in ("open_hat", "tambourine", "crash")]
                # הפתיח נבנה בהדרגה (קרשנדו) עד הכניסה של הזמר
                if inst in BASS and end_of_phrase and bar >= IB and not compound and not in_outro \
                        and style.get("bass_runs", True):
                    # הבס 'רץ' בסוף כל משפט: שני צלילים עולים אל האקורד הבא
                    evs = [e for e in evs if e["t"] < meter - 1] + \
                          [{"t": meter - 1, "n": "run2", "v": 0.7, "d": 0.45},
                           {"t": meter - 0.5, "n": "run1", "v": 0.78, "d": 0.45}]
                lift = (0.7 + 0.22 * bar / max(1, IB - 1)) if bar < IB else \
                    (0.86 if lvl == 0 else (1.07 if last_phrase else 1.0))
                if inst == "drums" and INTRO_MEL and bar == IB - INTRO_MEL and bar > 0:
                    cv = 0.45                                  # מצילה רכה כשהמנגינה של הפתיח מתחילה
                    out.add(synth.render_drum("crash", cv), tl.beat_time(pos0), ("crash", 0.3, cv))
                t_next = tl.beat_time(pos0 + meter) - tl.lead
                if t_next > end_voice + 0.3 and bar > IB:
                    # התיבה האחרונה לפני אקורד הסיום: 'גלגול' שמתגבר אל תוך האקורד
                    if inst == "drums" and any(e["n"] == "snare" for e in bar_events):
                        evs = [e for e in evs if e["t"] < meter - 1] + \
                              [{"t": meter - 1 + k / 6, "n": "snare", "v": 0.3 + 0.11 * k} for k in range(6)]
                    elif inst == "timpani":
                        evs = [e for e in evs if e["t"] < meter - 1] + \
                              [{"t": meter - 1 + k / 4, "n": "root", "v": 0.45 + 0.13 * k, "d": 0.3} for k in range(4)]
                for ev in evs:
                    p = pos0 + ev["t"]
                    t = tl.beat_time(p) + rng.normal(0, 0.006)
                    accent = 1.06 if ev["t"] == 0 else (0.94 if ev["t"] % 1 else 1.0)   # פעמה ראשונה מודגשת
                    v = float(np.clip((ev.get("v", 0.8) + rng.normal(0, 0.06)) * lift * accent, 0.1, 1.0))
                    if inst == "drums":
                        if bar == 0 and ev["n"] in ("snare", "tambourine"):
                            continue
                        out.add(synth.render_drum(ev["n"], v), t, (ev["n"], 0.1, v))
                        continue
                    dur = max(0.08, ev.get("d", 1) * tl.period)
                    # צליל ארוך שעובר החלפת אקורד - מתחלק לחלקים
                    tv = t - tl.lead
                    cuts = [tv] + [cs for cs, _, _ in a.chords if tv + 0.15 < cs < tv + dur - 0.15] + [tv + dur]
                    for ci in range(len(cuts) - 1):
                        ch = chord_at(cuts[ci] + 0.02)
                        d = cuts[ci + 1] - cuts[ci]
                        vv = v if ci == 0 else v * 0.8
                        if ev["n"] in ("run1", "run2"):
                            # ריצה אל השורש של האקורד הבא, בצלילי הסולם
                            sc = set(scale_pcs(a.tonic, a.mode))
                            nxt = chord_at(tl.beat_time(pos0 + meter) - tl.lead + 0.05)
                            cur = _note_for("root", ch, oct_)[0]
                            tgt = cur + ((nxt["root"] - cur) % 12)
                            if tgt - cur > 6:
                                tgt -= 12
                            one = step_below(tgt, sc)
                            notes = [one if ev["n"] == "run1" else step_below(one, sc)]
                        else:
                            notes = _note_for(ev["n"], ch, oct_)
                        if inst in BASS and lvl == 1 and bar % 2 == 1 and len(notes) == 1 and not in_outro \
                                and meter - 2 <= ev["t"] < meter - 1 and style.get("bass_runs", True):
                            top = _note_for("root", ch, oct_)[0] + 12
                            if top <= 55:
                                notes = [top]                    # בפזמון: קפיצה לאוקטבה - נותן 'דחיפה'
                        if ev["n"] == "chord":
                            notes = voice_lead(notes, prev_voicing)
                            prev_voicing = notes
                            if lvl == 1 and (phrase_bar // PHRASE) % 2 == 1 and inst not in BASS:
                                notes = notes + [notes[0] + 12]          # פזמון חוזר: אקורד פתוח ומלא יותר
                        elif inst in BASS and ev is bar_events[-1] and ev["t"] >= meter - 1 and len(notes) == 1:
                            # 'הליכה' של הבס: צליל מעבר אל השורש של האקורד הבא
                            nxt = chord_at(tv + tl.period * (meter - ev["t"]) + 0.05)
                            if nxt["root"] != ch["root"] and rng.random() < 0.7:
                                tgt = notes[0] + ((nxt["root"] - notes[0]) % 12)
                                if tgt - notes[0] > 6:
                                    tgt -= 12
                                # צליל מעבר מהסולם (מלמטה או מלמעלה); כשאין - חצי טון מתחת
                                sc = set(scale_pcs(a.tonic, a.mode))
                                near = [q for q in (tgt - 1, tgt + 1, tgt - 2, tgt + 2) if q % 12 in sc]
                                notes = [near[int(rng.random() < 0.3) % len(near)] if near else tgt - 1]
                        for k, m in enumerate(notes):
                            play(out, inst, m, d, vv, cuts[ci] + tl.lead + k * ev.get("strum", 0.0),
                                 section=True)
                bar += 1
                if progress and ti == 0:
                    progress(min(95, int(100 * t_bar / max(1, a.duration))))
        else:
            for s, e, ch in free["segs"]:
                ch = enrich(ch, a.mode, rich)
                if inst == "drums":
                    continue
                for ev in tr["seg"]:
                    d = (e - s + 0.3) if ev["d"] == "seg" else ev["d"]
                    v = ev.get("v", 0.7)
                    for k, m in enumerate(_note_for(ev["n"], ch, oct_)):
                        play(out, inst, m, d, v, s + tl.lead + ev["t"] + k * ev.get("strum", 0.0))
        tracks.append((tr, out.buf, out.events))
    lead = _lead_instrument(style)
    if solo or INTRO_MEL or (free and free["notes"]):
        out = _Track(n)
        if free:
            # קצב חופשי: פתיח במנגינה של המשפט הראשון, 'תשובה' לזמר בסוף, והטוניקה עם אקורד הסיום
            for t0, d, m, v in free["notes"]:
                play(out, lead, m, max(0.12, d), v, t0 + tl.lead + rng.normal(0, 0.01))
            ft, fd = free["final"]
            play(out, lead, 72 + (a.tonic - 72) % 12, fd * 0.9, 0.5, ft + tl.lead + 0.12)
        off = (outro_bars * bar_sec)
        for s0, e0, m in solo:
            t = warp(s0 + off + tl.lead) + rng.normal(0, 0.008)
            d = warp(e0 + off + tl.lead) - warp(s0 + off + tl.lead)
            play(out, lead, m, max(0.1, d * 0.95), 0.72, t)
        if INTRO_MEL:
            scale = set(scale_pcs(a.tonic, a.mode))
            half = sing0 - (INTRO_MEL / 2) * bar_sec           # החצי השני של הפתיח
            for s0, e0, m in intro_melody(a, tl, INTRO_MEL):
                j = rng.normal(0, 0.008)
                play(out, lead, m, max(0.1, (e0 - s0) * 0.95), 0.66, s0 + tl.lead + j)
                if s0 >= half - 0.05 and style.get("intro_thirds", True):
                    # קול שני בטרצה מתחת למנגינה - הפתיח 'מתמלא' לקראת הכניסה של הזמר
                    play(out, lead, third_below(m, scale), max(0.1, (e0 - s0) * 0.95), 0.4, s0 + tl.lead + j + 0.01)
        if final and solo:
            # אחרי הסולו: הכלי המוביל מסיים על הטוניקה ומחזיק אותה עם אקורד הסיום
            top = 72 + (a.tonic - 72) % 12
            play(out, lead, top, final["dur"] * 0.95, 0.6, final["t"])
        spec = {"instrument": lead, "volume": 0.75, "pan": 0.15, "solo": True}
        tracks.append((spec, out.buf, out.events))
    insts = {tr["instrument"] for tr in specs} | {lead}
    from . import sampler
    if a.steady and style.get("brass_hits", True) and (insts & BRASS) and sampler.has("trumpet"):
        # קבוצת נשיפה: הרמות אל הפזמונים, דקירות באמצע הפזמון, וצליל עליון באקורד הסיום
        hits = brass_hits(a, tl, levels, IB, chord_at, last_voice, compound)
        out = _Track(n)
        for pos, beats_len, ms, v in hits:
            t = tl.beat_time(pos) + rng.normal(0, 0.005)
            d = max(0.1, beats_len * tl.period)
            for m in ms:
                play(out, "trumpet" if "trumpet" in insts or m > 64 else "brass", m, d, v, t, section=True)
        if final:
            for m in (67 + (a.tonic - 67) % 12, 72 + (a.tonic + 7 - 72) % 12):
                play(out, "trumpet", m, final["dur"] * 0.9, 0.78, final["t"], section=True)
        if out.events:
            spec = {"instrument": "trumpet", "volume": 0.4, "pan": 0.3, "hits": True}
            tracks.append((spec, out.buf, out.events))
    if a.steady and style.get("counter", True):
        cm = counter_melody(a, tl, chord_at, rng, sing0, last_voice)
        if cm:
            out = _Track(n)
            for t0, d, m, v in cm:
                play(out, lead, m, d, v, t0 + tl.lead + rng.normal(0, 0.006))
            spec = {"instrument": lead, "volume": 0.42, "pan": -0.2, "counter": True}
            tracks.append((spec, out.buf, out.events))
    return tracks, tl.lead
