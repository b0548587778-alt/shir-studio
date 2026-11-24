"""הפרדת קול: מוציאה את השירה מתוך שיר מוכן (שירה + כלי נגינה), ומשאירה את הנגינה בנפרד.
ההפרדה נעשית במודל MDX-Net של פרויקט Ultimate Vocal Remover (רישיון MIT) שרץ בתוך המחשב, בלי אינטרנט."""
import os
import sys

import numpy as np

from .fileio import SR, AudioError

N_FFT = 7680            # הגדרות המודל (UVR-MDX-NET Voc FT)
HOP = 1024
DIM_F = 3072
DIM_T = 256
COMPENSATE = 1.021
CHUNK = HOP * (DIM_T - 1)
TRIM = N_FFT // 2
GEN = CHUNK - 2 * TRIM
N_BINS = N_FFT // 2 + 1
_WIN = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)     # חלון Hann מחזורי
_session = None


def model_path():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base, "shir_studio", "models", "vocals.onnx")


def available():
    """האם ההפרדה אפשרית במחשב הזה (המודל והמנוע שמריץ אותו נמצאים)."""
    if not os.path.exists(model_path()):
        return False
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _load():
    global _session
    if _session is None:
        if not available():
            raise AudioError("הפרדת הקול לא זמינה בהתקנה הזו.\nהתקן מחדש את התוכנה מקובץ ההתקנה העדכני.")
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        _session = ort.InferenceSession(model_path(), sess_options=opts, providers=["CPUExecutionProvider"])
    return _session


def _stft(x):
    """x: (ערוצים, CHUNK) -> (ערוצים, N_BINS, DIM_T) מרוכב. זהה ל-torch.stft עם center=True."""
    xp = np.pad(x, ((0, 0), (TRIM, TRIM)), mode="reflect")
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(DIM_T)[:, None]
    frames = xp[:, idx] * _WIN                                    # (ערוצים, זמן, N_FFT)
    return np.fft.rfft(frames, axis=-1).transpose(0, 2, 1)


def _istft(spec):
    """ההפך של _stft: (ערוצים, N_BINS, DIM_T) -> (ערוצים, CHUNK)."""
    frames = np.fft.irfft(spec.transpose(0, 2, 1), n=N_FFT, axis=-1) * _WIN
    n = N_FFT + HOP * (DIM_T - 1)
    out = np.zeros((spec.shape[0], n), np.float64)
    norm = np.zeros(n, np.float64)
    w2 = _WIN.astype(np.float64) ** 2
    for t in range(DIM_T):
        out[:, t * HOP: t * HOP + N_FFT] += frames[:, t]
        norm[t * HOP: t * HOP + N_FFT] += w2
    out /= np.maximum(norm, 1e-8)
    return out[:, TRIM: TRIM + CHUNK]


def _vocals_of(chunk, run):
    """קטע אחד (2, CHUNK) -> השירה שבו (2, CHUNK)."""
    spec = _stft(chunk)
    x = np.stack([spec[0].real, spec[0].imag, spec[1].real, spec[1].imag])[None, :, :DIM_F].astype(np.float32)
    x[:, :, :3, :] = 0                                           # הנמוכים ביותר (מתחת ל-17 הרץ) - לא שירה
    y = 0.5 * run(x) - 0.5 * run(-x)                             # ממוצע של שתי הרצות - פחות רעש של המודל
    full = np.zeros((2, N_BINS, DIM_T), np.complex64)
    full[0, :DIM_F] = y[0, 0] + 1j * y[0, 1]
    full[1, :DIM_F] = y[0, 2] + 1j * y[0, 3]
    return _istft(full)


def separate(stereo, progress=None, run=None):
    """stereo: (דגימות, 2) או מונו. מחזיר (שירה, נגינה) - שתיהן (דגימות, 2), float32.
    run: פונקציה שמריצה את המודל (לבדיקות); ברירת המחדל - המודל האמיתי."""
    x = np.asarray(stereo, dtype=np.float32)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    n = len(x)
    if n < SR:
        raise AudioError("הקובץ קצר מדי להפרדה.")
    if run is None:
        sess = _load()
        run = lambda inp: sess.run(None, {"input": inp})[0]
    pad = GEN - n % GEN
    mix = np.concatenate([np.zeros((2, TRIM), np.float32), x.T, np.zeros((2, pad + TRIM), np.float32)], axis=1)
    steps = range(0, n + pad, GEN)
    voc = np.zeros((2, n + pad), np.float32)
    for k, i in enumerate(steps):
        if progress:
            progress(100.0 * k / len(steps), None)
        part = _vocals_of(mix[:, i: i + CHUNK], run)
        voc[:, i: i + GEN] = part[:, TRIM: TRIM + GEN]
    voc = (voc[:, :n] * COMPENSATE).T.astype(np.float32)
    if progress:
        progress(100.0, None)
    return np.ascontiguousarray(voc), np.ascontiguousarray(x - voc)
