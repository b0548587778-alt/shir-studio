"""כל שלבי העבודה: ניקוי -> ניתוח -> תיקון קול -> ליווי -> ערבוב."""
import numpy as np

from .audio.denoise import denoise
from .audio.psola import shift
from .audio.mix import mix
from .music.analysis import analyze
from .music.arrange import render
from .music.theory import key_name


class Song:
    def __init__(self, raw):
        self.raw = raw
        self.clean = None
        self.tuned = None
        self.analysis = None

    def prepare(self, progress):
        """שלבים שלא תלויים בסגנון - נעשים פעם אחת לכל שיר."""
        progress(2, "מנקה רעשי רקע...")
        self.clean = denoise(self.raw, progress=lambda p: progress(2 + p * 0.18, None))
        progress(22, "מזהה את המנגינה והקצב...")
        self.analysis = analyze(self.clean, progress=lambda p: progress(22 + p * 0.2, None))
        progress(45, "מתקן את הקול...")
        self.tuned = shift(self.clean, self.analysis.f0, self.analysis.correction)

    def next_key(self):
        """הליווי לא מתאים? עוברים לסולם הבא בסדר ההתאמה."""
        from .music.analysis import set_key
        set_key(self.analysis, self.analysis.key_index + 1)
        self.tuned = shift(self.clean, self.analysis.f0, self.analysis.correction)

    def make(self, style, progress):
        if self.tuned is None:
            self.prepare(progress)
        progress(55, "מוסיף ליווי...")
        tracks, lead = render(self.analysis, style, progress=lambda p: progress(55 + p * 0.3, None))
        progress(88, "מערבב את הקול והליווי...")
        out = mix(self.tuned, tracks, lead, style)
        progress(100, None)
        return out

    def info(self):
        a = self.analysis
        return {"key": key_name(a.tonic, a.mode), "tempo": int(round(a.tempo)), "steady": a.steady}
