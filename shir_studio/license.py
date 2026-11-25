"""גרסת ניסיון וקוד רישיון. הכול נבדק על המחשב עצמו, בלי אינטרנט.

קוד רישיון = שם הלקוח + תאריך + חתימה דיגיטלית (Ed25519). התוכנה מכילה רק את המפתח הציבורי ולכן יכולה
לבדוק קוד אבל לא ליצור אחד. שם הלקוח מוצג בתוכנה ("רשום על שם...") - כך מי שמעביר את הקוד לאחרים חשוף."""
from .i18n import tx
import base64
import datetime
import hashlib
import json
import os

from . import ed25519
from .license_key import PUBLIC_KEY_HEX
from .log import log_dir

TRIAL_SONGS = 10                 # כמה שירים אפשר לשמור בגרסת הניסיון
PREFIX = "SHIR"
EPOCH = datetime.date(2025, 1, 1)
_SALT = b"shir-studio-trial-v1"


class LicenseError(Exception):
    pass


# ---------- קוד הרישיון ----------
def make_code(secret: bytes, name: str, day: datetime.date = None) -> str:
    """יוצר קוד רישיון (רק בעל המפתח הסודי יכול). name: שם הלקוח, עד 30 תווים."""
    raw_name = name.strip().encode("utf-8")
    if not raw_name or len(raw_name) > 60:
        raise LicenseError(tx("שם הלקוח ריק או ארוך מדי"))
    days = ((day or datetime.date.today()) - EPOCH).days
    payload = b"\x01" + days.to_bytes(2, "big") + raw_name
    blob = payload + ed25519.sign(secret, payload)
    text = base64.b32encode(blob).decode().rstrip("=")
    return PREFIX + "-" + "-".join(text[i:i + 5] for i in range(0, len(text), 5))


def read_code(code: str, public_hex: str = None):
    """בודק קוד רישיון. מחזיר {"name": שם הלקוח, "date": תאריך} או זורק LicenseError עם הסבר פשוט."""
    public_hex = PUBLIC_KEY_HEX if public_hex is None else public_hex
    if not public_hex:
        raise LicenseError(tx("הגרסה הזו עדיין לא מוכנה לקבל קודי רישיון."))
    text = "".join(ch for ch in str(code).upper() if ch.isalnum())
    # טעויות הקלדה נפוצות: בקוד אין הספרות 0, 1, 8, 9 - הן הוקלדו במקום האותיות O, I, B
    if text.startswith(PREFIX):
        text = text[len(PREFIX):]
    text = text.replace("0", "O").replace("1", "I").replace("8", "B")
    try:
        blob = base64.b32decode(text + "=" * (-len(text) % 8))
    except Exception:
        raise LicenseError(tx("הקוד לא שלם או שיש בו טעות הקלדה.\nבדוק שהעתקת את כל הקוד, מההתחלה ועד הסוף."))
    if len(blob) < 3 + 1 + 64 or blob[0] != 1:
        raise LicenseError(tx("הקוד לא שלם או שיש בו טעות הקלדה.\nבדוק שהעתקת את כל הקוד, מההתחלה ועד הסוף."))
    payload, sig = blob[:-64], blob[-64:]
    if not ed25519.verify(bytes.fromhex(public_hex), payload, sig):
        raise LicenseError(tx("הקוד אינו נכון.\nבדוק שהעתקת אותו בדיוק כמו שקיבלת."))
    day = EPOCH + datetime.timedelta(days=int.from_bytes(payload[1:3], "big"))
    return {"name": payload[3:].decode("utf-8", "replace"), "date": day.isoformat()}


# ---------- מה שנשמר במחשב ----------
def _paths():
    """שני מקומות: מי שמוחק אחד מהם לא מאפס את גרסת הניסיון."""
    home = os.path.expanduser("~")
    return [os.path.join(log_dir(), "license.json"), os.path.join(home, ".shirstudio")]


def _seal(d):
    body = json.dumps(d, ensure_ascii=False, sort_keys=True)
    return {"d": d, "s": hashlib.sha256(_SALT + body.encode("utf-8")).hexdigest()[:16]}


def _load_all():
    out = []
    for p in _paths():
        try:
            with open(p, encoding="utf-8") as f:
                j = json.load(f)
            if isinstance(j, dict) and j == _seal(j.get("d")):
                out.append(j["d"])
        except (OSError, ValueError, TypeError):
            pass
    return out


def _store(d):
    for p in _paths():
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(_seal(d), f, ensure_ascii=False)
        except OSError:
            pass


def _state():
    found = _load_all()
    used = max([int(d.get("used", 0)) for d in found] + [0])
    code = next((d.get("code") for d in found if d.get("code")), None)
    return {"used": used, "code": code}


def status():
    """מצב הרישיון: {"licensed": bool, "name": שם או None, "used": שירים שנשמרו, "left": כמה נשארו בניסיון}."""
    st = _state()
    name = None
    if st["code"]:
        try:
            name = read_code(st["code"])["name"]
        except LicenseError:
            name = None
    left = max(0, TRIAL_SONGS - st["used"])
    return {"licensed": name is not None, "name": name, "used": st["used"], "left": left}


def can_save():
    s = status()
    return s["licensed"] or s["left"] > 0


def count_song(n=1):
    """נקרא כשנשמר שיר מוכן. ברישיון מלא לא סופרים."""
    st = _state()
    if status()["licensed"]:
        return
    st["used"] += int(n)
    _store(st)


def activate(code):
    """מזין קוד רישיון. מחזיר את שם הלקוח, או זורק LicenseError."""
    info = read_code(code)
    st = _state()
    st["code"] = str(code).strip()
    _store(st)
    return info["name"]
