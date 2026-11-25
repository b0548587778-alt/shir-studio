"""שמירת פרויקט (קובץ .shir) ועיבוד כמה שירים ברצף."""
from .i18n import tx
import dataclasses
import io
import json
import os
import zipfile

import numpy as np

from .pipeline import Settings, Song

EXT = ".shir"
VERSION = 1


def settings_to_dict(st: Settings):
    d = dataclasses.asdict(st)
    d["key"] = list(st.key) if st.key else None
    return d


def settings_from_dict(d):
    names = {f.name for f in dataclasses.fields(Settings)}
    d = {k: v for k, v in (d or {}).items() if k in names}
    if d.get("key"):
        d["key"] = (int(d["key"][0]), str(d["key"][1]))
    if d.get("note_edits"):
        d["note_edits"] = {str(k): v for k, v in d["note_edits"].items()}
    return Settings(**d)


def save_project(path, raw, settings, style_id=None, extra=None):
    """שומר את ההקלטה המקורית + כל ההגדרות, כדי לחזור לשיר בהמשך."""
    buf = io.BytesIO()
    np.save(buf, np.asarray(raw, dtype=np.float32))
    meta = {"version": VERSION, "settings": settings_to_dict(settings), "style": style_id}
    meta.update(extra or {})
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(meta, ensure_ascii=False, indent=1))
        z.writestr("voice.npy", buf.getvalue())
    os.replace(tmp, path)


def load_project(path):
    """מחזיר (raw, settings, style_id, meta)."""
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("project.json").decode("utf-8"))
        raw = np.load(io.BytesIO(z.read("voice.npy")))
    return raw, settings_from_dict(meta.get("settings")), meta.get("style"), meta


class History:
    """ביטול/חזרה (Undo/Redo) של הגדרות וסגנון."""

    def __init__(self, limit=50):
        self.undo_stack, self.redo_stack, self.limit = [], [], limit

    def push(self, state):
        state = _freeze(state)
        if self.undo_stack and self.undo_stack[-1] == state:
            return
        self.undo_stack.append(state)
        del self.undo_stack[:-self.limit]
        self.redo_stack.clear()

    def can_undo(self):
        return len(self.undo_stack) > 1

    def can_redo(self):
        return bool(self.redo_stack)

    def undo(self):
        if not self.can_undo():
            return None
        self.redo_stack.append(self.undo_stack.pop())
        return json.loads(self.undo_stack[-1])

    def redo(self):
        if not self.redo_stack:
            return None
        s = self.redo_stack.pop()
        self.undo_stack.append(s)
        return json.loads(s)


def _freeze(state):
    return json.dumps(state, ensure_ascii=False, sort_keys=True)


def batch(paths, style, settings, out_folder, fmt="mp3", progress=None, load=None, save=None, artist=""):
    """מעבד כמה קבצים ברצף. מחזיר רשימת (קובץ, תוצאה או None, שגיאה)."""
    from .audio.fileio import load as _load, save as _save
    tagged = save is None                    # השמירה הרגילה כותבת את שם השיר והזמר בתוך הקובץ
    load, save = load or _load, save or _save
    results = []
    n = len(paths)
    for i, p in enumerate(paths):
        def rep(pct, msg=None, i=i):
            if progress:
                progress(int(100 * (i + pct / 100) / n),
                         tx("שיר {0} מתוך {1}: {2}").format(i + 1, n, os.path.basename(p)))
        try:
            song = Song(load(p))
            out = song.make(style, rep, dataclasses.replace(settings, key=None, chords_text=""))
            base = os.path.splitext(os.path.basename(p))[0]
            dst = os.path.join(out_folder, "{0} - {1}.{2}".format(base, style.get("name") or tx("שיר"), fmt))
            if tagged:
                save(dst, out, tags={"title": base, "artist": artist})
            else:
                save(dst, out)
            results.append((p, dst, None))
        except Exception as e:                       # שיר אחד שנכשל לא עוצר את כל השאר
            results.append((p, None, str(e) or type(e).__name__))
    if progress:
        progress(100, None)
    return results
