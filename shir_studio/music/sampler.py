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


def available():
    global _pack, _meta
    if _pack is None:
        p = _path()
        if not os.path.exists(p):
            return False
        _pack = np.load(p)
        _meta = json.loads(bytes(_pack["_meta"]).decode())
    return True


def has(instrument):
    return available() and instrument in _meta


def _region(instrument, midi):
    regs = _meta[instrument]
    for r in regs:
        if r["lo"] <= midi <= r["hi"]:
            return r
    return min(regs, key=lambda r: min(abs(r["lo"] - midi), abs(r["hi"] - midi)))


def _play(r, ratio, n):
    data = _pack[r["key"]].astype(np.float32) / 32768.0
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
    r = _region(instrument, midi)
    ratio = 2 ** ((midi - r["root"]) / 12 + (r["tune"] + tuning * 100) / 1200) * r["sr"] / SR
    rel = float(np.clip(r["release"], 0.06, release_cap))
    n = int((dur + rel) * SR)
    x = _play(r, ratio, n)
    t = np.arange(n) / SR
    att = max(r["attack"], 0.002)
    dec = max(r["decay"], 0.01)
    db = np.where(t < att, 0.0, r["sustain_db"] * np.minimum(1.0, (t - att) / dec))
    db = np.maximum(db, -100)
    rel_db = np.where(t > dur, -60 * (t - dur) / rel, 0.0)
    env = 10 ** ((db + rel_db - r["att_db"]) / 20) * np.minimum(1.0, t / att)
    gain = (0.25 + 0.75 * vel) ** 1.3
    return (x * env * gain).astype(np.float32)


def drum(name, vel):
    key = _meta["_drum_keys"][name]
    r = _region("drums", key)
    ratio = 2 ** ((key - r["root"]) / 12 + r["tune"] / 1200) * r["sr"] / SR
    n = int(min(len(_pack[r["key"]]) / ratio, 3 * SR))
    x = _play(r, ratio, n)
    env = 10 ** (-r["att_db"] / 20)
    return (x * env * (0.3 + 0.7 * vel) ** 1.3).astype(np.float32)
