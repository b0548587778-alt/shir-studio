"""שינוי סולם וקצב של שיר שלם (פלייבק): להעלות או להוריד בחצאי טונים, להאט או להאיץ - כל אחד בנפרד.
השיטה: 'ווקודר פאזה' עם נעילת פאזה סביב כל שיא בספקטרום (Laroche-Dolson), ואחריו דגימה מחדש."""
from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly

from .fileio import SR

N_FFT = 4096
HOP_OUT = N_FFT // 4


def _stretch_channel(x, rate, progress=None):
    """rate > 1 = קצר יותר (מהיר יותר). הגובה לא משתנה."""
    win = np.hanning(N_FFT + 1)[:-1]
    hop_in = HOP_OUT * rate
    x = np.concatenate([np.zeros(N_FFT // 2), np.asarray(x, dtype=np.float64), np.zeros(N_FFT)])
    n_frames = max(2, int((len(x) - N_FFT) / hop_in))
    out = np.zeros(n_frames * HOP_OUT + N_FFT)
    norm = np.zeros_like(out)
    omega = 2 * np.pi * np.arange(N_FFT // 2 + 1) / N_FFT           # התקדמות הפאזה לדגימה בכל תדר
    bins = np.arange(N_FFT // 2 + 1)
    prev_phase = None
    phase_out = None
    prev_pos = 0
    for k in range(n_frames):
        pos = int(round(k * hop_in))
        spec = np.fft.rfft(x[pos: pos + N_FFT] * win)
        mag, phase = np.abs(spec), np.angle(spec)
        if prev_phase is None:
            phase_out = phase.copy()
        else:
            step = pos - prev_pos
            d = phase - prev_phase - omega * step
            d -= 2 * np.pi * np.round(d / (2 * np.pi))                 # הסטייה מהתדר הנומינלי
            freq = omega + d / max(step, 1)
            # שיאים בספקטרום: כל שיא מתקדם לפי התדר האמיתי שלו, ושכניו נעולים אליו - הצליל נשאר 'חד'
            pk = np.where((mag[2:-2] > mag[1:-3]) & (mag[2:-2] > mag[3:-1]) &
                          (mag[2:-2] > mag[:-4]) & (mag[2:-2] > mag[4:]))[0] + 2
            if len(pk):
                edges = (pk[:-1] + pk[1:]) // 2 + 1
                owner = pk[np.searchsorted(edges, bins, side="right")]
                new_pk = phase_out[owner] + freq[owner] * HOP_OUT
                phase_out = new_pk + (phase - phase[owner])
            else:
                phase_out = phase_out + freq * HOP_OUT
        prev_phase, prev_pos = phase, pos
        frame = np.fft.irfft(mag * np.exp(1j * phase_out)) * win
        o = k * HOP_OUT
        out[o: o + N_FFT] += frame
        norm[o: o + N_FFT] += win ** 2
        if progress and k % 200 == 0:
            progress(100.0 * k / n_frames)
    out /= np.maximum(norm, 1e-3)
    return out[N_FFT // 2:]


def change(audio, semitones=0, tempo=1.0, progress=None):
    """audio: מונו או (דגימות, 2). semitones: חצאי טונים למעלה (+) או למטה (-).
    tempo: 1.0 = כמו שהוא, 0.9 = איטי ב-10%, 1.1 = מהיר ב-10%. מחזיר באותו מבנה, float32."""
    x = np.asarray(audio, dtype=np.float32)
    if semitones == 0 and abs(tempo - 1.0) < 1e-6:
        return x.copy()
    f = 2 ** (semitones / 12.0)
    frac = Fraction(f).limit_denominator(400)                        # יחס הדגימה מחדש (קירוב מדויק מאוד)
    f = float(frac)
    rate = tempo / f                                                 # קודם מותחים בזמן, ואז 'מנגנים' מהר/לאט יותר
    chans = [x] if x.ndim == 1 else [x[:, c] for c in range(x.shape[1])]
    want = int(round(len(x) / tempo))
    outs = []
    for ci, ch in enumerate(chans):
        rep = (lambda p, ci=ci: progress((ci * 100 + p) / len(chans))) if progress else None
        y = _stretch_channel(ch, rate, rep) if abs(rate - 1.0) > 1e-6 else ch.astype(np.float64)
        if frac != 1:
            y = resample_poly(y, frac.denominator, frac.numerator)
        y = y[:want] if len(y) >= want else np.concatenate([y, np.zeros(want - len(y))])
        outs.append(y)
    out = outs[0] if x.ndim == 1 else np.stack(outs, axis=1)
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 0.98:
        out = out * (0.98 / peak)
    if progress:
        progress(100.0)
    return out.astype(np.float32)
