"""כלי פיתוח: משדרג את חבילת הצלילים (shir_studio/samples/pack.npz) בצלילים איכותיים יותר מ-FreePats.
כל המקורות ברישיון שמתיר מכירה מסחרית (CC0 או CC-BY 4.0 - ראו LICENSES.md).

שימוש:
    python tools/add_samples.py <תיקייה עם קבצי ה-sf2 שחולצו>
הקבצים (מ-freepats.zenvoid.org):
    UprightPianoKW-20220221.sf2          פסנתר      CC0
    SpanishClassicalGuitar-20190618.sf2  גיטרה      CC0
    Clarinet-20190818.sf2                קלרינט     CC0
    MuldjordKit 20201018.sf2             תופים      CC-BY 4.0 (Lars Muldjord)
"""
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from build_samples import parse, zones_of, rng, s16  # noqa: E402

PACK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shir_studio", "samples", "pack.npz")

# שם בתוכנה: (תבנית שם קובץ, מקסימום שניות לדגימה)
MELODIC = {
    "piano": ("UprightPianoKW*.sf2", 4.0, True),
    "guitar": ("SpanishClassicalGuitar*.sf2", 3.0, False),
    "clarinet": ("Clarinet-*.sf2", 4.0, False),
}
# תופים: שם -> מקש בערכה של Muldjord (לפי שמות הדגימות בקובץ)
KIT_KEYS = {"kick": 48, "snare": 50, "hat": 52, "open_hat": 53, "ride": 54, "crash": 58,
            "tom_hi": 61, "tom_low": 63}
KIT_LAYERS = (28, 52, 76, 98, 116)     # שכבות עוצמה שנשמרות לכל תוף
KIT_ROUND_ROBIN = 2                     # כמה דגימות שונות לכל שכבה (שלא יישמע 'מכונה')
KIT_MAX_SEC = {"kick": 1.0, "snare": 1.2, "hat": 0.6, "open_hat": 1.5, "ride": 2.5, "crash": 3.0,
               "tom_hi": 1.5, "tom_low": 1.8}


def _zones(sf):
    """כל אזורי הדגימה של התוכנית הראשונה בקובץ, עם הגדרות גלובליות ממוזגות."""
    smpl, phdr, pbag, pgen, inst, ibag, igen, shdr = sf
    out = []
    for z in zones_of(pbag, pgen, phdr[0][3], phdr[1][3]):
        if 41 not in z:
            continue
        klo, khi = rng(z, 43)
        ii = z[41]
        iz = zones_of(ibag, igen, inst[ii][1], inst[ii + 1][1])
        glob_ = iz[0] if 53 not in iz[0] else {}
        for zz in iz:
            if 53 not in zz:
                continue
            g = dict(glob_)
            g.update(zz)
            lo, hi = rng(g, 43)
            lo, hi = max(lo, klo), min(hi, khi)
            if lo <= hi:
                out.append((g, lo, hi))
    return out


def _read(sf, g, max_sec, stereo=False):
    """מחזיר את הדגימה (מונו: ממוצע של ימין ושמאל בזוג סטריאו) ופרטי הלולאה."""
    smpl, shdr = sf[0], sf[7]
    s = shdr[g[53]]
    start = s[1] + s16(g.get(0, 0)) + 32768 * s16(g.get(4, 0))
    end = s[2] + s16(g.get(1, 0)) + 32768 * s16(g.get(12, 0))
    ls = s[3] + s16(g.get(2, 0)) + 32768 * s16(g.get(45, 0)) - start
    le = s[4] + s16(g.get(3, 0)) + 32768 * s16(g.get(50, 0)) - start
    loop = (g.get(54, 0) & 1) == 1 and 0 < ls < le
    n = min(end - start, max(le, 1)) if loop else min(end - start, int(max_sec * s[5]))
    data = smpl[start:start + n].astype(np.float32)
    right = None
    if s[9] in (2, 4) and s[8] < len(shdr):       # זוג סטריאו - מוסיפים את הערוץ השני
        o = shdr[s[8]]
        other = smpl[o[1] + (start - s[1]):][:n].astype(np.float32)
        if len(other) == n:
            if stereo:                            # שומרים את שני הערוצים (צליל רחב ואמיתי)
                right = np.clip(other, -32768, 32767).astype(np.int16)
                if s[9] == 2:                     # הדגימה הזו היא הימנית - מחליפים
                    data, other = other, data
                    right = np.clip(other, -32768, 32767).astype(np.int16)
            else:
                data = 0.5 * (data + other)
    data = np.clip(data, -32768, 32767).astype(np.int16)
    root = g.get(58, s[6])
    if root > 127:
        root = s[6]

    def tc(op, d=-12000):
        return float(2 ** (s16(g.get(op, d)) / 1200))
    info = {"root": int(root), "tune": s16(g.get(51, 0)) * 100 + s16(g.get(52, 0)) + s[7], "sr": s[5],
            "loop": [int(ls), int(le)] if loop else None, "att_db": s16(g.get(48, 0)) / 10 * 0.4,
            "attack": tc(34), "decay": tc(36), "sustain_db": -g.get(37, 0) / 10, "release": tc(38)}
    if stereo:
        return data, info, s[9], right
    return data, info, s[9]


