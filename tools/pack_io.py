"""שמירת חבילת הצלילים בכמה קבצים (GitHub לא מקבל קובץ מעל 100MB)."""
import glob
import json
import os

import numpy as np

DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shir_studio", "samples")
PARTS = 3


def load_pack():
    pack, meta = {}, None
    for p in sorted(glob.glob(os.path.join(DIR, "pack*.npz"))):
        d = np.load(p)
        for k in d.files:
            if k == "_meta":
                meta = json.loads(bytes(d["_meta"]).decode())
            else:
                pack[k] = d[k]
    return pack, meta


def save_pack(pack, meta):
    for p in glob.glob(os.path.join(DIR, "pack*.npz")):
        os.remove(p)
    keys = sorted(pack, key=lambda k: -pack[k].nbytes)
    parts = [dict() for _ in range(PARTS)]
    size = [0] * PARTS
    for k in keys:                                   # חלוקה מאוזנת לפי גודל
        i = size.index(min(size))
        parts[i][k] = pack[k]
        size[i] += pack[k].nbytes
    parts[0]["_meta"] = np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8)
    for i, part in enumerate(parts):
        p = os.path.join(DIR, "pack.npz" if i == 0 else f"pack{i + 1}.npz")
        np.savez_compressed(p, **part)
        print(os.path.basename(p), os.path.getsize(p) // 1024 // 1024, "MB")
