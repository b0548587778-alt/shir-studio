"""בדיקה אם יש גרסה חדשה. רצה רק כשהמשתמש לוחץ על הכפתור - התוכנה עצמה עובדת בלי אינטרנט."""
import json
import re
import urllib.request

API = "https://api.github.com/repos/b0548587778-alt/shir-studio/releases/latest"
PAGE = "https://github.com/b0548587778-alt/shir-studio/releases/latest"


def parse(text):
    """'גרסה 1.0.57' -> (1, 0, 57). אין מספר גרסה -> None."""
    m = re.search(r"\d+(?:\.\d+)+", text or "")
    return tuple(int(x) for x in m.group(0).split(".")) if m else None


def newer(latest, current):
    a, b = parse(latest), parse(current)
    return bool(a and b and a > b)


def _fetch(timeout):
    req = urllib.request.Request(API, headers={"User-Agent": "ShirStudio",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def latest_version(fetch=None, timeout=8):
    """מספר הגרסה האחרונה שפורסמה ('1.0.57'), או None אם אי אפשר לדעת."""
    try:
        d = (fetch or _fetch)(timeout)
    except Exception:
        return None
    for field in ("name", "body", "tag_name"):
        v = parse(d.get(field) or "")
        if v:
            return ".".join(str(x) for x in v)
    return None
