"""בדיקה אם יש גרסה חדשה של התוכנה. רצה רק כשהמשתמש לוחץ על הכפתור - התוכנה עצמה עובדת בלי אינטרנט.
הבדיקה רק קוראת את מספר הגרסה האחרונה; שום מידע על המשתמש או על השירים לא נשלח."""
import json
import re

from . import APP_VERSION

LATEST = "https://api.github.com/repos/b0548587778-alt/shir-studio/releases/latest"
PAGE = "https://github.com/b0548587778-alt/shir-studio/releases/latest"


def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def _fetch(url, timeout):
    from urllib.request import Request, urlopen
    req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ShirStudio"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def check(current=APP_VERSION, timeout=8, fetch=None):
    """מחזיר (מצב, גרסה, קישור): 'newer' = יש גרסה חדשה, 'latest' = הגרסה מעודכנת, 'error' = לא הצלחתי לבדוק."""
    try:
        data = json.loads((fetch or _fetch)(LATEST, timeout))
        latest = parse_version(data.get("name")) or parse_version(data.get("tag_name"))
    except Exception:
        return "error", None, PAGE
    mine = parse_version(current)
    if latest is None or mine is None:
        return "error", None, PAGE
    text = ".".join(str(x) for x in latest)
    return ("newer" if latest > mine else "latest"), text, PAGE
