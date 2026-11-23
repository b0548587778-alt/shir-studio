"""מחרוזת: כמה שירים מחוברים לקובץ אחד, עם מעבר חלק בין שיר לשיר."""
import dataclasses
import os

import numpy as np

from .audio.fileio import SR, AudioError


def _stereo(x):
    x = np.asarray(x, dtype=np.float32)
    return x if x.ndim == 2 else np.stack([x, x], axis=1)


def _trim(x, keep=0.25):
    """בלי השקט שבתחילת השיר ובסופו (נשאר רבע שנייה)."""
    env = np.max(np.abs(x), axis=1)
    loud = np.where(env > max(1e-4, 0.01 * float(env.max())))[0]
    if not len(loud):
        return x
    k = int(keep * SR)
    return x[max(0, loud[0] - k): loud[-1] + k]


def _rms(x):
    return float(np.sqrt(np.mean(x ** 2)) + 1e-12)


def join(songs, crossfade=2.0):
    """מחבר שירים (מונו או סטריאו) לאחד: עוצמה אחידה, ומעבר שבו שיר אחד דועך והבא נכנס."""
    songs = [_trim(_stereo(s)) for s in songs if s is not None and len(s)]
    if not songs:
        raise AudioError("לא נבחרו שירים למחרוזת.")
    target = float(np.median([_rms(s) for s in songs]))
    out = None
    for s in songs:
        s = s * np.float32(np.clip(target / _rms(s), 0.25, 4.0))        # כל השירים באותה עוצמה
        if out is None:
            out = s
            continue
        k = int(min(crossfade * SR, len(out) // 3, len(s) // 3))
        if k > 0:
            w = np.linspace(0, np.pi / 2, k, dtype=np.float32)[:, None]   # מעבר בעוצמה שווה
            mixed = out[-k:] * np.cos(w) + s[:k] * np.sin(w)
            out = np.concatenate([out[:-k], mixed, s[k:]])
        else:
            out = np.concatenate([out, s])
    peak = float(np.max(np.abs(out)))
    if peak > 0.89:
        out = out * np.float32(0.89 / peak)
    return out.astype(np.float32)


def make_medley(paths, out_path, style=None, settings=None, process=False, crossfade=2.0, progress=None):
    """paths: קבצי השירים לפי הסדר. process=True: הקבצים הם שירה בלי ליווי, ומכינים לכל אחד שיר מלא קודם.
    מחזיר (אורך בשניות, רשימת קבצים שלא נפתחו)."""
    from .audio.fileio import load, load_stereo, save
    from .pipeline import Song, Settings
    songs, bad = [], []
    n = len(paths)
    for i, p in enumerate(paths):
        def rep(pct, msg=None, i=i):
            if progress:
                progress(int(95 * (i + pct / 100) / n), f"שיר {i + 1} מתוך {n}: {os.path.basename(p)}")
        rep(0)
        try:
            if process:
                st = dataclasses.replace(settings or Settings(), key=None, chords_text="",
                                         sections=None, note_edits=None)
                songs.append(Song(load(p)).make(style, rep, st))
            else:
                songs.append(load_stereo(p))
        except MemoryError:
            raise
        except Exception:                               # שיר אחד שנכשל לא עוצר את המחרוזת
            bad.append(p)
    if not songs:
        raise AudioError("לא הצלחתי לפתוח אף אחד מהשירים.")
    if progress:
        progress(96, "מחבר את השירים...")
    out = join(songs, crossfade)
    save(out_path, out)
    if progress:
        progress(100, None)
    return len(out) / SR, bad
