"""כל שלבי העבודה: ניקוי -> ניתוח -> תיקון קול -> ליווי -> ערבוב."""
from dataclasses import dataclass
import os

import numpy as np

from .audio.denoise import denoise
from .audio.psola import shift
from .audio.mix import mix
from .audio.fileio import save
from .music.analysis import analyze, apply_settings, set_key, chords_as_text
from .music.arrange import render
from .music.theory import key_name
from . import midi


@dataclass
class Settings:
    """הגדרות מתקדמות. ערכי ברירת המחדל = מה שמשתמש רגיל מקבל."""
    denoise: int = 100          # 0-100
    tune: int = 80              # עוצמת תיקון הזיופים 0-100
    key: tuple = None           # (טוניקה 0-11, 'major'/'minor'/'ahava'/'misheberach'/'adonai') או None = אוטומטי
    tempo_mode: str = "auto"    # auto / manual / free
    bpm: float = 0
    meter: int = 4              # 4, 3 או 6 (= 6/8)
    chords_per_bar: int = 2     # 1 או 2
    chords_text: str = ""       # אקורדים שהמוזיקאי כתב (ריק = אוטומטי)
    transpose: int = 0          # חצאי טונים
    voice_db: float = 0
    accomp_db: float = 0
    reverb: int = 100           # אחוזים
    harmony: str = "off"        # off / auto / above / below / three  - קול שני (three = שלושה קולות)
    choir: bool = False         # מקהלה: כמה עותקים של הקול עם הבדלים קטנים
    swaps: dict = None          # החלפת כלים בסגנון: {"clarinet": "violin"}
    sections: list = None       # בית/פזמון ידני לכל משפט: [0, 1, 0, 1] (None = אוטומטי)
    modulate: bool = False      # עליית סולם (חצי טון) בפזמון האחרון - הקול והליווי יחד
    note_edits: dict = None     # תיקון ידני מהגרף: {מפתח הצליל: חצאי טונים, או "off" = בלי תיקון}

    def prep_key(self):
        return (self.denoise,)


