import os
import numpy as np
from synth_voice import sing
from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles, apply_swaps, instruments_of
from shir_studio.music.theory import rank_keys, MODES, scale_pcs
from shir_studio.audio.mix import deess, gate, master, choir_copies
from shir_studio.audio.denoise import denoise
from shir_studio.audio.devices import click_track
from shir_studio.audio.fileio import SR
from shir_studio.project import save_project, load_project, History, batch

quiet = lambda p, m=None: None


def _song():
    x, _ = sing(bpm=120, repeats=1)
    s = Song(x)
    s.prepare(quiet)
    return s


def test_three_voices_choir_and_swaps():
    s = _song()
    st = load_styles()[0]
    inst = instruments_of(st)[0]
    cfg = Settings(harmony="three", choir=True, swaps={inst: "violin"})
    y = s.make(st, quiet, cfg)
    assert isinstance(s.harmony, list) and len(s.harmony) == 2
    assert y.ndim == 2 and np.isfinite(y).all() and np.abs(y).max() <= 0.9
    sw = apply_swaps(st, cfg.swaps)
    assert inst not in instruments_of(sw) and inst in instruments_of(st)   # המקור לא השתנה


def test_new_styles_present():
    names = {s["id"] for s in load_styles()}
    assert {"08_mizrahi", "09_chabad_slow", "10_march"} <= names


def test_misheberach_mode_detected_when_clear():
    w = np.full(12, 0.2)
    for d in MODES["misheberach"][1]:
        w[(2 + d) % 12] = 1.0
    w[2] = 2.0
    t, m, _ = rank_keys(w, final_pc=2)[0]
    assert (t, m) == (2, "misheberach")
    assert scale_pcs(2, "misheberach") == sorted({(2 + d) % 12 for d in [0, 2, 3, 6, 7, 9, 10]})


def test_deesser_reduces_sibilance_and_gate_quiets_noise():
    rng = np.random.default_rng(0)
    t = np.arange(SR) / SR
    hiss = rng.standard_normal(SR) * 0.3
    from scipy.signal import butter, sosfilt
    hiss = sosfilt(butter(4, 7000, btype="high", fs=SR, output="sos"), hiss)
    v = np.concatenate([0.3 * np.sin(2 * np.pi * 220 * t), hiss])
    out = deess(v)
    assert np.std(out[SR:]) < 0.8 * np.std(v[SR:])
    assert np.std(out[:SR]) > 0.9 * np.std(v[:SR])
    nz = np.concatenate([0.5 * np.sin(2 * np.pi * 220 * t), 0.003 * rng.standard_normal(SR)])
    g = gate(nz)
    assert np.std(g[int(1.5 * SR):]) < 0.5 * np.std(nz[int(1.5 * SR):])


def test_master_hits_loudness_and_choir_is_stereo():
    rng = np.random.default_rng(1)
    x = rng.standard_normal((SR * 2, 2)) * 0.01
    y = master(x)
    assert np.isfinite(y).all() and np.sqrt(np.mean(y ** 2)) > 5 * np.sqrt(np.mean(x ** 2))
    v = np.zeros((SR, 2)); v[:, 0] = v[:, 1] = np.sin(2 * np.pi * 300 * np.arange(SR) / SR)
    c = choir_copies(v)
    assert not np.allclose(c[:, 0], c[:, 1])


def test_dereverb_keeps_signal():
    x, _ = sing(bpm=100, repeats=1)
    y = denoise(x)
    assert np.isfinite(y).all() and np.max(np.abs(y)) > 0.5


def test_project_roundtrip_and_history(tmp_path):
    raw = np.random.default_rng(2).standard_normal(1000).astype(np.float32)
    st = Settings(key=(2, "misheberach"), harmony="three", choir=True, swaps={"piano": "organ"})
    p = str(tmp_path / "שיר.shir")
    save_project(p, raw, st, "01_hasidi", {"key_index": 3})
    r, s2, sid, meta = load_project(p)
    assert np.array_equal(r, raw) and s2 == st and sid == "01_hasidi" and meta["key_index"] == 3
    h = History()
    h.push({"a": 1}); h.push({"a": 2}); h.push({"a": 3})
    assert h.undo() == {"a": 2} and h.undo() == {"a": 1} and h.undo() is None
    assert h.redo() == {"a": 2}
    h.push({"a": 9})
    assert not h.can_redo()


def test_batch_and_pitch_curves(tmp_path):
    x, _ = sing(bpm=120, repeats=1)
    saved = {}
    files = ["a.wav", "broken.wav"]

    def fake_load(p):
        if "broken" in p:
            raise ValueError("bad")
        return x
    res = batch(files, load_styles()[0], Settings(), str(tmp_path), "wav",
                load=fake_load, save=lambda p, d: saved.setdefault(p, d))
    assert res[0][1] and res[1][1] is None and len(saved) == 1
    s = _song()
    t, before, after, notes = s.pitch_curves()
    assert len(t) == len(before) == len(after) and notes


def test_click_track():
    c = click_track(120, 4, 2.0)
    assert len(c) == 2 * SR and np.abs(c).max() > 0.2


def test_metronome_stream_is_seamless(monkeypatch):
    """מדמה כרטיס קול: בודק שהמטרונום מנגן תקתוקים בקצב הנכון וברצף, גם בין קטעים."""
    import shir_studio.audio.devices as dev
    got = {}

    class FakeStream:
        def __init__(self, samplerate, channels, dtype, callback):
            got["cb"] = callback

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

    class FakeSD:
        OutputStream = FakeStream
    monkeypatch.setattr(dev, "_sd", lambda: FakeSD)
    m = dev.Metronome()
    m.start(120, 4)
    out = []
    for _ in range(200):                                  # 200 קטעים של 512 דגימות (כ-2.3 שניות)
        buf = np.zeros((512, 1), np.float32)
        got["cb"](buf, 512, None, None)
        out.append(buf[:, 0].copy())
    m.stop()
    y = np.concatenate(out)
    onsets = np.where((np.abs(y[1:]) > 0.05) & (np.abs(y[:-1]) <= 0.05))[0]
    starts = [onsets[0]] + [o for a, o in zip(onsets, onsets[1:]) if o - a > SR * 0.2]
    gaps = np.diff(starts) / SR
    assert len(starts) >= 4 and np.allclose(gaps, 0.5, atol=0.01)     # 120 BPM = תקתוק כל חצי שנייה
