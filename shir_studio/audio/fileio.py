"""טעינה ושמירה של קבצי קול."""
from ..i18n import tx
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

SR = 44100


class AudioError(Exception):
    """שגיאה עם הודעה בעברית פשוטה למשתמש."""


def to_mono_sr(data: np.ndarray, sr: int) -> np.ndarray:
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 2:
        data = data.mean(axis=1)
    if sr != SR:
        g = gcd(sr, SR)
        data = resample_poly(data, SR // g, sr // g).astype(np.float32)
    return data


def load(path: str) -> np.ndarray:
    try:
        data, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        raise AudioError(tx("לא הצלחתי לפתוח את הקובץ.\nבחר קובץ שיר אחר (למשל קובץ שנגמר ב-mp3 או wav)."))
    data = to_mono_sr(data, sr)
    if len(data) < SR * 2:
        raise AudioError(tx("ההקלטה קצרה מדי.\nצריך לפחות שתי שניות של שירה."))
    if len(data) > SR * 60 * 15:
        raise AudioError(tx("הקובץ ארוך מדי.\nאפשר להכין שיר של עד 15 דקות."))
    if np.max(np.abs(data)) < 1e-4:
        raise AudioError(tx("בקובץ הזה אין קול - הוא שקט לגמרי.\nבדוק שהמיקרופון היה מחובר בזמן ההקלטה."))
    return data


def load_stereo(path: str) -> np.ndarray:
    """שיר מוכן (עם ליווי) בסטריאו - למחרוזת."""
    try:
        data, sr = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        raise AudioError(tx("לא הצלחתי לפתוח את הקובץ.\nבחר קובץ שיר אחר (למשל קובץ שנגמר ב-mp3 או wav)."))
    data = data[:, :2] if data.shape[1] > 1 else np.repeat(data, 2, axis=1)
    if sr != SR:
        g = gcd(sr, SR)
        data = resample_poly(data, SR // g, sr // g, axis=0).astype(np.float32)
    if len(data) < SR:
        raise AudioError(tx("הקובץ קצר מדי."))
    return np.ascontiguousarray(data, dtype=np.float32)


def save(path: str, data: np.ndarray, bitrate: int = 256, tags: dict = None) -> None:
    """tags: פרטי השיר (title, artist...) - נכתבים בתוך קובץ MP3."""
    data = np.clip(np.asarray(data, dtype=np.float32), -1.0, 1.0)
    try:
        if path.lower().endswith(".mp3"):
            import lameenc
            enc = lameenc.Encoder()
            enc.set_bit_rate(bitrate)
            enc.set_in_sample_rate(SR)
            ch = 1 if data.ndim == 1 else data.shape[1]
            enc.set_channels(ch)
            enc.set_quality(2)
            pcm = (data * 32767).astype("<i2").tobytes()   # שורות = דגימות, משולב ערוצים
            from ..tags import id3
            with open(path, "wb") as f:
                f.write(id3(tags) + enc.encode(pcm) + enc.flush())
        else:
            sf.write(path, data, SR, subtype="PCM_16")
    except PermissionError:
        raise AudioError(tx("אין אפשרות לשמור במקום הזה.\nבחר מקום אחר, למשל 'מסמכים'."))
    except OSError:
        raise AudioError(tx("השמירה לא הצליחה.\nייתכן שהדיסק מלא. בחר מקום אחר ונסה שוב."))
