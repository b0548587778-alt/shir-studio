"""בניית הליווי לפי ניתוח השיר וסגנון שנבחר."""
import numpy as np

from ..audio.fileio import SR
from . import synth
from .theory import chords_for

BEATS_PER_BAR = 4


def _note_for(spec, chord, octave, center_prev=None):
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
        notes = []
        for pc in chord["pcs"]:
            m = center - 6 + (pc - (center - 6)) % 12
            notes.append(m)
        return sorted(notes)
    return table.get(spec, [root])


class _Track:
    def __init__(self, n):
        self.buf = np.zeros(n, dtype=np.float32)

    def add(self, x, t):
        i = int(t * SR)
        if i < 0:
            x = x[-i:]
            i = 0
        e = min(len(self.buf), i + len(x))
        if e > i:
            self.buf[i:e] += x[:e - i]


class Timeline:
    """פעמות מורחבות קדימה ואחורה, כולל מבוא."""

    def __init__(self, a, intro_bars=2):
        self.a = a
        if a.steady:
            b = np.asarray(a.beats, float)
            period = float(np.median(np.diff(b)))
            first_bar = a.downbeat
            pre = intro_bars * BEATS_PER_BAR + first_bar  # פעמות לפני תחילת התיבה הראשונה
            back = b[0] - period * np.arange(intro_bars * BEATS_PER_BAR, 0, -1)
            last_needed = a.duration + 3 * BEATS_PER_BAR * period
            fwd = []
            t = b[-1]
            while t < last_needed:
                t += period
                fwd.append(t)
            self.beats = np.concatenate([back, b, fwd])
            self.bar0 = first_bar + intro_bars * BEATS_PER_BAR - intro_bars * BEATS_PER_BAR
            # אינדקס הפעמה של תיבת המבוא הראשונה
            self.bar0 = first_bar
            self.period = period
            self.lead = max(0.0, -self.beats[0]) + 0.3
        else:
            self.period = 1.0
            self.lead = 1.5
            self.beats = None

    def beat_time(self, pos):
        """pos = אינדקס פעמה (עשרוני) ביחס לרשימת הפעמות המורחבת."""
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
    tl = Timeline(a)
    tonic_chord = chords_for(a.tonic, a.mode)[0]
    last_voice = max([nt.end for nt in a.notes] + [1.0])
    total = tl.lead + a.duration + 8.0
    n = int(total * SR)
    tracks = []
    tun = a.tuning
    specs = style["tracks"] if a.steady else style.get("free", style["tracks"])

    for ti, tr in enumerate(specs):
        out = _Track(n)
        inst = tr["instrument"]
        oct_ = tr.get("octave", 3)
        if a.steady:
            intro = 2 * BEATS_PER_BAR
            start_beat = tl.bar0  # תחילת תיבת המבוא (באינדקס המורחב)
            nb = len(tl.beats)
            bar = 0
            ending_done = False
            while True:
                pos0 = start_beat + bar * BEATS_PER_BAR
                if pos0 + BEATS_PER_BAR >= nb - 1:
                    break
                t_bar = tl.beat_time(pos0) - tl.lead      # בזמן השירה
                if t_bar > last_voice + 0.3:
                    # תיבת סיום: אקורד טוניקה ארוך
                    t = tl.beat_time(pos0)
                    dur = tl.period * BEATS_PER_BAR
                    if inst == "drums":
                        out.add(synth.render_drum("crash", 0.8), t)
                        out.add(synth.render_drum("kick", 1.0), t)
                    else:
                        ev = tr["bar"][0]
                        for m in _note_for(ev["n"], tonic_chord, oct_):
                            out.add(synth.render_note(inst, m, dur, 0.6, tun), t)
                    ending_done = True
                    break
                for ev in tr["bar"]:
                    p = pos0 + ev["t"]
                    t = tl.beat_time(p) + rng.normal(0, 0.006)
                    v = float(np.clip(ev.get("v", 0.8) + rng.normal(0, 0.06), 0.1, 1.0))
                    if bar < 2:
                        v *= 0.85
                    if inst == "drums":
                        if bar == 0 and ev["n"] in ("snare", "tambourine"):
                            continue
                        out.add(synth.render_drum(ev["n"], v), t)
                        continue
                    dur = max(0.08, ev.get("d", 1) * tl.period)
                    # צליל ארוך שעובר החלפת אקורד - מתחלק לחלקים
                    tv = t - tl.lead
                    cuts = [tv] + [cs for cs, _, _ in a.chords if tv + 0.15 < cs < tv + dur - 0.15] + [tv + dur]
                    for ci in range(len(cuts) - 1):
                        ch = _chord_at(a, cuts[ci] + 0.02, tonic_chord)
                        d = cuts[ci + 1] - cuts[ci]
                        vv = v if ci == 0 else v * 0.8
                        for k, m in enumerate(_note_for(ev["n"], ch, oct_)):
                            out.add(synth.render_note(inst, m, d, vv, tun),
                                    cuts[ci] + tl.lead + k * ev.get("strum", 0.0))
                bar += 1
                if progress and ti == 0:
                    progress(min(95, int(100 * t_bar / max(1, a.duration))))
            if inst == "drums" and not ending_done:
                pass
        else:
            segs = list(a.chords) or [(0, a.duration, tonic_chord)]
            # מבוא: אקורד הפתיחה לפני השירה
            segs = [(-1.2, segs[0][0], segs[0][2])] + segs
            segs.append((segs[-1][1], segs[-1][1] + 3.0, tonic_chord))
            for s, e, ch in segs:
                if inst == "drums":
                    continue
                for ev in tr["seg"]:
                    d = (e - s + 0.3) if ev["d"] == "seg" else ev["d"]
                    v = ev.get("v", 0.7)
                    for k, m in enumerate(_note_for(ev["n"], ch, oct_)):
                        out.add(synth.render_note(inst, m, d, v, tun),
                                s + tl.lead + ev["t"] + k * ev.get("strum", 0.0))
        tracks.append((tr, out.buf))
    return tracks, tl.lead
