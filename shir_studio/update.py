"""בדיקה אם יש גרסה חדשה, והורדה והתקנה שלה מתוך התוכנה.
הכול רץ רק כשהמשתמש לוחץ על הכפתור - התוכנה עצמה עובדת בלי אינטרנט."""
from .i18n import tx
import hashlib
import os
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


ASSET = "ShirStudio-Setup.exe"
TRUSTED = "https://github.com/b0548587778-alt/shir-studio/releases/download/"


from .audio.fileio import AudioError


class UpdateError(AudioError):
    """העדכון לא הצליח - עם הודעה בעברית למשתמש."""


def release_info(fetch=None, timeout=8):
    """פרטי קובץ ההתקנה של הגרסה האחרונה: {version, url, size, sha256}, או None אם אין."""
    try:
        d = (fetch or _fetch)(timeout)
    except Exception:
        return None
    version = None
    for field in ("name", "body", "tag_name"):
        v = parse(d.get(field) or "")
        if v:
            version = ".".join(str(x) for x in v)
            break
    for asset in d.get("assets") or []:
        url = asset.get("browser_download_url") or ""
        digest = asset.get("digest") or ""
        if asset.get("name") == ASSET and url.startswith(TRUSTED) and digest.startswith("sha256:"):
            return {"version": version, "url": url, "size": int(asset.get("size") or 0),
                    "sha256": digest.split(":", 1)[1].lower()}
    return None


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "ShirStudio"})
    return urllib.request.urlopen(req, timeout=timeout)


def download(info, folder, progress=None, opener=None, timeout=30):
    """מוריד את קובץ ההתקנה ובודק שהוא שלם ומקורי (גודל וטביעת SHA-256 כפי שפורסמו). מחזיר את הנתיב."""
    if not info or not str(info.get("url", "")).startswith(TRUSTED) or not info.get("sha256"):
        raise UpdateError(tx("לא מצאתי קובץ התקנה לגרסה החדשה."))
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, ASSET)
    tmp = dst + ".part"
    h = hashlib.sha256()
    done, size = 0, int(info.get("size") or 0)
    try:
        with (opener or _open)(info["url"], timeout) as r, open(tmp, "wb") as f:
            while True:
                block = r.read(1 << 20)
                if not block:
                    break
                f.write(block)
                h.update(block)
                done += len(block)
                if progress and size:
                    progress(min(99, int(100 * done / size)))
    except UpdateError:
        raise
    except Exception:
        _remove(tmp)
        raise UpdateError(tx("ההורדה נקטעה.\nבדוק את החיבור לאינטרנט ונסה שוב."))
    if (size and done != size) or h.hexdigest() != info["sha256"]:
        _remove(tmp)
        raise UpdateError(tx("הקובץ שירד אינו תקין, ולכן לא הותקן.\nנסה שוב מאוחר יותר."))
    os.replace(tmp, dst)
    if progress:
        progress(100)
    return dst


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def can_install():
    """התקנה מתוך התוכנה - רק בווינדוס, ורק בתוכנה המותקנת (לא בהרצה מקוד המקור)."""
    import sys
    return os.name == "nt" and bool(getattr(sys, "frozen", False))


def install(path, launch=None):
    """מפעיל את קובץ ההתקנה בלי שאלות; בסיום ההתקנה התוכנה נפתחת מחדש."""
    import subprocess
    (launch or subprocess.Popen)([path, "/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS"])
