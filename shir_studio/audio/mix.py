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


def gate(v, floor_db=-14.0):
    """שער רעש רך: מנמיך את הקטעים השקטים בין המשפטים (נשימות, רחש)."""
    env = np.sqrt(uniform_filter1d(v ** 2, int(0.03 * SR)) + 1e-12)
    loud = np.percentile(env, 90) + 1e-9
    thr = loud * 10 ** (-30 / 20)
    g = np.clip((env - thr) / (thr * 2), 0, 1)
    floor = 10 ** (floor_db / 20)
    g = floor + (1 - floor) * g
    g = maximum_filter1d(g, int(0.15 * SR))          # לא לקטוע סופי מילים
    g = uniform_filter1d(g, int(0.08 * SR))
    return v * g


def deess(v, freq=6000, amount=0.6):
    """מחליש שריקות ('ס', 'ש') חזקות מדי."""
    hp = sosfiltfilt(butter(2, freq, btype="high", fs=SR, output="sos"), v)
    w = int(0.01 * SR)
    e_hi = np.sqrt(uniform_filter1d(hp ** 2, w) + 1e-12)
    e_all = np.sqrt(uniform_filter1d(v ** 2, w) + 1e-12)
    ratio = e_hi / e_all
    over = np.clip((ratio - 0.35) / 0.35, 0, 1)            # רק כשהשריקה דומיננטית
    g = 1 - amount * over
    g = uniform_filter1d(g, int(0.005 * SR))
    return v - hp + hp * g


def auto_eq(v):
    """אקולייזר אוטומטי: משווה את הקול לעקומה 'מאוזנת' בשלושה תחומים."""
    bands = ((200, 400, 250), (2000, 4500, 3200), (8000, 12000, 10000))
    ref = rms(sosfiltfilt(butter(2, [500, 1500], btype="band", fs=SR, output="sos"), v))
    target = (-1.0, -4.0, -12.0)                            # dB ביחס לאמצע
    for (lo, hi, f0), t in zip(bands, target):
        b = rms(sosfiltfilt(butter(2, [lo, hi], btype="band", fs=SR, output="sos"), v))
        diff = t - 20 * np.log10(b / max(ref, 1e-9) + 1e-9)
        v = _peaking(v, f0, float(np.clip(diff * 0.5, -4, 4)), 0.9)
    return v


def process_voice(v):
    v = sosfiltfilt(butter(2, 90, btype="high", fs=SR, output="sos"), v)
    v = _peaking(v, 250, -2.0, 1.0)      # פחות 'בוץ'
    v = _peaking(v, 3200, 2.5, 0.8)      # בהירות ונוכחות
    v = auto_eq(v)
    v = deess(v)
    v = gate(v)
    peak_ref = np.percentile(np.abs(v), 99.5) + 1e-9
    v = v / peak_ref * 0.5
    thr = 20 * np.log10(rms(v[np.abs(v) > 0.02]) if np.any(np.abs(v) > 0.02) else 0.1)
    return compress(v, threshold_db=thr - 2, ratio=3.0)


def master(st, target_db=-14.0):
    """עיבוד סופי (מאסטרינג): EQ עדין, קומפרסור 'דבק' ועוצמה כמו בשירים מסחריים."""
    sos_lo = butter(1, 60, btype="high", fs=SR, output="sos")
    out = np.empty_like(st)
    for c in range(st.shape[1]):
        x = sosfiltfilt(sos_lo, st[:, c])
        x = _peaking(x, 11000, 1.5, 0.7)                    # אוויר
        out[:, c] = x
    mono = out.mean(axis=1)
    env = np.sqrt(uniform_filter1d(mono ** 2, int(0.05 * SR)) + 1e-12)
    db = 20 * np.log10(env)
    thr = np.percentile(db, 80) - 3
    g = -np.maximum(db - thr, 0) * (1 - 1 / 2.0)
    g = uniform_filter1d(g, int(0.2 * SR))
    out *= 10 ** (g / 20)[:, None]
    # עוצמה: RMS של הקטעים הרועשים (קירוב פשוט ל-LUFS)
    loud = env > np.percentile(env, 30)
    cur = 20 * np.log10(rms(out[loud]) if loud.any() else rms(out))
    return out * 10 ** ((target_db - 3 - cur) / 20)


