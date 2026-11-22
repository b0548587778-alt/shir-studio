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
    key: tuple = None           # (טוניקה 0-11, 'major'/'minor'/'ahava'/'misheberach') או None = אוטומטי
    tempo_mode: str = "auto"    # auto / manual / free
    bpm: float = 0
    meter: int = 4              # 4 או 3
    chords_per_bar: int = 2     # 1 או 2
    chords_text: str = ""       # אקורדים שהמוזיקאי כתב (ריק = אוטומטי)
    transpose: int = 0          # חצאי טונים
    voice_db: float = 0
    accomp_db: float = 0
    reverb: int = 100           # אחוזים
    harmony: str = "off"        # off / auto / above / below / three  - קול שני (three = שלושה קולות)
    choir: bool = False         # מקהלה: כמה עותקים של הקול עם הבדלים קטנים
    swaps: dict = None          # החלפת כלים בסגנון: {"clarinet": "violin"}

    def prep_key(self):
        return (self.denoise,)


class Song:
    def __init__(self, raw):
        self.raw = raw
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

    def prepare(self, progress, settings=None):
        """שלבים שלא תלויים בסגנון - נעשים פעם אחת לכל שיר."""
        st = settings or Settings()
        progress(2, "מנקה רעשי רקע...")
        self.clean = denoise(self.raw, strength=st.denoise / 100,
                             progress=lambda p: progress(2 + p * 0.18, None))
        progress(22, "מזהה את המנגינה והקצב...")
        self.analysis = analyze(self.clean, progress=lambda p: progress(22 + p * 0.2, None))
        self._prep = st.prep_key()
        self._tune_key = None

    def _retune(self, st):
        a = self.analysis
        k = (st.tune, st.transpose, a.tonic, a.mode, a.key_index)
        if k != self._tune_key:
            corr = a.correction + st.transpose
            self.tuned = shift(self.clean, a.f0, corr)
            self._tune_key = k

    def _make_harmony(self, st):
        a = self.analysis
        if st.harmony == "off":
            self.harmony = None
            return
        k = (st.harmony, st.tune, st.transpose, a.tonic, a.mode, a.key_index, len(a.chords),
             st.chords_text, st.meter, st.tempo_mode, st.bpm)
        if k != self._harm_key:
            from .music.harmony import harmony_shift
            # הקול השני תמיד מתוקן מלא - שלא יתנגש עם הקול הראשי
            full = a.correction / max(a.strength, 1e-3) if a.strength > 0 else a.correction
            modes = ("above", "below") if st.harmony == "three" else (st.harmony,)
            self.harmony = [shift(self.clean, a.f0, full + st.transpose + harmony_shift(a, m))
                            for m in modes]
            self._harm_key = k

    def next_key(self):
        """הליווי לא מתאים? עוברים לסולם הבא בסדר ההתאמה."""
        set_key(self.analysis, self.analysis.key_index + 1)

    def make(self, style, progress, settings=None):
        st = settings or Settings()
        if self.analysis is None or self._prep != st.prep_key():
            self.prepare(progress, st)
        apply_settings(self.analysis, st)
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
        out, stems = mix(self.tuned, tracks, lead, style, accomp_db=st.accomp_db,
                         voice_db=st.voice_db, reverb=st.reverb / 100, stems=True,
                         harmony=self.harmony, choir=st.choir)
        self.last_tracks, self.last_lead, self.last_stems = tracks, lead, stems
        progress(100, None)
        return out

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
        return t, before, after, [(nt.start, nt.end, nt.pitch) for nt in a.notes]

    def info(self):
        a = self.analysis
        return {"key": key_name(a.tonic, a.mode), "tempo": int(round(a.tempo)), "steady": a.steady,
                "tonic": a.tonic, "mode": a.mode, "chords": chords_as_text(a), "meter": a.meter}

    def export_extras(self, folder, base):
        """קבצים נפרדים לקול ולליווי (WAV) וקובץ MIDI."""
        paths = []
        for name, data in (self.last_stems or {}).items():
            p = os.path.join(folder, f"{base} - {name}.wav")
            save(p, np.clip(data, -1, 1))
            paths.append(p)
        a = self.analysis
        melody = [(nt.start, nt.end, round(nt.pitch) + a.transpose) for nt in a.notes]
        p = os.path.join(folder, f"{base}.mid")
        midi.write(p, a.tempo if a.steady else 120.0, melody, self.last_tracks, self.last_lead)
        paths.append(p)
        return paths
