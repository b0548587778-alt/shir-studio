"""כלי פיתוח: מחלץ מתוך FluidR3_GM.sf2 (רישיון MIT) רק את הכלים שהתוכנה צריכה,
ושומר אותם בחבילה קטנה: shir_studio/samples/pack.npz
שימוש: python tools/build_samples.py /path/FluidR3_GM.sf2"""
import struct
import sys
import json
import numpy as np

# שם בתוכנה: (בנק, תוכנית GM)
WANTED = {
    "piano": (0, 0), "guitar": (0, 24), "steel_guitar": (0, 25), "bass": (0, 33),
    "acoustic_bass": (0, 32), "strings": (0, 48), "slow_strings": (0, 49), "choir": (0, 52),
    "choir_oo": (0, 53), "trumpet": (0, 56), "brass": (0, 61), "clarinet": (0, 71),
    "accordion": (0, 21), "timpani": (0, 47), "organ": (0, 16), "flute": (0, 73),
    "violin": (0, 40), "drums": (128, 0),
}
DRUM_KEYS = {"kick": 36, "snare": 38, "clap": 39, "hat": 42, "open_hat": 46, "crash": 49,
             "tambourine": 54, "ride": 51, "tom_low": 45, "tom_hi": 50}
MAX_SEC = 4.0


def chunks(data, off, end):
    while off < end:
        cid, size = struct.unpack_from("<4sI", data, off)
        yield cid, off + 8, size
        off += 8 + size + (size & 1)


def parse(path):
    data = open(path, "rb").read()
    out = {}
    for cid, o, sz in chunks(data, 12, len(data)):
        if cid == b"LIST":
            kind = data[o:o + 4]
            for c2, o2, s2 in chunks(data, o + 4, o + sz):
                out[(kind, c2)] = data[o2:o2 + s2]
    smpl = np.frombuffer(out[(b"sdta", b"smpl")], dtype="<i2")
    def recs(name, fmt):
        b = out[(b"pdta", name)]
        n = struct.calcsize(fmt)
        return [struct.unpack_from(fmt, b, i) for i in range(0, len(b), n)]
    phdr = recs(b"phdr", "<20sHHHIII")
    pbag = recs(b"pbag", "<HH")
    pgen = recs(b"pgen", "<HH")
    inst = recs(b"inst", "<20sH")
    ibag = recs(b"ibag", "<HH")
    igen = recs(b"igen", "<HH")
    shdr = recs(b"shdr", "<20sIIIIIBbHH")
    return smpl, phdr, pbag, pgen, inst, ibag, igen, shdr


def s16(v):
    return v - 65536 if v >= 32768 else v


def zones_of(bags, gens, start, end):
    zs = []
    for b in range(start, end):
        g0, g1 = bags[b][0], bags[b + 1][0]
        zs.append({op: amt for op, amt in gens[g0:g1]})
    return zs


def rng(z, op):
    if op in z:
        v = z[op]
        return v & 0xFF, v >> 8
    return 0, 127


def extract(path):
    smpl, phdr, pbag, pgen, inst, ibag, igen, shdr = parse(path)
    pack = {}
    meta = {}
    for name, (bank, prog) in WANTED.items():
        pi = [i for i, p in enumerate(phdr[:-1]) if p[1] == prog and p[2] == bank][0]
        pz = zones_of(pbag, pgen, phdr[pi][3], phdr[pi + 1][3])
        regions = []
        for z in pz:
            if 41 not in z:
                continue
            klo, khi = rng(z, 43)
            ii = z[41]
            iz = zones_of(ibag, igen, inst[ii][1], inst[ii + 1][1])
            glob = iz[0] if 53 not in iz[0] else {}
            for zz in iz:
                if 53 not in zz:
                    continue
                g = dict(glob); g.update(zz)
                vlo, vhi = rng(g, 44)
                if not (vlo <= 100 <= vhi):
                    continue
                s = shdr[g[53]]
                if s[9] == 2:          # ערוץ ימני של זוג סטריאו - מדלגים
                    continue
                lo, hi = rng(g, 43)
                lo, hi = max(lo, klo), min(hi, khi)
                if lo > hi:
                    continue
                start = s[1] + s16(g.get(0, 0)) + 32768 * s16(g.get(4, 0))
                end = s[2] + s16(g.get(1, 0)) + 32768 * s16(g.get(12, 0))
                ls = s[3] + s16(g.get(2, 0)) + 32768 * s16(g.get(45, 0)) - start
                le = s[4] + s16(g.get(3, 0)) + 32768 * s16(g.get(50, 0)) - start
                loop = (g.get(54, 0) & 1) == 1 and 0 < ls < le
                sr = s[5]
                maxn = int(MAX_SEC * sr)
                if loop:
                    n = min(end - start, max(le, 1))
                else:
                    n = min(end - start, maxn)
                data = smpl[start:start + n].copy()
                root = g.get(58, s[6])
                if root > 127:
                    root = s[6]
                tune = s16(g.get(51, 0)) * 100 + s16(g.get(52, 0)) + s[7]
                def tc(op, d=-12000):
                    return float(2 ** (s16(g.get(op, d)) / 1200))
                key = f"s{start}_{n}"
                if any(r["key"] == key and r["lo"] == lo for r in regions):
                    continue
                # כל מקש מקבל אזור אחד בלבד
                if any(r["lo"] <= lo and hi <= r["hi"] for r in regions):
                    continue
                pack[key] = data
                regions.append({"key": key, "lo": lo, "hi": hi, "root": int(root), "tune": tune,
                                "sr": sr, "loop": [int(ls), int(le)] if loop else None,
                                "att_db": s16(g.get(48, 0)) / 10 * 0.4,
                                "attack": tc(34), "decay": tc(36), "sustain_db": -g.get(37, 0) / 10,
                                "release": tc(38)})
        meta[name] = regions
    meta["_drum_keys"] = DRUM_KEYS
    return pack, meta


if __name__ == "__main__":
    pack, meta = extract(sys.argv[1])
    pack["_meta"] = np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8)
    np.savez_compressed("shir_studio/samples/pack.npz", **pack)
    for k, v in meta.items():
        if not k.startswith("_"):
            print(k, len(v), "regions")
