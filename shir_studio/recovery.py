"""גיבוי אוטומטי: אם התוכנה או המחשב נסגרים באמצע - ההקלטה והעבודה לא הולכות לאיבוד."""
import json
import os

import numpy as np
import soundfile as sf

from .audio.fileio import SR
from .log import log_dir

REC, VOICE, META = "recording.wav", "voice.npy", "session.json"


def folder():
    d = os.path.join(log_dir(), "recovery")
    os.makedirs(d, exist_ok=True)
    return d


def _p(name):
    return os.path.join(folder(), name)


def _rm(*names):
    for n in names:
        try:
            os.remove(_p(n))
        except OSError:
            pass


class RecordingBackup:
    """כותב את ההקלטה לדיסק תוך כדי שירה (כל שנייה בערך)."""

    def __init__(self):
        self.f = None
        try:
            self.f = sf.SoundFile(_p(REC), "w", SR, 1, "PCM_16")
        except Exception:
            self.f = None

    def restart(self):
        self.close()
        self.__init__()

    def write(self, chunks):
        if self.f is None or not chunks:
            return
        try:
            self.f.write(np.concatenate(chunks))
            self.f.flush()
        except Exception:
            self.close()

    def close(self):
        if self.f is not None:
            try:
                self.f.close()
            except Exception:
                pass
            self.f = None

    def discard(self):
        self.close()
        _rm(REC)


def save_session(raw, meta, raw_changed=True):
    """שומר את העבודה הנוכחית (ההקלטה + ההגדרות). הקול נכתב רק כשהוא השתנה."""
    try:
        if raw_changed or not os.path.exists(_p(VOICE)):
            tmp = _p(VOICE) + ".tmp"
            with open(tmp, "wb") as f:
                np.save(f, np.asarray(raw, dtype=np.float32))
            os.replace(tmp, _p(VOICE))
        tmp = _p(META) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        os.replace(tmp, _p(META))
    except Exception:
        pass


def pending():
    """מה נשאר מהפעם הקודמת: ("recording", הקלטה) / ("session", הקלטה, מידע) / None."""
    try:
        rec = os.path.getmtime(_p(REC)) if os.path.exists(_p(REC)) else 0
        ses = os.path.getmtime(_p(META)) if os.path.exists(_p(META)) and os.path.exists(_p(VOICE)) else 0
        if rec and rec >= ses:
            data, sr = sf.read(_p(REC), dtype="float32")
            if sr == SR and len(data) >= 2 * SR and float(np.max(np.abs(data))) > 0.003:
                return ("recording", data)
        if ses:
            with open(_p(META), encoding="utf-8") as f:
                meta = json.load(f)
            raw = np.load(_p(VOICE))
            if len(raw) >= 2 * SR:
                return ("session", raw, meta)
    except Exception:
        pass
    return None


def clear():
    _rm(REC, VOICE, META, VOICE + ".tmp", META + ".tmp")
