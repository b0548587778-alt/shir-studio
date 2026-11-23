"""כלי פיתוח: מוסיף לחבילת הצלילים כלי מתוך תיקיית SFZ מקומית (למשל אקורדיון הכפתורים של FreePats, CC0).

שימוש:
    python tools/add_sfz.py accordion "<תיקייה>/PRESET Button Accordion HN tuned.sfz"
"""
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(__file__))
from add_vsco import parse_sfz, _num  # noqa: E402
from pack_io import load_pack, save_pack  # noqa: E402


def build(name, sfz_path, pack, max_sec=4.0):
    folder = os.path.dirname(sfz_path)
    text = open(sfz_path, encoding="utf-8", errors="replace").read()
    out = []
    for r in parse_sfz(text):
        if "sample" not in r or r.get("trigger") == "release":     # צלילי 'שחרור' - לא בשימוש
            continue
        x, sr = sf.read(os.path.join(folder, r.get("default_path", ""), r["sample"]), dtype="float32", always_2d=True)
        loop = None
        if "loop_start" in r and "loop_end" in r and r.get("loop_mode", "") .startswith("loop"):
            loop = [int(r["loop_start"]), int(r["loop_end"])]
            x = x[: loop[1] + 2]                     # צליל עם לולאה - מספיק עד סוף הלולאה
        else:
            x = x[: int(max_sec * sr)]
        if x.shape[1] == 1:
            x = np.repeat(x, 2, axis=1)
        peak = np.abs(x).max() + 1e-9
        q = np.round(x[:, :2] / peak * 0.9 * 32767).astype(np.int16)
        lo = _num(r.get("lokey", "0"))
        key = f"{name}_{lo}"
        pack[key] = np.ascontiguousarray(q[:, 0])
        reg = {"key": key, "lo": lo, "hi": _num(r.get("hikey", "127")),
               "root": _num(r.get("pitch_keycenter", str(lo))), "tune": float(r.get("tune", 0)), "sr": int(sr),
               "loop": loop, "att_db": float(-0.5 * 20 * np.log10(peak / 0.9)),
               "attack": float(r.get("ampeg_attack", 0.01)), "decay": float(r.get("ampeg_decay", 1.0)),
               "sustain_db": float(20 * np.log10(max(float(r.get("ampeg_sustain", 100)), 1) / 100)),
               "release": float(r.get("ampeg_release", 0.3))}
        if not np.allclose(q[:, 0], q[:, 1], atol=64):
            pack[key + "_R"] = np.ascontiguousarray(q[:, 1])
            reg["right"] = key + "_R"
        out.append(reg)
    return out


if __name__ == "__main__":
    name, path = sys.argv[1], sys.argv[2]
    pack, meta = load_pack()
    meta[name] = build(name, path, pack)
    print(name, len(meta[name]), "regions")
    used = {r[f] for k, v in meta.items() if not k.startswith("_") for r in v for f in ("key", "right") if r.get(f)}
    save_pack({k: v for k, v in pack.items() if k in used}, meta)
