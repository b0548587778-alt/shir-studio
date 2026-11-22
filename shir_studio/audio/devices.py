"""הקלטה והשמעה דרך כרטיס הקול."""
import threading
import numpy as np
from .fileio import SR, AudioError


def _sd():
    try:
        import sounddevice as sd
        return sd
    except Exception:
        raise AudioError("לא הצלחתי לגשת לכרטיס הקול של המחשב.\nהפעל מחדש את המחשב ונסה שוב.")


class Recorder:
    def __init__(self):
        self._chunks = []
        self._stream = None
        self.level = 0.0

    def start(self):
        sd = _sd()
        try:
            sd.query_devices(kind="input")
        except Exception:
            raise AudioError("לא נמצא מיקרופון.\nחבר מיקרופון למחשב ונסה שוב.")

        def cb(indata, frames, t, status):
            mono = indata.mean(axis=1).copy()
            self._chunks.append(mono)
            self.level = float(np.sqrt(np.mean(mono ** 2)))

        try:
            self._stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=cb)
            self._stream.start()
        except Exception:
            raise AudioError("לא הצלחתי להפעיל את המיקרופון.\n"
                             "בדוק שהמיקרופון מחובר ושאף תוכנה אחרת לא משתמשת בו.\n"
                             "אם זה לא עוזר: פתח 'הגדרות' > 'פרטיות' > 'מיקרופון' ואפשר גישה.")

    def stop(self) -> np.ndarray:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks).astype(np.float32)


class Player:
    """השמעה עם מעקב אחרי המיקום בשיר."""

    def __init__(self):
        self.data = None
        self.t0 = None
        self.offset = 0.0

    def play(self, data: np.ndarray, start_sec: float = 0.0):
        import time
        sd = _sd()
        try:
            sd.stop()
            sd.play(data[int(start_sec * SR):], SR)
        except Exception:
            raise AudioError("לא הצלחתי להשמיע.\nבדוק שהרמקולים או האוזניות מחוברים.")
        self.data, self.offset, self.t0 = data, start_sec, time.time()

    def position(self):
        """שניות מתחילת השיר, או None אם לא מנגן."""
        import time
        if self.t0 is None or self.data is None:
            return None
        p = self.offset + time.time() - self.t0
        if p >= len(self.data) / SR:
            self.t0 = None
            return None
        return p

    def length(self):
        return 0 if self.data is None else len(self.data) / SR

    def stop(self):
        self.t0 = None
        try:
            _sd().stop()
        except AudioError:
            pass
