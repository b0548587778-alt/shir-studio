"""בניית הליווי לפי ניתוח השיר וסגנון שנבחר."""
import numpy as np

from ..audio.fileio import SR
from . import synth
from .theory import chords_for, scale_pcs

BASS = {"bass", "acoustic_bass"}
LEAD_PREF = ("violin", "clarinet", "flute", "trumpet", "accordion", "guitar", "piano")
PHRASE = 8            # תיבות במשפט


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
    tp = getattr(a, "transpose", 0)
    tonic_chord = chords_for(a.tonic, a.mode)[0]
    rich = style.get("rich_chords", False)
    total = tl.lead + a.duration + 8.0
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

    def chord_at(tv):
        if INTRO_MEL and sing0 - intro_off <= tv < sing0 - 0.01:
            tv += intro_off
        return enrich(_chord_at(a, tv, tonic_chord), a.mode, rich)

    def level_at(phrase_bar):
        if phrase_bar < 0:
            return 0
        p = phrase_bar // PHRASE
        return levels[p] if p < len(levels) else 1

    def play(out, inst, m, d, v, t):
        out.add(synth.render_note(inst, m + tp, d, v, tun), t, (m + tp, d, v))

    for ti, tr in enumerate(specs):
        out = _Track(n)
        inst = tr["instrument"]
        oct_ = tr.get("octave", 3)
        prev_voicing = None
        layer = tr.get("enter", 0) >= 8          # כלי 'שכבה' - מנגן רק בפזמונים
        if a.steady:
            bar_events = [ev for ev in tr["bar"] if ev["t"] < meter]
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
                    if inst == "drums":
                        for dn, dv in (("crash", 0.85), ("kick", 1.0)):
                            out.add(synth.render_drum(dn, dv), t, (dn, 0.3, dv))
                    else:
                        # אקורד סיום מלא: הצליל של הכלי + האקורד כולו + שורש נמוך
                        fin = enrich(tonic_chord, a.mode, rich)
                        fin = dict(fin, seventh=None) if not rich else fin
                        ns = set(_note_for(tr["bar"][0]["n"], fin, oct_))
                        if inst not in BASS:
                            ns |= set(_note_for("chord", fin, oct_))
                        for m in sorted(ns):
                            play(out, inst, m, dur, 0.62, t)
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
                    f0 = min(e["t"] for e in tr["fill"])
                    fill = tr["fill"]
                    if next_lvl > lvl and synth.has_drum("tom_hi"):
                        # כניסה לפזמון: מילוי טומים שיורד מגבוה לנמוך
                        fill = [{"t": meter - 1, "n": "tom_hi", "v": 0.75},
                                {"t": meter - 0.5, "n": "tom_hi", "v": 0.7},
                                {"t": meter - 0.25, "n": "tom_low", "v": 0.85}]
                        f0 = meter - 1
                    elif synth.has_drum("tom_hi") and phrase_bar >= 0:
                        # מילויים מתחלפים - כל משפט נגמר קצת אחרת
                        k = (phrase_bar // PHRASE) % 3
                        if k == 1:
                            fill = [{"t": meter - 1 + j / 4, "n": "snare", "v": 0.45 + 0.12 * j} for j in range(4)]
                            f0 = meter - 1
                        elif k == 2:
                            fill = [{"t": meter - 1, "n": "snare", "v": 0.7}, {"t": meter - 0.5, "n": "tom_hi", "v": 0.7},
                                    {"t": meter - 0.25, "n": "tom_low", "v": 0.8}]
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
                    evs = evs + [{"t": k / 2, "n": "hat", "v": 0.35 + 0.1 * (k % 2 == 0)}
                                 for k in range(2 * meter) if (k / 2, "hat") not in have]
                if inst == "drums" and lvl == 0 and bar >= IB:
                    # בבית: בלי מצילות פתוחות וטמבורין - נשמע רגוע יותר
                    evs = [e for e in evs if e["n"] not in ("open_hat", "tambourine", "crash")]
                lift = 0.82 if bar < IB else (0.86 if lvl == 0 else (1.07 if last_phrase else 1.0))
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
                        notes = _note_for(ev["n"], ch, oct_)
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
                                notes = [tgt - 1 if rng.random() < 0.5 else tgt + 1]
                        for k, m in enumerate(notes):
                            play(out, inst, m, d, vv, cuts[ci] + tl.lead + k * ev.get("strum", 0.0))
                bar += 1
                if progress and ti == 0:
                    progress(min(95, int(100 * t_bar / max(1, a.duration))))
        else:
            segs = list(a.chords) or [(0, a.duration, tonic_chord)]
            segs = [(-1.2, segs[0][0], segs[0][2])] + segs          # מבוא
            segs.append((segs[-1][1], segs[-1][1] + 3.0, tonic_chord))
            for s, e, ch in segs:
                if inst == "drums":
                    continue
                for ev in tr["seg"]:
                    d = (e - s + 0.3) if ev["d"] == "seg" else ev["d"]
                    v = ev.get("v", 0.7)
                    for k, m in enumerate(_note_for(ev["n"], ch, oct_)):
                        play(out, inst, m, d, v, s + tl.lead + ev["t"] + k * ev.get("strum", 0.0))
        tracks.append((tr, out.buf, out.events))
    lead = _lead_instrument(style)
    if solo or INTRO_MEL:
        out = _Track(n)
        off = (outro_bars * bar_sec)
        for s0, e0, m in solo:
            t = warp(s0 + off + tl.lead) + rng.normal(0, 0.008)
            d = warp(e0 + off + tl.lead) - warp(s0 + off + tl.lead)
            play(out, lead, m, max(0.1, d * 0.95), 0.72, t)
        if INTRO_MEL:
            for s0, e0, m in intro_melody(a, tl, INTRO_MEL):
                play(out, lead, m, max(0.1, (e0 - s0) * 0.95), 0.66, s0 + tl.lead + rng.normal(0, 0.008))
        spec = {"instrument": lead, "volume": 0.75, "pan": 0.15, "solo": True}
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
