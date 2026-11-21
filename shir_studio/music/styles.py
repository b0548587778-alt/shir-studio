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
