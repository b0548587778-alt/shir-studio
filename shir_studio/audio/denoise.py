"""ניקוי רעשי רקע בשיטת 'שער ספקטרלי' (Spectral gating) - כתוב כאן מאפס, ללא תלות ברישיונות נוספים."""
import numpy as np
from scipy.signal import stft, istft, butter, sosfiltfilt
from scipy.ndimage import uniform_filter

from .fileio import SR

NFFT = 2048
HOP = 512


def _highpass(x, cutoff=70.0):
    sos = butter(4, cutoff, btype="highpass", fs=SR, output="sos")
    return sosfiltfilt(sos, x).astype(np.float32)


def denoise(x: np.ndarray, strength: float = 1.0, progress=None) -> np.ndarray:
    """strength: 0 (בלי ניקוי) עד 1 (ניקוי מלא)."""
    x = _highpass(x)
    if progress:
        progress(10)
    _, _, Z = stft(x, fs=SR, nperseg=NFFT, noverlap=NFFT - HOP)
    mag = np.abs(Z)
    db = 20 * np.log10(mag + 1e-10)
    # פרופיל רעש: 15% מהפריימים השקטים ביותר
    frame_energy = np.mean(mag ** 2, axis=0)
    n_quiet = max(5, int(0.15 * len(frame_energy)))
    quiet = np.argsort(frame_energy)[:n_quiet]
    noise_mean = db[:, quiet].mean(axis=1, keepdims=True)
    noise_std = db[:, quiet].std(axis=1, keepdims=True)
    thresh = noise_mean + 1.5 * noise_std + 6.0
    if progress:
        progress(40)
    # מסכה רכה - מעבר הדרגתי ולא חד, כדי למנוע צלילים מתכתיים
    mask = 1.0 / (1.0 + np.exp(-(db - thresh) / 3.0))
    mask = uniform_filter(mask, size=(3, 5))
    floor = 10 ** (-(18.0 * strength) / 20)  # הנחתה מקסימלית של 18dB
    gain = floor + (1 - floor) * mask
    gain = 1 - strength * (1 - gain)
    if progress:
        progress(70)
    _, y = istft(Z * gain, fs=SR, nperseg=NFFT, noverlap=NFFT - HOP)
    y = y[: len(x)].astype(np.float32)
    if len(y) < len(x):
        y = np.pad(y, (0, len(x) - len(y)))
    if progress:
        progress(90)
    return normalize(y)


def normalize(y: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    peak = np.max(np.abs(y))
    if peak < 1e-6:
        return y
    return (y * (10 ** (peak_db / 20) / peak)).astype(np.float32)