def limiter(st, ceiling=0.89):
    peak = np.max(np.abs(st), axis=1)
    look = int(0.005 * SR)
    pk = maximum_filter1d(peak, size=2 * look + 1)
    gain = np.minimum(1.0, ceiling / np.maximum(pk, 1e-9))
    gain = -maximum_filter1d(-gain, size=2 * look + 1)
    gain = uniform_filter1d(gain, look)
    out = st * gain[:, None]
    return np.clip(out, -ceiling, ceiling)


def choir_copies(vst, copies=4, depth=0.35):
    """מקהלה: עותקים מושהים בזמנים מעט שונים, עם שינוי קל וזוחל בגובה, מפוזרים בסטריאו."""
    rng = np.random.default_rng(11)
    mono = vst.mean(axis=1)
    n = len(mono)
    t = np.arange(n) / SR
    out = np.zeros_like(vst)
    for k in range(copies):
        base = 0.025 + 0.012 * k
        lfo = 0.004 * np.sin(2 * np.pi * rng.uniform(0.15, 0.4) * t + rng.uniform(0, 6.28))
        idx = np.clip(np.arange(n) - (base + lfo) * SR, 0, n - 1)
        c = np.interp(idx, np.arange(n), mono)
        c = sosfilt(butter(1, 5000, fs=SR, output="sos"), c)   # עותקים קצת 'רכים' יותר
        gl, gr = pan_gains(-0.8 + 1.6 * k / max(1, copies - 1))
        out[:, 0] += c * gl
        out[:, 1] += c * gr
    return out * depth / copies * 2


def pan_gains(p):
    ang = (p + 1) * np.pi / 4
    return np.cos(ang), np.sin(ang)


def mix(voice, tracks, lead, style, accomp_db=0.0, voice_db=0.0, reverb=1.0, stems=False, harmony=None, choir=False):
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
    voices = harmony if isinstance(harmony, (list, tuple)) else ([harmony] if harmony is not None else [])
    pans = (0.35, -0.35)
    for hi, hv in enumerate(voices):
        h = process_voice(hv.astype(np.float64))
        h *= 10 ** (-6 / 20) * (vr / max(rms(h[np.abs(h) > 0.02]) if np.any(np.abs(h) > 0.02) else 1, 1e-9))
        h *= 10 ** (voice_db / 20)
        hb = np.zeros(n)
        d = s + int((0.018 + 0.009 * hi) * SR)      # השהיה קטנה - נשמע כמו זמר נוסף
        hb[d:d + len(h)] = h[: max(0, min(len(h), n - d))]
        gl, gr = pan_gains(pans[hi % 2])
        vst[:, 0] += hb * gl * 0.9
        vst[:, 1] += hb * gr * 0.9
    if choir:
        vst += choir_copies(vst)
    vst = add_reverb(vst, rv * 0.7, 1.6)
    acc = add_reverb(acc, rv, 2.0)
    out = vst + acc
    # חיתוך שקט בסוף
    loud = np.where(np.max(np.abs(out), axis=1) > 1e-4)[0]
    if len(loud):
        out = out[: min(n, loud[-1] + int(0.5 * SR))]
    # עוצמה כוללת סבירה והגבלה
    pre = rms(out)
    out = master(out)
    g = rms(out) / max(pre, 1e-9)
    out = limiter(out)
    fade = int(0.3 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    if stems:
        k = len(out)
        return out.astype(np.float32), {"קול": (vst[:k] * g).astype(np.float32),
                                        "ליווי": (acc[:k] * g).astype(np.float32)}
    return out.astype(np.float32)
