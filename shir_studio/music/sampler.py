"""נגן דגימות: מנגן הקלטות אמיתיות של כלים מתוך החבילה (מקור: FluidR3_GM, רישיון MIT)."""
import json
import os
import sys
import numpy as np

from ..audio.fileio import SR

_pack = None
_meta = None


def _path():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "shir_studio", "samples", "pack.npz")
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples", "pack.npz")


class _Packs:
    """כמה קבצי npz (pack.npz, pack2.npz...) שמתנהגים כמו קובץ אחד."""

    def __init__(self, paths):
        self._files = [np.load(p) for p in paths]
        self._where = {k: f for f in self._files for k in f.files}

    def __getitem__(self, k):
        return self._where[k][k]


def available():
    global _pack, _meta
    if _pack is None:
        p = _path()
        if not os.path.exists(p):
            return False
        import glob
        parts = [p] + sorted(q for q in glob.glob(os.path.join(os.path.dirname(p), "pack*.npz")) if q != p)
        _pack = _Packs(parts)
        _meta = json.loads(bytes(_pack["_meta"]).decode())
    return True


def has(instrument):
    return available() and instrument in _meta


def _region(instrument, midi, vel=0.8):
    """בוחר דגימה לפי הצליל ולפי עוצמת הנגינה (בכלים שיש להם כמה שכבות עוצמה)."""
    available()
    regs = _meta[instrument]
    v = int(np.clip(vel, 0, 1) * 127)
    match = [r for r in regs if r["lo"] <= midi <= r["hi"]]
    if not match:
        d = min(min(abs(r["lo"] - midi), abs(r["hi"] - midi)) for r in regs)
        match = [r for r in regs if min(abs(r["lo"] - midi), abs(r["hi"] - midi)) == d]
    layered = [r for r in match if r.get("vlo", 0) <= v <= r.get("vhi", 127)]
    return (layered or match)[0]


def _play(r, ratio, n, key=None):
    data = _pack[key or r["key"]].astype(np.float32) / 32768.0
    pos = np.arange(n) * ratio
    if r["loop"]:
        ls, le = r["loop"]
        le = min(le, len(data) - 1)
        if le - ls > 8:
            over = pos >= le
            pos[over] = ls + np.mod(pos[over] - ls, le - ls)
    valid = pos < len(data) - 1
    i = pos.astype(np.int64)
    i = np.minimum(i, len(data) - 2)
    frac = pos - i
    out = data[i] * (1 - frac) + data[i + 1] * frac
    out[~valid] = 0
    return out


def note(instrument, midi, dur, vel, tuning=0.0, release_cap=1.2):
    r = _region(instrument, midi, vel)
    ratio = 2 ** ((midi - r["root"]) / 12 + (r["tune"] + tuning * 100) / 1200) * r["sr"] / SR
    rel = float(np.clip(r["release"], 0.06, release_cap))
    n = int((dur + rel) * SR)
    x = _play(r, ratio, n)
    if r.get("right"):                                    # דגימת סטריאו אמיתית
        x = np.stack([x, _play(r, ratio, n, r["right"])], axis=1)
    t = np.arange(n) / SR
    att = max(r["attack"], 0.002)
    dec = max(r["decay"], 0.01)
    db = np.where(t < att, 0.0, r["sustain_db"] * np.minimum(1.0, (t - att) / dec))
    db = np.maximum(db, -100)
    rel_db = np.where(t > dur, -60 * (t - dur) / rel, 0.0)
    env = 10 ** ((db + rel_db - r["att_db"]) / 20) * np.minimum(1.0, t / att)
    # בכלי עם שכבות עוצמה, הדגימה עצמה כבר רכה/חזקה - מקטינים את השינוי בעוצמה
    gain = (0.25 + 0.75 * vel) ** (0.7 if "vlo" in r else 1.3)
    g = env * gain
    return (x * (g[:, None] if x.ndim == 2 else g)).astype(np.float32)


KIT = {"kick", "snare", "hat", "open_hat", "ride", "crash", "tom_hi", "tom_low"}
_rr = {}


def drum(name, vel, variant=None):
    """מכת תוף. בערכה החדשה: דגימה לפי עוצמת המכה, ומתחלפת בין מכות (לא 'מכונה')."""
    if "kit" in _meta and name in KIT:
        v = int(np.clip(vel, 0, 1) * 127)
        cands = [r for r in _meta["kit"] if r["drum"] == name and r["vlo"] <= v <= r["vhi"]]
        if cands:
            if variant is None:
                variant = _rr.get(name, 0)
                _rr[name] = variant + 1
            r = cands[variant % len(cands)]
            x = _pack[r["key"]].astype(np.float32) / 32768.0
            if r["sr"] != SR:
                x = _play(r, r["sr"] / SR, int(len(x) * SR / r["sr"]))
            if r.get("right"):                               # תוף בסטריאו אמיתי
                xr = _pack[r["right"]].astype(np.float32) / 32768.0
                if r["sr"] != SR:
                    xr = _play(r, r["sr"] / SR, int(len(xr) * SR / r["sr"]), r["right"])
                k = min(len(x), len(xr))
                x = np.stack([x[:k], xr[:k]], axis=1)
            # השכבה כבר בעוצמה הנכונה; התאמה עדינה בתוך השכבה + איזון כללי
            return (x * (0.75 + 0.35 * vel) * 0.9).astype(np.float32)
    return _gm_drum(name, vel)


def _gm_drum(name, vel):
    key = _meta["_drum_keys"][name]
    r = _region("drums", key)
    ratio = 2 ** ((key - r["root"]) / 12 + r["tune"] / 1200) * r["sr"] / SR
    n = int(min(len(_pack[r["key"]]) / ratio, 3 * SR))
    x = _play(r, ratio, n)
    env = 10 ** (-r["att_db"] / 20)
    return (x * env * (0.3 + 0.7 * vel) ** 1.3).astype(np.float32)
