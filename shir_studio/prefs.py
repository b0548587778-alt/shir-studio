"""ההעדפות האישיות של המשתמש ('הטעם שלי') - נשמרות בין הפעלה להפעלה."""
import dataclasses
import json
import os

from .log import log_dir
from .pipeline import Settings

# מה שנשמר כטעם אישי. סולם, אקורדים וקצב שייכים לשיר מסוים - ולא נשמרים.
PERSONAL = ("denoise", "tune", "voice_db", "accomp_db", "reverb", "harmony", "choir", "swaps", "modulate",
            "voice_tone", "space", "loudness", "intro", "ending")


def _path():
    return os.path.join(log_dir(), "prefs.json")


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(prefs):
    try:
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path())
        return True
    except OSError:
        return False


def personal_settings(prefs):
    """הגדרות לשיר חדש: ברירות המחדל של התוכנה + מה שהמשתמש שמר כטעם שלו."""
    names = {f.name for f in dataclasses.fields(Settings)}
    d = {k: v for k, v in (prefs.get("defaults") or {}).items() if k in PERSONAL and k in names}
    try:
        return Settings(**d)
    except TypeError:
        return Settings()


def store_personal(prefs, settings, style_id=None, fmt="mp3", extras=False):
    prefs = dict(prefs)
    prefs["defaults"] = {k: getattr(settings, k) for k in PERSONAL}
    prefs.update(style=style_id, fmt=fmt, extras=bool(extras))
    save(prefs)
    return prefs
