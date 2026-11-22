"""כלי נגינה סינתטיים - כל הצלילים נוצרים בקוד, בלי קבצי דגימות, ולכן בלי בעיית רישיונות."""
import numpy as np
from scipy.signal import butter, sosfilt, resample_poly

from ..audio.fileio import SR

_cache = {}
_rng = np.random.default_rng(1234)


def hz(midi, tuning=0.0):
    return 440.0 * 2 ** ((midi + tuning - 69) / 12)


def _adsr(n, a, d, s, r, hold):
    """hold = מספר דגימות עד שחרור."""
    t = np.arange(n) / SR
    env = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    rel_t = hold / SR
    level_at_rel = np.interp(rel_t, t, env) if n else 0
    env = np.where(t >= rel_t, level_at_rel * np.exp(-(t - rel_t) / max(r, 1e-4)), env)
    return env


def _additive(f, n, amps, decays=None, inharm=0.0, detune_cents=0.0, vib=(0, 0), phase_rand=True):
    t = np.arange(n) / SR
    out = np.zeros(n)
    fm = 1.0
    if vib[1]:
        fm = 1 + vib[1] * np.sin(2 * np.pi * vib[0] * t + _rng.uniform(0, 6.28)) * np.minimum(1, t / 0.4)
    f = f * 2 ** (detune_cents / 1200)
    for k, a in enumerate(amps, start=1):
        fk = f * k * np.sqrt(1 + inharm * k * k)
        if fk > 17000 or a <= 0:
            break
        ph = 2 * np.pi * fk * np.cumsum(fm) / SR if vib[1] else 2 * np.pi * fk * t
        p0 = _rng.uniform(0, 6.28) if phase_rand else 0
        part = a * np.sin(ph + p0)
        if decays is not None:
            part *= np.exp(-t * decays[k - 1])
        out += part
    return out


# ------------------------------------------------------------ כלים מלודיים
def piano(f, dur, vel):
    n = int((dur + 1.2) * SR)
    k = np.arange(1, 25)
    bright = 0.5 + vel
    amps = (1 / k ** 1.3) * np.exp(-k / (6 * bright))
    dec = 0.6 + 0.35 * k * (f / 260) ** 0.4
    x = _additive(f, n, amps, dec, inharm=0.0003 * (f / 260))
    x += 0.5 * _additive(f, n, amps * 0.6, dec * 1.2, inharm=0.0003, detune_cents=1.5)
    hold = int(dur * SR)
    x *= _adsr(n, 0.004, 3.0, 1.0, 0.25, hold)
    click = _rng.standard_normal(int(0.01 * SR)) * np.exp(-np.arange(int(0.01 * SR)) / 60)
    x[:len(click)] += 0.05 * vel * click
    return x


def guitar(f, dur, vel):
    """Karplus-Strong מורחב, מחושב בבלוקים (מהיר)."""
    over = 4
    sr = SR * over
    n = int((dur + 1.5) * sr)
    P = max(2, int(round(sr / f - 0.5)))
    noise = _rng.uniform(-1, 1, P)
    # מיקום פריטה - מסנן מסרק עדין
    pick = max(1, int(P * 0.13))
    noise = noise - np.roll(noise, pick) * 0.6
    sos = butter(1, min(0.45, (2000 + 5000 * vel) / sr * 2), output="sos")
    noise = sosfilt(sos, noise)
    y = np.zeros(n)
    y[:P] = noise
    decay = 0.996 if f < 200 else 0.994
    mute_at = int(dur * sr)
    b = 1
    while b * P < n:
        s = b * P
        e = min(n, s + P)
        prev = y[s - P:e - P]
        prev2 = y[s - P - 1:e - P - 1] if s - P - 1 >= 0 else np.concatenate([[0], y[s - P:e - P - 1]])
        d = decay if s < mute_at else 0.93
        y[s:e] = d * 0.5 * (prev + prev2[:len(prev)])
        b += 1
    y = resample_poly(y, 1, over)
    return y * (0.6 + 0.6 * vel)


