import os
import datetime


def log_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "ShirStudio")
    os.makedirs(d, exist_ok=True)
    return d


def log_error(text):
    try:
        with open(os.path.join(log_dir(), "log.txt"), "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}]\n{text}\n")
    except OSError:
        pass
