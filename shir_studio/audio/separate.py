"""הפרדת קול: מוציאה את השירה מתוך שיר מוכן (שירה + כלי נגינה), ומשאירה את הנגינה בנפרד.
אפשר גם להפריד את הנגינה לתופים, בס ושאר הכלים.
ההפרדה נעשית במודלים מסוג MDX-Net (פרויקט Ultimate Vocal Remover ו-KUIELab, רישיון MIT) שרצים בתוך המחשב."""
import os
import sys

import numpy as np

from .fileio import SR, AudioError

HOP = 1024
_session = {}


def _base():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class Model:
    """מודל הפרדה אחד (MDX-Net) וההגדרות שלו: גודל חלון הניתוח, כמה תדרים וכמה זמן בכל קטע."""

    def __init__(self, name, n_fft, dim_f, dim_t, compensate):
        self.name, self.n_fft, self.dim_f, self.dim_t, self.compensate = name, n_fft, dim_f, dim_t, compensate
        self.chunk = HOP * (dim_t - 1)
        self.trim = n_fft // 2
        self.gen = self.chunk - 2 * self.trim
        self.n_bins = n_fft // 2 + 1
        self.win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n_fft) / n_fft)).astype(np.float32)   # Hann מחזורי

    def path(self):
        return os.path.join(_base(), "shir_studio", "models", self.name + ".onnx")

    def stft(self, x):
        """x: (ערוצים, chunk) -> (ערוצים, n_bins, dim_t) מרוכב. זהה ל-torch.stft עם center=True."""
        xp = np.pad(x, ((0, 0), (self.trim, self.trim)), mode="reflect")
        idx = np.arange(self.n_fft)[None, :] + HOP * np.arange(self.dim_t)[:, None]
        return np.stack([np.fft.rfft(xp[c][idx] * self.win, axis=-1).T for c in range(x.shape[0])])

    def istft(self, spec):
        """ההפך של stft: (ערוצים, n_bins, dim_t) -> (ערוצים, chunk)."""
        n = self.n_fft + HOP * (self.dim_t - 1)
        out = np.zeros((spec.shape[0], n), np.float64)
        norm = np.zeros(n, np.float64)
        w2 = self.win.astype(np.float64) ** 2
        for c in range(spec.shape[0]):
            frames = np.fft.irfft(spec[c].T, n=self.n_fft, axis=-1) * self.win
            for t in range(self.dim_t):
                out[c, t * HOP: t * HOP + self.n_fft] += frames[t]
        for t in range(self.dim_t):
            norm[t * HOP: t * HOP + self.n_fft] += w2
        out /= np.maximum(norm, 1e-8)
        return out[:, self.trim: self.trim + self.chunk]

    def session(self):
        if self.name not in _session:
            if not os.path.exists(self.path()) or not _engine():
                raise AudioError("הפרדת הקול לא זמינה בהתקנה הזו.\nהתקן מחדש את התוכנה מקובץ ההתקנה העדכני.")
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            _session[self.name] = ort.InferenceSession(self.path(), sess_options=opts,
                                                       providers=["CPUExecutionProvider"])
        return _session[self.name]

    def part(self, chunk, run):
        """קטע אחד (2, chunk) -> החלק המבוקש שבו (2, chunk)."""
        spec = self.stft(chunk)
        f = self.dim_f
        x = np.stack([spec[0].real, spec[0].imag, spec[1].real, spec[1].imag])[None, :, :f].astype(np.float32)
        x[:, :, :3, :] = 0                                           # הנמוכים ביותר - לא מוזיקה
        y = 0.5 * run(x) - 0.5 * run(-x)                             # ממוצע של שתי הרצות - פחות רעש של המודל
        full = np.zeros((2, self.n_bins, self.dim_t), np.complex64)
        full[0, :f] = y[0, 0] + 1j * y[0, 1]
        full[1, :f] = y[0, 2] + 1j * y[0, 3]
        return self.istft(full)

    def extract(self, x, progress=None, run=None):
        """x: (דגימות, 2). מחזיר את החלק שהמודל מוציא (שירה / תופים / בס), באותו גודל."""
        n = len(x)
        if run is None:
            sess = self.session()
            run = lambda inp: sess.run(None, {"input": inp})[0]
        pad = self.gen - n % self.gen
        mix = np.concatenate([np.zeros((2, self.trim), np.float32), x.T,
                              np.zeros((2, pad + self.trim), np.float32)], axis=1)
        steps = range(0, n + pad, self.gen)
        out = np.zeros((2, n + pad), np.float32)
        for k, i in enumerate(steps):
            if progress:
                progress(100.0 * k / len(steps), None)
            part = self.part(mix[:, i: i + self.chunk], run)
            out[:, i: i + self.gen] = part[:, self.trim: self.trim + self.gen]
        return np.ascontiguousarray((out[:, :n] * self.compensate).T.astype(np.float32))


VOCALS = Model("vocals", 7680, 3072, 256, 1.021)        # UVR-MDX-NET Voc FT
DRUMS = Model("drums", 4096, 2048, 512, 1.035)          # kuielab_a_drums
BASS = Model("bass", 16384, 2048, 512, 1.035)           # kuielab_a_bass
STEM_NAMES = ("שירה", "תופים", "בס", "כלים אחרים")

# ההגדרות של מודל השירה - בשמות הקצרים שלהן
N_FFT, DIM_F, DIM_T, COMPENSATE = VOCALS.n_fft, VOCALS.dim_f, VOCALS.dim_t, VOCALS.compensate
CHUNK, TRIM, GEN, N_BINS = VOCALS.chunk, VOCALS.trim, VOCALS.gen, VOCALS.n_bins
_stft, _istft = VOCALS.stft, VOCALS.istft


def model_path():
    return VOCALS.path()


def _engine():
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def available():
    """האם ההפרדה אפשרית במחשב הזה (המודל והמנוע שמריץ אותו נמצאים)."""
    return os.path.exists(VOCALS.path()) and _engine()


def stems_available():
    """האם אפשר להפריד גם לכלים (תופים ובס)."""
    return available() and os.path.exists(DRUMS.path()) and os.path.exists(BASS.path())


def _stereo(stereo):
    x = np.asarray(stereo, dtype=np.float32)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    if len(x) < SR:
        raise AudioError("הקובץ קצר מדי להפרדה.")
    return x


def separate(stereo, progress=None, run=None):
    """stereo: (דגימות, 2) או מונו. מחזיר (שירה, נגינה) - שתיהן (דגימות, 2), float32.
    run: פונקציה שמריצה את המודל (לבדיקות); ברירת המחדל - המודל האמיתי."""
    x = _stereo(stereo)
    voc = VOCALS.extract(x, progress, run)
    if progress:
        progress(100.0, None)
    return voc, np.ascontiguousarray(x - voc)


def separate_stems(stereo, progress=None, run=None):
    """הפרדה לכלים: מחזיר {שירה, תופים, בס, כלים אחרים} - כל אחד (דגימות, 2). הסכום שלהם הוא השיר כולו."""
    x = _stereo(stereo)
    step = lambda k: (lambda pct, m=None: progress((k * 100 + pct) / 3, None)) if progress else None
    voc = VOCALS.extract(x, step(0), run)
    music = x - voc
    drums = DRUMS.extract(music, step(1), run)
    bass = BASS.extract(music - drums, step(2), run)
    other = music - drums - bass
    if progress:
        progress(100.0, None)
    return dict(zip(STEM_NAMES, (voc, drums, bass, np.ascontiguousarray(other))))
