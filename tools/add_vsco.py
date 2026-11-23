"""כלי פיתוח: מוסיף לחבילת הצלילים כלי מיתר ונשיפה אמיתיים מ-VS Chamber Orchestra Community Edition
(רישיון CC0 - נחלת הכלל, מותר למכירה). https://github.com/sgossner/VSCO-2-CE (ענף SFZ)

שימוש:
    git clone --filter=blob:none -b SFZ https://github.com/sgossner/VSCO-2-CE vsco
    python tools/add_vsco.py vsco
"""
import io
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import soundfile as sf
from scipy.signal import resample_poly

PACK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shir_studio", "samples", "pack.npz")
SR = 44100

# שם בתוכנה: (קובץ sfz, מקסימום שניות, כמה שכבות עוצמה לשמור, attack, release)
INSTRUMENTS = {
    "violin": ("SViolinVib.sfz", 3.5, 2, 0.04, 0.5),
    "strings": ("ViolinEnsSusVib.sfz", 4.0, 2, 0.08, 0.7),
    "slow_strings": ("ViolinEnsSusVib.sfz", 4.0, 1, 0.35, 1.0),
    "cello": ("CelloEnsSusVib.sfz", 4.0, 1, 0.08, 0.7),
    "trumpet": ("TrumpetSusVib.sfz", 3.0, 2, 0.02, 0.35),
    "brass": ("TromboneSus.sfz", 3.0, 2, 0.02, 0.35),
    "flute": ("FluteSusVib.sfz", 3.5, 1, 0.04, 0.4),
    "acoustic_bass": ("ContrabassPizz.sfz", 2.0, 2, 0.002, 0.25),
    "harp": ("Harp.sfz", 3.0, 1, 0.002, 1.2),
    "oboe": ("OboeSusVib.sfz", 3.0, 1, 0.03, 0.35),
    "bassoon": ("BassoonSus.sfz", 3.0, 1, 0.03, 0.35),
    "horn": ("FHornSus.sfz", 3.5, 2, 0.04, 0.5),
    "marimba": ("Marimba.sfz", 2.0, 1, 0.002, 0.6),
    "glockenspiel": ("Glockenspiel.sfz", 2.5, 1, 0.002, 1.5),
    "bells": ("TubularBells.sfz", 4.0, 1, 0.002, 2.0),
}
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _num(v):
    """מספר מקש: '57' או 'a3' / 'c#4'."""
    v = v.strip()
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    m = re.fullmatch(r"([a-gA-G])([#b]?)(-?\d)", v)
    n = NOTE[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return 12 * (int(m.group(3)) + 1) + n


def parse_sfz(text):
    """רשימת אזורים (dict) עם ירושה מ-global/group/control."""
    text = re.sub(r"//[^\n]*", "", text)
    ctx = {"control": {}, "global": {}, "group": {}}
    regions, cur, kind = [], None, None
    for tok in re.split(r"(<\w+>)", text):
        m = re.fullmatch(r"<(\w+)>", tok)
        if m:
            kind = m.group(1)
            if kind == "group":
                ctx["group"] = {}
            if kind == "region":
                cur = {}
                regions.append(cur)
            continue
        # מפתח=ערך (ערכים של sample יכולים להכיל רווחים - עד המפתח הבא)
        for k, v in re.findall(r"(\w+)=(.*?)(?=\s+\w+=|$)", tok.strip(), flags=re.S):
            v = v.strip()
            if kind == "region":
                cur[k] = v
            elif kind in ctx:
                ctx[kind][k] = v
        if kind == "region" and cur is not None:
            for level in ("control", "global", "group"):
                for k, v in ctx[level].items():
                    cur.setdefault(k, v)
    return regions


def _read_wav(repo, path):
    data = subprocess.run(["git", "-C", repo, "show", f"HEAD:{path}"], capture_output=True, check=True).stdout
    x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != SR:
        g = np.gcd(sr, SR)
        x = resample_poly(x, SR // g, sr // g).astype(np.float32)
    return x


_done = {}


def build(repo, name, sfz, max_sec, layers, attack, release, pack):
    text = subprocess.run(["git", "-C", repo, "show", f"HEAD:{sfz}"], capture_output=True,
                          check=True).stdout.decode("utf-8", "replace")
    regs = parse_sfz(text)
    regs = [r for r in regs if "sample" in r and r.get("seq_position", "1") == "1"]
    # שכבות העוצמה: שומרים את העליונות (הכי 'חיות') עד המספר המבוקש
    by_key = {}
    for r in regs:
        by_key.setdefault((_num(r.get("lokey", r.get("key", "0"))), _num(r.get("hikey", r.get("key", "127")))), []).append(r)
    out = []
    for (lo, hi), rs in sorted(by_key.items()):
        rs = sorted(rs, key=lambda r: int(r.get("hivel", 127)))[-layers:]
        for i, r in enumerate(rs):
            path = (r.get("default_path", "") + r["sample"]).replace("\\", "/")
            key = "v_" + re.sub(r"\W", "_", os.path.splitext(r["sample"])[0])
            if key in _done:                      # אותה דגימה משמשת שני כלים (למשל מיתרים ומיתרים רכים)
                out.append(dict(_done[key][1], lo=lo, hi=hi, attack=attack, release=release,
                                vlo=0 if i == 0 else int(rs[i - 1].get("hivel", 127)) + 1,
                                vhi=127 if i == len(rs) - 1 else int(r.get("hivel", 127))))
                continue
            try:
                x = _read_wav(repo, path)
            except subprocess.CalledProcessError:
                print("missing", path)
                continue
            # חיתוך שקט בהתחלה ובסוף, ואורך מקסימלי עם דעיכה
            nz = np.nonzero(np.abs(x) > 10 ** (-50 / 20) * np.abs(x).max())[0]
            if len(nz):
                x = x[max(0, nz[0] - 32):]
            x = x[: int(max_sec * SR)]
            f = min(len(x), int(0.15 * SR))
            x[-f:] *= np.linspace(1, 0, f)
            peak = np.abs(x).max() + 1e-9
            pack[key] = np.round(x / peak * 0.9 * 32767).astype(np.int16)
            vol_db = float(float(r.get("volume", 0)) + 20 * np.log10(peak / 0.9))
            vlo = 0 if i == 0 else int(rs[i - 1].get("hivel", 127)) + 1
            out.append({"key": key, "lo": lo, "hi": hi, "vlo": vlo, "vhi": 127 if i == len(rs) - 1 else int(r.get("hivel", 127)),
                        "root": _num(r.get("pitch_keycenter", r.get("key", str(lo)))),
                        "tune": float(r.get("tune", 0)), "sr": SR, "loop": None, "att_db": -vol_db * 0.5,
                        "attack": attack, "decay": 1.0, "sustain_db": 0.0, "release": release})
            _done[key] = (None, out[-1])
    return out


def main(repo):
    from pack_io import load_pack, save_pack
    pack, meta = load_pack()
    for name, (sfz, max_sec, layers, att, rel) in INSTRUMENTS.items():
        meta[name] = build(repo, name, sfz, max_sec, layers, att, rel, pack)
        print(name, len(meta[name]), "regions")
    used = {r[f] for k, v in meta.items() if not k.startswith("_") for r in v for f in ("key", "right") if r.get(f)}
    pack = {k: v for k, v in pack.items() if k in used}
    save_pack(pack, meta)


if __name__ == "__main__":
    main(sys.argv[1])