def bass(f, dur, vel):
    n = int((dur + 0.4) * SR)
    amps = np.array([1, 0.45, 0.2, 0.1, 0.05])
    x = _additive(f, n, amps, decays=np.array([0.8, 1.5, 2.5, 4, 6]))
    return x * _adsr(n, 0.008, 0.4, 0.6, 0.08, int(dur * SR)) * (0.7 + 0.5 * vel)


def strings(f, dur, vel):
    n = int((dur + 0.6) * SR)
    k = np.arange(1, 40)
    amps = (1 / k) * np.exp(-k * f / 4500)
    x = sum(_additive(f, n, amps, detune_cents=c, vib=(5.2, 0.003)) for c in (-7, 0, 7)) / 3
    return x * _adsr(n, 0.25, 1.0, 0.85, 0.4, int(dur * SR)) * (0.5 + 0.5 * vel)


def brass(f, dur, vel):
    n = int((dur + 0.3) * SR)
    t = np.arange(n) / SR
    k = np.arange(1, 30)
    x = np.zeros(n)
    bright = np.minimum(1, t / 0.06) * (0.7 + 0.3 * vel)
    for kk in k:
        fk = f * kk
        if fk > 15000:
            break
        a = (1 / kk) * np.exp(-(kk - 1) * (1.4 - bright) * 0.9) * np.exp(-fk / 6000)
        x += a * np.sin(2 * np.pi * fk * t * (1 + 0.002 * np.sin(2 * np.pi * 5 * t)) + _rng.uniform(0, 6))
    return x * _adsr(n, 0.04, 0.3, 0.8, 0.12, int(dur * SR)) * (0.5 + 0.5 * vel)


def accordion(f, dur, vel):
    """אקורדיון/אורגן כמו בכלייזמר - שני קנים מכוונים מעט שונה (טרמולו)."""
    n = int((dur + 0.15) * SR)
    k = np.arange(1, 30)
    amps = np.where(k % 2 == 1, 1 / k, 0.5 / k) * np.exp(-k * f / 6000)
    x = _additive(f, n, amps, detune_cents=-6) + _additive(f, n, amps, detune_cents=6)
    return 0.5 * x * _adsr(n, 0.03, 0.2, 0.9, 0.08, int(dur * SR)) * (0.5 + 0.5 * vel)


# פורמנטים לתנועות (F, רוחב, עוצמה)
VOWELS = {
    "a": [(800, 80, 1.0), (1150, 90, 0.5), (2900, 120, 0.1), (3900, 130, 0.05)],
    "o": [(450, 70, 1.0), (800, 80, 0.3), (2830, 100, 0.03)],
    "u": [(325, 50, 1.0), (700, 60, 0.12), (2530, 170, 0.02)],
}


def _voice(f, dur, vel, vowel, voices=4, attack=0.12, release=0.3):
    n = int((dur + release + 0.1) * SR)
    k = np.arange(1, 60)
    fk = f * k
    env = sum(g * np.exp(-0.5 * ((fk - F) / (B * 1.6)) ** 2) for F, B, g in VOWELS[vowel])
    amps = (env + 0.01) / k ** 0.5
    amps = np.where(fk < 8000, amps, 0)
    x = sum(_additive(f, n, amps, detune_cents=_rng.uniform(-12, 12),
                      vib=(_rng.uniform(4.6, 5.8), 0.004)) for _ in range(voices)) / voices
    breath = sosfilt(butter(2, [1500, 5000], btype="band", fs=SR, output="sos"), _rng.standard_normal(n))
    x += 0.004 * breath
    return x * _adsr(n, attack, 1.0, 0.9, release, int(dur * SR)) * (0.5 + 0.5 * vel)


def choir(f, dur, vel):
    return _voice(f, dur, vel, "a")


def choir_oo(f, dur, vel):
    return _voice(f, dur, vel, "o", voices=3)


def bass_voice(f, dur, vel):
    """'דום' של זמר בס."""
    x = _voice(f, dur, vel, "u", voices=2, attack=0.02, release=0.12)
    n = len(x)
    return x * np.exp(-np.arange(n) / SR / max(0.15, dur * 0.8))


# ------------------------------------------------------------ תופים
def _noise(n):
    return _rng.standard_normal(n)


