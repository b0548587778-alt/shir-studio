"""גרסת ניסיון ורישיון. הכול נבדק על המחשב עצמו, בלי אינטרנט.

הרישיונות הם הרישיונות של SuperSuite (docs/LICENSING-DESIGN.md שם): בעל התוכנה מנהל את כל התוכנות שלו
ממסך "רישוי ומערכות" אחד. הסדר:
  1. שיר סטודיו יוצר 'בקשת רישיון' - קובץ קטן עם המפתח הציבורי של ההתקנה הזו (המפתח הפרטי לא יוצא מהמחשב).
  2. בעל התוכנה פותח את הבקשה ב-SuperSuite, מסמן את התחום 'שיר סטודיו' ותקופה, ומנפיק קובץ רישיון.
  3. שיר סטודיו טוען את קובץ הרישיון ובודק: חתום במפתח השורש, שייך להתקנה הזו, כולל את התחום, ובתוקף.
הרישיון נעול למחשב (למפתח של ההתקנה), ויש לו תאריך סיום - כלומר מנוי."""
from .i18n import tx
import base64
import hashlib
import json
import os
import time

from . import ed25519
from .license_key import ROOT_KEYS, FEATURE
from .log import log_dir

TRIAL_SONGS = 10                 # כמה שירים אפשר לשמור בגרסת הניסיון
PKG_REQUEST = "supersuite-license-request"
PKG_LICENSE = "supersuite-license"
DAY_MS = 24 * 60 * 60 * 1000
_SALT = b"shir-studio-trial-v1"


class LicenseError(Exception):
    pass


# ---------- אותו קידוד כמו ב-SuperSuite (shell/licensing/license.js) ----------
def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def canonical(value) -> str:
    """JSON קנוני: מפתחות ממוינים, בלי רווחים - אותם בתים בדיוק כמו ב-JavaScript, כדי שהחתימה תתאים."""
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + canonical(value[k])
                              for k in sorted(value)) + "}"
    if isinstance(value, list):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    if isinstance(value, float):
        if value != int(value):
            raise LicenseError(tx("מספר לא תקין ברישיון"))
        value = int(value)
    return json.dumps(value, ensure_ascii=False)


def key_id(public: bytes) -> str:
    return b64u(hashlib.sha256(public).digest()[:16])


def _jwk(public: bytes):
    return {"kty": "OKP", "crv": "Ed25519", "x": b64u(public)}


def sign_object(obj, seed: bytes) -> str:
    return b64u(ed25519.sign(seed, canonical(obj).encode("utf-8")))


def verify_object(obj, sig: str, public: bytes) -> bool:
    try:
        raw = b64u_decode(sig)
    except Exception:
        return False
    return len(raw) == 64 and ed25519.verify(public, canonical(obj).encode("utf-8"), raw)


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
    return {"used": max([int(d.get("used", 0)) for d in found] + [0]),
            "seed": next((d.get("seed") for d in found if d.get("seed")), None),
            "license": next((d.get("license") for d in found if d.get("license")), None),
            "seen": max([int(d.get("seen", 0)) for d in found] + [0])}


def _now_ms(st=None):
    """הזמן לבדיקת התוקף: המאוחר מבין שעון המחשב לזמן המאוחר ביותר שכבר נראה - הגנה מהחזרת השעון אחורה."""
    now = int(time.time() * 1000)
    return max(now, int((st or {}).get("seen", 0)))


def _node_seed(create=False):
    st = _state()
    if st["seed"]:
        return bytes.fromhex(st["seed"])
    if not create:
        return None
    seed = os.urandom(32)
    st["seed"] = seed.hex()
    _store(st)
    return seed


# ---------- בקשת רישיון ----------
def request(name: str) -> str:
    """בקשת רישיון לשליחה לבעל התוכנה (טקסט JSON, באותו מבנה שמסך הרישוי של SuperSuite פותח)."""
    name = "".join(ch for ch in str(name or "") if ch >= " " and ch != "\x7f").strip()[:80]
    if not name:
        raise LicenseError(tx("כתוב את השם שלך, כדי שהרישיון יירשם על שמך."))
    pub = ed25519.public_key(_node_seed(create=True))
    return json.dumps({"type": PKG_REQUEST, "v": 1, "name": name, "publicKey": _jwk(pub), "keyId": key_id(pub),
                       "product": FEATURE}, ensure_ascii=False)


