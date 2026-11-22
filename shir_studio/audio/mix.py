"""עיבוד הקול, הדהוד (ריוורב), ערבוב ומגביל עוצמה."""
import numpy as np
from scipy.signal import butter, sosfiltfilt, oaconvolve, sosfilt
from scipy.ndimage import maximum_filter1d, uniform_filter1d

from .fileio import SR

_ir_cache = {}


def reverb_ir(seconds=1.8):
    if seconds in _ir_cache:
        return _ir_cache[seconds]
    rng = np.random.default_rng(42)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    irs = []
    for ch in range(2):
        nz = rng.standard_normal(n)
        lo = sosfilt(butter(2, 2500, fs=SR, output="sos"), nz) * np.exp(-t * 6.9 / seconds)
        hi = (nz - sosfilt(butter(2, 2500, fs=SR, output="sos"), nz)) * np.exp(-t * 6.9 / (seconds * 0.45))
        ir = lo + 0.5 * hi
        pre = int(0.022 * SR)
        ir = np.concatenate([np.zeros(pre), ir])
        ir = sosfilt(butter(1, 180, btype="high", fs=SR, output="sos"), ir)
        irs.append(ir / np.sqrt(np.sum(ir ** 2)))
    _ir_cache[seconds] = irs
    return irs


def add_reverb(stereo, amount, seconds=1.8):
    if amount <= 0:
        return stereo
    irs = reverb_ir(seconds)
    wet = np.stack([oaconvolve(stereo[:, c], irs[c])[: len(stereo)] for c in range(2)], axis=1)
    return stereo + amount * wet


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


def compress(x, threshold_db=-20, ratio=3.0, attack=0.01, release=0.15):
    env = np.sqrt(uniform_filter1d(x ** 2, int(0.02 * SR)) + 1e-12)
    db = 20 * np.log10(env)
    over = np.maximum(db - threshold_db, 0)
    gain_db = -over * (1 - 1 / ratio)
    # החלקה
    g = uniform_filter1d(gain_db, int(release * SR))
    return x * 10 ** (g / 20)


def _peaking(x, f0, gain_db, q=1.0):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / SR
    alpha = np.sin(w) / (2 * q)
    b = np.array([1 + alpha * A, -2 * np.cos(w), 1 - alpha * A])
    a = np.array([1 + alpha / A, -2 * np.cos(w), 1 - alpha / A])
    from scipy.signal import tf2sos
    return sosfilt(tf2sos(b / a[0], a / a[0]), x)


def process_voice(v):
    v = sosfiltfilt(butter(2, 90, btype="high", fs=SR, output="sos"), v)
    v = _peaking(v, 250, -2.0, 1.0)      # פחות 'בוץ'
    v = _peaking(v, 3200, 2.5, 0.8)      # בהירות ונוכחות
    peak_ref = np.percentile(np.abs(v), 99.5) + 1e-9
    v = v / peak_ref * 0.5
    thr = 20 * np.log10(rms(v[np.abs(v) > 0.02]) if np.any(np.abs(v) > 0.02) else 0.1)
    return compress(v, threshold_db=thr - 2, ratio=3.0)


def limiter(st, ceiling=0.89):
    peak = np.max(np.abs(st), axis=1)
    look = int(0.005 * SR)
    pk = maximum_filter1d(peak, size=2 * look + 1)
    gain = np.minimum(1.0, ceiling / np.maximum(pk, 1e-9))
    gain = -maximum_filter1d(-gain, size=2 * look + 1)
    gain = uniform_filter1d(gain, look)
    out = st * gain[:, None]
    return np.clip(out, -ceiling, ceiling)


def pan_gains(p):
    ang = (p + 1) * np.pi / 4
    return np.cos(ang), np.sin(ang)


def mix(voice, tracks, lead, style, accomp_db=0.0, voice_db=0.0, reverb=1.0, stems=False, harmony=None):
    """voice: מונו מעובד. tracks: [(spec, buf)]. lead: שניות מבוא לפני השירה."""
    n = max(len(t[1]) for t in tracks) if tracks else len(voice) + int(lead * SR)
    n = max(n, len(voice) + int(lead * SR) + SR)
    v = process_voice(voice.astype(np.float64))
    vbuf = np.zeros(n)
    s = int(lead * SR)
    vbuf[s:s + len(v)] = v * 10 ** (voice_db / 20)
    vr = rms(v[np.abs(v) > 0.02]) if np.any(np.abs(v) > 0.02) else rms(v)

    acc = np.zeros((n, 2))
    for spec, buf, *_ in tracks:
        b = np.zeros(n)
        b[:min(n, len(buf))] = buf[:n]
        r = rms(b[np.abs(b) > 1e-4]) if np.any(np.abs(b) > 1e-4) else 1.0
        b = b / r * spec.get("volume", 0.7)
        gl, gr = pan_gains(spec.get("pan", 0))
        acc[:, 0] += b * gl
        acc[:, 1] += b * gr
    if tracks:
        ar = rms(acc[s:s + len(v)]) if len(v) else rms(acc)
        target = vr * 10 ** ((style.get("accomp_db", -5) + accomp_db) / 20)
        acc *= target / max(ar, 1e-9)
        # הנמכה קלה של הליווי כשיש שירה
        venv = uniform_filter1d(np.abs(vbuf), int(0.2 * SR))
        duck = 1 - 0.25 * np.clip(venv / (vr + 1e-9), 0, 1)
        acc *= duck[:, None]
    rv = style.get("reverb", 0.2) * reverb
    vst = np.stack([vbuf, vbuf], axis=1) * 0.707
    if harmony is not None:
        h = process_voice(harmony.astype(np.float64))
        h *= 10 ** (-6 / 20) * (vr / max(rms(h[np.abs(h) > 0.02]) if np.any(np.abs(h) > 0.02) else 1, 1e-9))
        h *= 10 ** (voice_db / 20)
        hb = np.zeros(n)
        d = s + int(0.018 * SR)                     # השהיה קטנה - נשמע כמו זמר נוסף
        hb[d:d + len(h)] = h[: max(0, min(len(h), n - d))]
        gl, gr = pan_gains(0.35)
        vst[:, 0] += hb * gl * 0.9
        vst[:, 1] += hb * gr * 0.9
    vst = add_reverb(vst, rv * 0.7, 1.6)
    acc = add_reverb(acc, rv, 2.0)
    out = vst + acc
    # חיתוך שקט בסוף
    loud = np.where(np.max(np.abs(out), axis=1) > 1e-4)[0]
    if len(loud):
        out = out[: min(n, loud[-1] + int(0.5 * SR))]
    # עוצמה כוללת סבירה והגבלה
    g = 0.25 / max(rms(out), 1e-9)
    out = limiter(out * g)
    fade = int(0.3 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    if stems:
        k = len(out)
        return out.astype(np.float32), {"קול": (vst[:k] * g).astype(np.float32),
                                        "ליווי": (acc[:k] * g).astype(np.float32)}
    return out.astype(np.float32)