def kick(vel):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 48 + 90 * np.exp(-t / 0.03)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.18)
    x[:200] += 0.3 * _noise(200) * np.exp(-np.arange(200) / 40)
    return x * (0.6 + 0.6 * vel)


def snare(vel):
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
    nz = sosfilt(butter(2, [1500, 9000], btype="band", fs=SR, output="sos"), _noise(n)) * np.exp(-t / 0.09)
    return (0.5 * tone + 1.2 * nz) * (0.5 + 0.5 * vel)


def hat(vel, open_=False):
    n = int((0.35 if open_ else 0.08) * SR)
    t = np.arange(n) / SR
    nz = sosfilt(butter(4, 7000, btype="high", fs=SR, output="sos"), _noise(n))
    return nz * np.exp(-t / (0.12 if open_ else 0.022)) * (0.3 + 0.4 * vel)


def tambourine(vel):
    n = int(0.2 * SR)
    t = np.arange(n) / SR
    nz = sosfilt(butter(2, [5000, 12000], btype="band", fs=SR, output="sos"), _noise(n))
    jingle = 1 + 0.6 * np.sin(2 * np.pi * 70 * t)
    return nz * jingle * np.exp(-t / 0.06) * (0.4 + 0.4 * vel)


def crash(vel):
    n = int(2.0 * SR)
    t = np.arange(n) / SR
    nz = sosfilt(butter(2, 4000, btype="high", fs=SR, output="sos"), _noise(n))
    return nz * np.exp(-t / 0.7) * (0.25 + 0.25 * vel)


def timpani(f, dur, vel):
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    x = sum(a * np.sin(2 * np.pi * f * r * t) for r, a in ((1, 1), (1.5, 0.5), (1.98, 0.3), (2.44, 0.2)))
    x *= np.exp(-t / 0.5)
    x[:300] += 0.2 * _noise(300) * np.exp(-np.arange(300) / 60)
    return x * (0.5 + 0.6 * vel)


def clap(vel):
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    nz = sosfilt(butter(2, [900, 4000], btype="band", fs=SR, output="sos"), _noise(n))
    env = sum(np.exp(-np.maximum(t - d, 0) / 0.01) * (t >= d) for d in (0, 0.01, 0.02)) + \
        np.exp(-np.maximum(t - 0.03, 0) / 0.08) * (t >= 0.03)
    return nz * env * 0.35 * (0.5 + 0.5 * vel)


MELODIC = {"piano": piano, "guitar": guitar, "bass": bass, "strings": strings, "brass": brass,
           "accordion": accordion, "choir": choir, "choir_oo": choir_oo, "bass_voice": bass_voice,
           "timpani": timpani}
DRUMS = {"kick": kick, "snare": snare, "hat": hat, "open_hat": lambda v: hat(v, True),
         "tambourine": tambourine, "crash": crash, "clap": clap}


from . import sampler

SYNTH_ONLY = {"bass_voice"}


def render_note(instrument, midi, dur, vel, tuning=0.0):
    key = (instrument, int(midi), round(dur, 2), round(vel, 1), round(tuning, 2))
    if key in _cache:
        return _cache[key]
    if instrument not in SYNTH_ONLY and sampler.has(instrument):
        x = sampler.note(instrument, int(midi), dur, vel, tuning)
    else:
        x = MELODIC[instrument](hz(midi, tuning), dur, vel).astype(np.float32)
    if len(_cache) < 3000:
        _cache[key] = x
    return x


def render_drum(name, vel):
    if sampler.has("drums"):
        var = int(_rng.integers(2))                          # שתי גרסאות לכל מכה
        key = ("s", name, round(vel, 1), var)
        if key not in _cache:
            _cache[key] = sampler.drum(name, vel, var)
        return _cache[key]
    key = (name, round(vel, 1), int(_rng.integers(3)))   # 3 גרסאות לכל מכה - פחות 'מכני'
    if key not in _cache:
        _cache[key] = DRUMS[name](vel).astype(np.float32)
    return _cache[key]


def has_drum(name):
    """האם יש צליל אמיתי לתוף הזה (למשל טומים - רק בערכת התופים החדשה)."""
    return sampler.available() and ("kit" in sampler._meta and name in sampler.KIT
                                    or name in sampler._meta.get("_drum_keys", {}))
