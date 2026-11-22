import numpy as np
from synth_voice import sing
from shir_studio.pipeline import Song
from shir_studio.music.styles import load_styles
from shir_studio.audio.pitch import yin, hz_to_midi


def test_key_tempo_and_all_styles():
    x, truth = sing(bpm=120, detune=0.25, drift=-0.3, repeats=1)
    s = Song(x)
    s.prepare(lambda p, m=None: None)
    info = s.info()
    assert info["steady"] and abs(info["tempo"] - 120) < 3
    a = s.analysis
    assert (a.tonic, a.mode) == (9, "minor")         # לה מינור
    styles = load_styles()
    assert len(styles) == 10
    for st in styles:
        y = s.make(st, lambda p, m=None: None)
        assert y.ndim == 2 and np.isfinite(y).all() and np.abs(y).max() <= 0.9


def test_pitch_correction_reduces_out_of_tune():
    x, truth = sing(bpm=110, wobble=0.25, detune=0.3, repeats=2)
    s = Song(x)
    s.prepare(lambda p, m=None: None)
    from shir_studio.pipeline import Settings
    s._retune(Settings())
    f1, _ = yin(s.tuned)

    def spread(f):
        m = hz_to_midi(f)
        e = []
        for t0, mm, _ in truth:
            k = int((t0 + 0.15) / 0.01)
            seg = m[k:k + 20][f[k:k + 20] > 0]
            if len(seg):
                e.append(np.median(seg) - mm)
        e = np.array(e)
        return np.std(e - np.median(e))
    assert spread(f1) < 0.5 * spread(s.analysis.f0)


def test_free_tempo_is_detected():
    import synth_voice
    rng = np.random.default_rng(5)
    old = synth_voice.MELODY
    synth_voice.MELODY = [(m, b * rng.uniform(0.5, 2.2)) for m, b in old]
    try:
        x, _ = synth_voice.sing(bpm=80, repeats=1)
    finally:
        synth_voice.MELODY = old
    s = Song(x)
    s.prepare(lambda p, m=None: None)
    assert not s.info()["steady"]
