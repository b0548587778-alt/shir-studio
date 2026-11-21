import numpy as np
from shir_studio.audio.denoise import denoise
from shir_studio.audio.fileio import SR, save, load


def make_voice(sec=6):
    t = np.arange(int(SR * sec)) / SR
    f0 = 220 * 2 ** (np.floor(t) % 4 / 12)  # "מנגינה" פשוטה
    phase = 2 * np.pi * np.cumsum(f0) / SR
    v = sum(np.sin(k * phase) / k for k in range(1, 8))
    env = ((t % 1) < 0.8).astype(float)  # הפסקות בין צלילים
    return (0.3 * v * env).astype(np.float32), env


def snr(clean, test):
    return 10 * np.log10(np.sum(clean ** 2) / np.sum((test - clean) ** 2))


def test_denoise_improves_snr(tmp_path):
    rng = np.random.default_rng(0)
    clean, env = make_voice()
    noisy = clean + 0.03 * rng.standard_normal(len(clean)).astype(np.float32)
    out = denoise(noisy)
    # מתאים עוצמה להשוואה הוגנת
    a = np.dot(out, clean) / np.dot(out, out)
    assert snr(clean, a * out) > snr(clean, noisy) + 3
    # בקטעי השקט הרעש ירד מאוד
    silent = env == 0
    assert np.std(a * out[silent]) < 0.3 * np.std(noisy[silent])
    p = tmp_path / "x.mp3"
    save(str(p), out)
    back = load(str(p))
    assert abs(len(back) - len(out)) < SR * 0.2
