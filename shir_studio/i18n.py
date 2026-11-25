"""שפות הממשק. הטקסטים בקוד כתובים בעברית; לכל שפה יש קובץ בתיקייה lang (למשל en.json) שממפה כל
משפט בעברית לתרגום שלו. כדי להוסיף שפה: מעתיקים את he.json לשם חדש (למשל fr.json), מתרגמים את הערכים
(הצד הימני של כל שורה), ומוסיפים את השפה לרשימה LANGS כאן.

השפה נטענת פעם אחת, כשהתוכנה נפתחת - לכן שינוי שפה נכנס לתוקף בהפעלה הבאה."""
import json
import os
import sys

LANGS = {"he": "עברית", "yi": "ייִדיש", "en": "English"}       # קוד השפה -> שם השפה בשפה עצמה
RTL = {"he", "yi"}                                              # שפות שנכתבות מימין לשמאל

_lang = "he"
_table = {}


def _dir():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "shir_studio", "lang")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")


def _prefs_file():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ShirStudio", "prefs.json")


def saved_language():
    """השפה שהמשתמש בחר (None = עוד לא בחר, זו ההפעלה הראשונה)."""
    try:
        with open(_prefs_file(), encoding="utf-8") as f:
            code = json.load(f).get("language")
        return code if code in LANGS else None
    except (OSError, ValueError, AttributeError):
        return None


def save_language(code):
    p = _prefs_file()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                d = {}
        except (OSError, ValueError):
            d = {}
        d["language"] = code
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        return True
    except OSError:
        return False


def set_language(code):
    """טוען את קובץ השפה. עברית היא שפת המקור - אין מה לתרגם."""
    global _lang, _table
    _lang = code if code in LANGS else "he"
    _table = {}
    if _lang != "he":
        try:
            with open(os.path.join(_dir(), _lang + ".json"), encoding="utf-8") as f:
                _table = {k: v for k, v in json.load(f).items() if isinstance(v, str) and v}
        except (OSError, ValueError):
            _table = {}
    return _lang


def language():
    return _lang


def is_rtl():
    return _lang in RTL


def direction():
    """כיוון המסך לשפה הנוכחית (לשימוש ב-setLayoutDirection)."""
    from PySide6.QtCore import Qt
    return Qt.RightToLeft if is_rtl() else Qt.LeftToRight


def tx(text):
    """התרגום של משפט לשפה הנוכחית. משפט שאין לו תרגום נשאר בעברית."""
    return _table.get(text, text)


set_language(saved_language() or "he")