# ---------- בדיקת רישיון ----------
def read_license(text, node_public: bytes = None, root_keys=None):
    """בודק קובץ רישיון של SuperSuite. מחזיר את תוכן הרישיון (payload) או זורק LicenseError עם הסבר פשוט."""
    root_keys = ROOT_KEYS if root_keys is None else root_keys
    if not root_keys:
        raise LicenseError(tx("הגרסה הזו עדיין לא מוכנה לקבל רישיונות."))
    bad = LicenseError(tx("זה לא קובץ רישיון תקין.\nבדוק שבחרת את הקובץ שקיבלת, או שהעתקת את כל הקוד."))
    try:
        pkg = json.loads(text) if isinstance(text, str) else text
    except ValueError:
        raise bad
    if not isinstance(pkg, dict) or pkg.get("type") != PKG_LICENSE or not isinstance(pkg.get("chain"), list) \
            or not pkg["chain"]:
        raise bad
    if len(pkg["chain"]) != 1:
        raise LicenseError(tx("הרישיון הזה שייך למערכת בת של SuperSuite, ולא לשיר סטודיו."))
    lic = pkg["chain"][0]
    p = lic.get("payload") if isinstance(lic, dict) else None
    try:
        ok_shape = (isinstance(p, dict) and p.get("v") == 1 and p.get("depth") == 1 and p.get("parentId") is None
                    and isinstance(p.get("features"), list) and isinstance(p["publicKey"]["x"], str)
                    and all(isinstance(p.get(k), int) and not isinstance(p.get(k), bool)
                            for k in ("issuedAt", "expiresAt", "graceDays", "slot"))
                    and p["expiresAt"] > p["issuedAt"] and 0 <= p["graceDays"] <= 90
                    and p.get("id") == key_id(b64u_decode(p["publicKey"]["x"])))
    except Exception:
        ok_shape = False
    if not ok_shape:
        raise bad
    roots = []
    for k in root_keys:
        try:
            roots.append(b64u_decode(k))
        except Exception:
            pass
    if not any(verify_object(p, lic.get("sig", ""), r) for r in roots):
        raise LicenseError(tx("הרישיון אינו חתום על ידי בעל התוכנה.\nבדוק שקיבלת אותו ממקור מוסמך."))
    if node_public is None:
        seed = _node_seed()
        node_public = ed25519.public_key(seed) if seed else None
    if node_public is None or p["publicKey"]["x"] != b64u(node_public):
        raise LicenseError(tx("הרישיון הזה הונפק למחשב אחר.\nצור בקשת רישיון מהמחשב הזה ושלח אותה לבעל התוכנה."))
    if FEATURE not in p["features"]:
        raise LicenseError(tx("הרישיון הזה אינו כולל את שיר סטודיו.\nפנה לבעל התוכנה כדי להוסיף אותו."))
    return p


def validity(payload, now_ms):
    """active / grace / expired / not-yet-valid - כמו ב-SuperSuite."""
    if now_ms < payload["issuedAt"] - DAY_MS:           # יום של מרווח: שעונים של שני מחשבים אינם זהים
        return "not-yet-valid"
    if now_ms <= payload["expiresAt"]:
        return "active"
    if now_ms <= payload["expiresAt"] + payload["graceDays"] * DAY_MS:
        return "grace"
    return "expired"


def status():
    """מצב הרישיון: licensed, name, until (אלפיות שנייה), state, used, left (שירים שנשארו בניסיון)."""
    st = _state()
    now = _now_ms(st)
    if now > st["seen"] + 60 * 60 * 1000:               # מעדכנים את 'הזמן המאוחר שנראה' פעם בשעה
        st["seen"] = now
        _store(st)
    name = until = None
    state = "trial"
    if st["license"]:
        try:
            p = read_license(st["license"])
            state = validity(p, now)
            name, until = p.get("name"), p["expiresAt"]
        except LicenseError:
            state = "trial"
    licensed = state in ("active", "grace")
    left = max(0, TRIAL_SONGS - st["used"])
    return {"licensed": licensed, "name": name, "until": until, "state": state, "used": st["used"], "left": left}


def can_save():
    s = status()
    return s["licensed"] or s["left"] > 0


def count_song(n=1):
    """נקרא כשנשמר שיר מוכן. ברישיון בתוקף לא סופרים."""
    if status()["licensed"]:
        return
    st = _state()
    st["used"] += int(n)
    _store(st)


def activate(text):
    """טוען רישיון. מחזיר את תוכן הרישיון, או זורק LicenseError."""
    p = read_license(text)
    st = _state()
    state = validity(p, _now_ms(st))
    if state == "expired":
        raise LicenseError(tx("תוקף הרישיון הזה כבר הסתיים.\nפנה לבעל התוכנה כדי לחדש אותו."))
    if state == "not-yet-valid":
        raise LicenseError(tx("הרישיון עדיין לא נכנס לתוקף.\nבדוק שהתאריך במחשב נכון."))
    st["license"] = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    st["seen"] = max(st["seen"], p["issuedAt"])
    _store(st)
    return p