def melodic(path, name, max_sec, pack, stereo=False):
    sf = parse(path)
    regions, seen = [], set()
    for g, lo, hi in _zones(sf):
        vlo, vhi = rng(g, 44)
        if stereo:
            data, info, typ, right = _read(sf, g, max_sec, stereo=True)
        else:
            (data, info, typ), right = _read(sf, g, max_sec), None
        if typ == 2:                                  # ערוץ ימני - כבר נכלל בממוצע של השמאלי
            continue
        if (lo, hi, vlo, vhi) in seen:
            continue
        seen.add((lo, hi, vlo, vhi))
        key = f"{name}_{lo}_{vlo}"
        pack[key] = data
        reg = dict(info, key=key, lo=lo, hi=hi, vlo=vlo, vhi=vhi)
        if right is not None:
            pack[key + "_R"] = right
            reg["right"] = key + "_R"
        regions.append(reg)
    return regions


def kit(path, pack):
    sf = parse(path)
    by_key = {}
    for g, lo, hi in _zones(sf):
        if lo == hi:
            by_key.setdefault(lo, []).append(g)
    regions = []
    bounds = [0] + [(a + b) // 2 for a, b in zip(KIT_LAYERS, KIT_LAYERS[1:])] + [128]
    for drum, k in KIT_KEYS.items():
        zs = by_key[k]
        for li, v in enumerate(KIT_LAYERS):
            for rr in range(KIT_ROUND_ROBIN):
                want = v + 3 * rr
                g = min(zs, key=lambda z: abs(rng(z, 44)[0] - want))
                data, info, typ = _read(sf, g, KIT_MAX_SEC[drum])
                fade = min(len(data), int(0.05 * info["sr"]))
                d = data.astype(np.float32)
                d[-fade:] *= np.linspace(1, 0, fade)
                key = f"kit_{drum}_{v}_{rr}"
                pack[key] = d.astype(np.int16)
                regions.append(dict(info, key=key, drum=drum, vlo=bounds[li], vhi=bounds[li + 1] - 1,
                                    rr=rr, lo=k, hi=k))
    return regions


def main(folder):
    from pack_io import load_pack, save_pack
    pack, meta = load_pack()
    for name, (pat, max_sec, stereo) in MELODIC.items():
        path = glob.glob(os.path.join(folder, "**", pat), recursive=True)[0]
        meta[name] = melodic(path, name, max_sec, pack, stereo)
        print(name, len(meta[name]), "regions")
    path = glob.glob(os.path.join(folder, "**", "MuldjordKit*.sf2"), recursive=True)[0]
    meta["kit"] = kit(path, pack)
    print("kit", len(meta["kit"]), "regions")
    # מוחקים דגימות ישנות שאף כלי כבר לא משתמש בהן
    used = {r[f] for k, v in meta.items() if not k.startswith("_") for r in v for f in ("key", "right") if r.get(f)}
    pack = {k: v for k, v in pack.items() if k in used}
    save_pack(pack, meta)


if __name__ == "__main__":
    main(sys.argv[1])
