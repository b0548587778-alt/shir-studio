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


CLIP = 0.985              # מעל זה כרטיס הקול כבר 'חותך' את הצליל


def mic_verdict(peak, loud, floor):
    """בדיקת מיקרופון. peak: השיא שנמדד, loud: העוצמה בזמן השירה, floor: העוצמה כששקט (רעש הרקע).
    מחזיר (מצב, הסבר): silent / quiet / loud / noisy / good."""
    if loud < 0.0015:
        return "silent", "לא שומע אותך בכלל.\nבדוק שהמיקרופון מחובר, ושהוא לא מושתק."
    if peak >= CLIP:
        return "loud", "חזק מדי - הקול נחתך ויישמע צרוד.\nהתרחק מעט מהמיקרופון, או הנמך את עוצמת המיקרופון במחשב."
    if loud < 0.02:
        return "quiet", "חלש מדי.\nהתקרב למיקרופון (כ-15 ס\"מ), או הגבר את עוצמת המיקרופון במחשב."
    if floor > 0.012 and floor > loud * 0.25:
        return "noisy", "יש רעש רקע חזק (מאוורר, מזגן, רחוב).\nכדאי לסגור חלון או לכבות את מה שמרעיש, ולשיר קרוב יותר."
    return "good", "מצוין! העוצמה מתאימה, אפשר להקליט."


def clipped_share(data):
    """איזה חלק מההקלטה 'נחתך' (חזק מדי)."""
    data = np.asarray(data)
    return float(np.mean(np.abs(data) >= CLIP)) if len(data) else 0.0


class Recorder:
    def __init__(self):
        self._chunks = []
        self._stream = None
        self._drained = 0
        self.level = 0.0
        self.peak = 0.0               # השיא של החלק האחרון שהוקלט
        self.clips = 0                # כמה חלקים הגיעו לקצה (הקלטה חזקה מדי)

    def reset(self):
        """מתחילים את ההקלטה מחדש מהרגע הזה (אחרי הספירה לאחור)."""
        self._chunks = []
        self._drained = 0

    def drain(self):
        """החלקים שהוקלטו מאז הקריאה הקודמת - לגיבוי שוטף לדיסק."""
        chunks = self._chunks
        new = chunks[self._drained:len(chunks)]
        self._drained += len(new)
        return new

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
            self.peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
            if self.peak >= CLIP:
                self.clips += 1

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


class Overdub:
    """משמיע (ליווי, או את מה שלפני המשפט) ומקליט באותו זמן - שני הכיוונים מסונכרנים.
    ההקלטה שחוזרת מיושרת לתחילת ההשמעה."""

    def __init__(self, backing):
        b = np.asarray(backing, dtype=np.float32)
        self.backing = b if b.ndim == 2 else np.stack([b, b], axis=1)
        self._chunks = []
        self._stream = None
        self._pos = 0
        self._latency = 0.0
        self.level = 0.0
        self.peak = 0.0
        self.clips = 0

    def reset(self):
        pass                                   # כאן הכול נשמר - החיתוך נעשה לפי הזמן

    def drain(self):
        return []

    def position(self):
        return self._pos / SR

    def start(self):
        sd = _sd()
        b = self.backing

        def cb(indata, outdata, frames, t, status):
            k = max(0, min(frames, len(b) - self._pos))
            outdata[:k] = b[self._pos:self._pos + k]
            outdata[k:] = 0
            self._pos += frames
            mono = indata[:, 0].copy()
            self._chunks.append(mono)
            self.level = float(np.sqrt(np.mean(mono ** 2)))
            self.peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
            if self.peak >= CLIP:
                self.clips += 1

        try:
            self._stream = sd.Stream(samplerate=SR, channels=(1, 2), dtype="float32", callback=cb)
            lat = self._stream.latency
            self._latency = float(sum(lat)) if isinstance(lat, (tuple, list)) else float(lat)
            self._stream.start()
        except Exception:
            self._stream = None
            raise AudioError("לא הצלחתי להשמיע ולהקליט באותו זמן.\n"
                             "בדוק שהמיקרופון והאוזניות מחוברים, ונסה שוב.")

    def stop(self) -> np.ndarray:
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        rec = np.concatenate(self._chunks).astype(np.float32)
        # מה שנשמע באוזניות מגיע למיקרופון באיחור קטן (של כרטיס הקול) - מפצים עליו
        return rec[int(min(max(self._latency, 0.0), 0.5) * SR):]


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


def click_track(bpm, meter=4, seconds=60.0):
    """צלילי מטרונום: פעמה ראשונה בתיבה גבוהה יותר."""
    n = int(seconds * SR)
    out = np.zeros(n, dtype=np.float32)
    period = 60.0 / bpm
    L = int(0.03 * SR)
    t = np.arange(L) / SR
    env = np.exp(-t * 120)
    k = 0
    while True:
        i = int(k * period * SR)
        if i + L >= n:
            break
        f = 1600 if k % meter == 0 else 1000
        out[i:i + L] += (0.35 * np.sin(2 * np.pi * f * t) * env).astype(np.float32)
        k += 1
    return out


class Metronome:
    """מטרונום שמתנגן ברקע בזמן ההקלטה (מומלץ עם אוזניות, כדי שלא ייכנס להקלטה)."""

    def __init__(self):
        self._stream = None

    def start(self, bpm, meter=4):
        sd = _sd()
        period = 60.0 / bpm
        bar = click_track(bpm, meter, seconds=period * meter * 8)[: int(round(period * meter * 8 * SR))]
        pos = [0]

        def cb(outdata, frames, t, status):
            idx = (pos[0] + np.arange(frames)) % len(bar)
            outdata[:, 0] = bar[idx]
            pos[0] = (pos[0] + frames) % len(bar)

        try:
            self._stream = sd.OutputStream(samplerate=SR, channels=1, dtype="float32", callback=cb)
            self._stream.start()
        except Exception:
            self._stream = None
            raise AudioError("לא הצלחתי להפעיל את המטרונום.\nבדוק שהרמקולים או האוזניות מחוברים.")

    def stop(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