class Song:
    def __init__(self, raw, grid=None):
        self.raw = raw
        self.grid = grid              # (פעמות, קצב, קבוע?) ידועים מראש - כששרו על ליווי קיים
        self.clean = None
        self.tuned = None
        self.analysis = None
        self._prep = None
        self._tune_key = None
        self.harmony = None
        self._harm_key = None
        self.last_tracks = None
        self.last_lead = 0.0
        self.last_stems = None
        self.keep_stems = False       # קבצי קול וליווי נפרדים - רק כשמבקשים (חוסך זיכרון)
        self._last_make = None

    def prepare(self, progress, settings=None):
        """שלבים שלא תלויים בסגנון - נעשים פעם אחת לכל שיר."""
        st = settings or Settings()
        progress(2, "מנקה רעשי רקע...")
        self.clean = denoise(self.raw, strength=st.denoise / 100,
                             progress=lambda p: progress(2 + p * 0.18, None))
        progress(22, "מזהה את המנגינה והקצב...")
        self.analysis = analyze(self.clean, progress=lambda p: progress(22 + p * 0.2, None))
        if self.grid:
            from .music.analysis import use_grid
            use_grid(self.analysis, *self.grid)
        self._prep = st.prep_key()
        self._tune_key = None

    def _apply(self, st, modulate=True):
        """מחיל את ההגדרות על הניתוח, וקובע אם ומתי הסולם עולה."""
        from .music.arrange import modulation
        a = self.analysis
        apply_settings(a, st)
        a.sections_override = st.sections
        m = modulation(a) if (st.modulate and modulate) else None
        a.modulate_at, a.modulate_voice = m if m else (None, None)

    def _up(self):
        """עליית הסולם של הקול: חצאי טונים לכל פריים (0 עד הרגע שבו עולים)."""
        from .audio.pitch import FRAME_SEC
        from .music.arrange import MOD_UP
        a = self.analysis
        if a.modulate_voice is None:
            return 0.0
        return np.where(np.arange(len(a.f0)) * FRAME_SEC >= a.modulate_voice, float(MOD_UP), 0.0)

    def _edits_key(self, st):
        return (repr(sorted((st.note_edits or {}).items())), self.analysis.modulate_voice)

    def _retune(self, st):
        a = self.analysis
        k = (st.tune, st.transpose, a.tonic, a.mode, a.key_index) + self._edits_key(st)
        if k != self._tune_key:
            corr = a.correction + st.transpose + self._up()
            self.tuned = shift(self.clean, a.f0, corr)
            self._tune_key = k

    def _make_harmony(self, st):
        a = self.analysis
        if st.harmony == "off":
            self.harmony = None
            return
        k = (st.harmony, st.tune, st.transpose, a.tonic, a.mode, a.key_index, len(a.chords),
             st.chords_text, st.meter, st.tempo_mode, st.bpm) + self._edits_key(st)
        if k != self._harm_key:
            from .music.harmony import harmony_shift
            from .music.analysis import correction_for
            # הקול השני תמיד מתוקן מלא - שלא יתנגש עם הקול הראשי
            full = correction_for(a, 1.0) if a.strength > 0 else a.correction
            modes = ("above", "below") if st.harmony == "three" else (st.harmony,)
            self.harmony = [shift(self.clean, a.f0, full + st.transpose + self._up() + harmony_shift(a, m))
                            for m in modes]
            self._harm_key = k

    def next_key(self):
        """הליווי לא מתאים? עוברים לסולם הבא בסדר ההתאמה."""
        set_key(self.analysis, self.analysis.key_index + 1)

    @staticmethod
    def _style_meter(style, st):
        """סגנון שנכתב למשקל מסוים (ואלס = 3/4, ניגון 6/8) קובע את המשקל, אם המשתמש לא בחר אחרת."""
        import dataclasses
        m = style.get("meter")
        return dataclasses.replace(st, meter=int(m)) if (m in (3, 6) and st.meter == 4) else st

    def make(self, style, progress, settings=None):
        st = self._style_meter(style, settings or Settings())
        if self.analysis is None or self._prep != st.prep_key():
            self.prepare(progress, st)
        self._apply(st)
        # סגנון ווקאלי: מקהלה שלמה מהקול של הזמר עצמו (אם המשתמש לא בחר אחרת)
        voices = style.get("voices")
        if voices and st.harmony == "off":
            import dataclasses
            st = dataclasses.replace(st, harmony=voices.get("harmony", "three"),
                                     choir=voices.get("choir", st.choir))
        progress(45, "מתקן את הקול...")
        self._retune(st)
        if st.harmony != "off":
            progress(50, "מוסיף קול שני...")
        self._make_harmony(st)
        progress(55, "מוסיף ליווי...")
        from .music.styles import apply_swaps
        style = apply_swaps(style, st.swaps)
        tracks, lead = render(self.analysis, style, progress=lambda p: progress(55 + p * 0.3, None))
        progress(88, "מערבב את הקול והליווי...")
        style = dict(style, _tempo=float(self.analysis.tempo) if self.analysis.steady else 90.0)
        res = mix(self.tuned, tracks, lead, style, accomp_db=st.accomp_db,
                  voice_db=st.voice_db, reverb=st.reverb / 100, stems=self.keep_stems,
                  harmony=self.harmony, choir=st.choir)
        out, stems = res if self.keep_stems else (res, None)
        self._last_make = (style, st)
        # שומרים רק את רשימת התווים (לקובץ MIDI) - לא את הצליל של כל כלי, כדי לפנות זיכרון
        self.last_tracks = [(spec, None, events) for spec, _, events in tracks]
        del tracks
        self.last_lead, self.last_stems = lead, stems
        progress(100, None)
        return out

    def preview(self, style, progress, settings=None, seconds=25.0):
        """האזנה מהירה: רק ההתחלה של השיר (בערך 25 שניות) - כדי לבחור סגנון בלי לחכות לשיר כולו."""
        import copy
        st = self._style_meter(style, settings or Settings())
        if self.analysis is None or self._prep != st.prep_key():
            self.prepare(progress, st)
        self._apply(st, modulate=False)          # בהאזנה המהירה שומעים רק את ההתחלה
        self._retune(st)
        a = copy.copy(self.analysis)
        cut = min(a.duration, seconds)
        a.notes = [nt for nt in a.notes if nt.start < cut]
        if not a.notes:
            a.notes = list(self.analysis.notes[:4])
        a.chords = [c for c in a.chords if c[0] < cut + 4]
        a.duration = cut
        progress(60, "מכין האזנה מהירה...")
        from .music.styles import apply_swaps
        style = apply_swaps(style, st.swaps)
        style = dict(style, solo=False, ritardando=False)
        tracks, lead = render(a, style)
        style["_tempo"] = float(a.tempo) if a.steady else 90.0
        voice = self.tuned[: int((cut + 0.5) * 44100)]
        out = mix(voice, tracks, lead, style, accomp_db=st.accomp_db, voice_db=st.voice_db,
                  reverb=st.reverb / 100)
        progress(100, None)
        return out[: int((lead + cut + 2.5) * 44100)]

    def pitch_curves(self, settings=None):
        """לגרף: זמן, גובה הצליל לפני התיקון ואחריו (בחצאי טונים), והצלילים הנקיים שזוהו."""
        from .audio.pitch import hz_to_midi, FRAME_SEC
        a = self.analysis
        f0 = np.asarray(a.f0, dtype=float)
        voiced = f0 > 0
        before = np.full(len(f0), np.nan)
        before[voiced] = hz_to_midi(f0[voiced])
        corr = a.correction if a.correction is not None else np.zeros(len(f0))
        after = before + corr[: len(f0)] + (settings.transpose if settings else 0)
        t = np.arange(len(f0)) * FRAME_SEC
        from .music.analysis import note_targets
        return t, before, after, note_targets(a)

    def phrases(self, style=None):
        """משפטי השיר: [(התחלה, סוף, 0=בית/1=פזמון)] - למסך העריכה."""
        from .music import arrange
        a = self.analysis
        if a is None or not a.steady or not a.notes:
            return []
        tl = arrange.Timeline(a)
        lv_end = max(nt.end for nt in a.notes)
        times = arrange.phrase_times(a, tl, lv_end)
        saved, a.sections_override = getattr(a, "sections_override", None), None   # הניחוש האוטומטי
        lv = arrange.sections(a, tl, lv_end)
        a.sections_override = saved
        return [(s, e, l) for (s, e), l in zip(times, lv)]

    def info(self):
        a = self.analysis
        return {"key": key_name(a.tonic, a.mode), "tempo": int(round(a.tempo)), "steady": a.steady,
                "tonic": a.tonic, "mode": a.mode, "chords": chords_as_text(a), "meter": a.meter,
                "phrases": self.phrases(), "voice": self.voice_info()}

    def voice_info(self):
        """המנעד של הזמר והמלצה לטרנספוזיציה."""
        from .music.analysis import vocal_range, suggest_transpose
        from .music.theory import NOTE_NAMES
        r = vocal_range(self.analysis)
        if r is None:
            return None
        name = lambda m: f"{NOTE_NAMES[int(round(m)) % 12]}{int(round(m)) // 12 - 1}"
        return {"low": name(r[0] + self.analysis.tuning), "high": name(r[1] + self.analysis.tuning),
                "suggest": suggest_transpose(self.analysis)}

    def stems(self, progress=None):
        """הקול והליווי בנפרד. אם לא נשמרו - מכינים את השיר שוב, הפעם עם שניהם."""
        if self.last_stems is None and self._last_make:
            self.keep_stems = True
            try:
                self.make(self._last_make[0], progress or (lambda p, m=None: None), self._last_make[1])
            finally:
                self.keep_stems = False
        return self.last_stems or {}

    def export_extras(self, folder, base):
        """קבצים נפרדים לקול ולליווי (WAV) וקובץ MIDI."""
        self.stems()
        paths = []
        for name, data in (self.last_stems or {}).items():
            p = os.path.join(folder, f"{base} - {name}.wav")
            save(p, np.clip(data, -1, 1))
            paths.append(p)
        a = self.analysis
        from .music.arrange import MOD_UP
        mv = a.modulate_voice
        melody = [(nt.start, nt.end, round(nt.pitch) + a.transpose
                   + (MOD_UP if mv is not None and nt.start >= mv else 0)) for nt in a.notes]
        p = os.path.join(folder, f"{base}.mid")
        midi.write(p, a.tempo if a.steady else 120.0, melody, self.last_tracks, self.last_lead)
        paths.append(p)
        return paths
