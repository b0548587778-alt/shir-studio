"""טעינת סגנונות הליווי מתיקיית styles (קובץ json לכל סגנון)."""
import json
import os
import sys

from ..i18n import tx


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
            s["name"], s["description"] = tx(s.get("name", "")), tx(s.get("description", ""))   # לפי שפת הממשק
            out.append(s)
    return sorted(out, key=lambda s: s.get("order", 99))


# כלים שאפשר להחליף ביניהם (כלים מלודיים - לא תופים)
SWAPPABLE = {"piano": tx("פסנתר"), "guitar": tx("גיטרה"), "steel_guitar": tx("גיטרה מתכת"), "accordion": tx("אקורדיון"),
             "violin": tx("כינור"), "clarinet": tx("קלרינט"), "flute": tx("חליל"), "trumpet": tx("חצוצרה"),
             "brass": tx("כלי נשיפה"), "strings": tx("כלי מיתר"), "slow_strings": tx("מיתרים רכים"),
             "organ": tx("עוגב"), "choir": tx("מקהלה"), "choir_oo": tx("מקהלה (אוּ)"),
             "cello": tx("צ'לו"), "harp": tx("נבל"), "oboe": tx("אבוב"), "bassoon": tx("בסון"), "horn": tx("קרן יער"),
             "marimba": tx("מרימבה"), "glockenspiel": tx("פעמוני זכוכית"), "bells": tx("פעמונים"), "bass": tx("בס"), "acoustic_bass": tx("קונטרבס")}


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
