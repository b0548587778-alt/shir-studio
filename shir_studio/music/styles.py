"""טעינת סגנונות הליווי מתיקיית styles (קובץ json לכל סגנון)."""
import json
import os
import sys


def styles_dir():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "shir_studio", "styles")
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "styles")


def load_styles():
    out = []
    d = styles_dir()
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                s = json.load(f)
            s["id"] = fn[:-5]
            out.append(s)
    return sorted(out, key=lambda s: s.get("order", 99))


# כלים שאפשר להחליף ביניהם (כלים מלודיים - לא תופים)
SWAPPABLE = {"piano": "פסנתר", "guitar": "גיטרה", "steel_guitar": "גיטרה מתכת", "accordion": "אקורדיון",
             "violin": "כינור", "clarinet": "קלרינט", "flute": "חליל", "trumpet": "חצוצרה",
             "brass": "כלי נשיפה", "strings": "כלי מיתר", "slow_strings": "מיתרים רכים",
             "organ": "עוגב", "choir": "מקהלה", "choir_oo": "מקהלה (אוּ)",
             "cello": "צ'לו", "bass": "בס", "acoustic_bass": "קונטרבס"}


def instruments_of(style):
    seen = []
    for tr in style.get("tracks", []) + style.get("free", []):
        i = tr["instrument"]
        if i in SWAPPABLE and i not in seen:
            seen.append(i)
    return seen


def apply_swaps(style, swaps):
    """מחזיר עותק של הסגנון עם כלים מוחלפים."""
    if not swaps:
        return style
    import copy
    s = copy.deepcopy(style)
    for tr in s.get("tracks", []) + s.get("free", []):
        tr["instrument"] = swaps.get(tr["instrument"], tr["instrument"])
    return s
