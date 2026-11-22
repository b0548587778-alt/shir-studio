import numpy as np
from synth_voice import sing
from shir_studio.pipeline import Song
from shir_studio.music.styles import load_styles
from shir_studio.music import sampler, synth
from shir_studio.music.arrange import voice_lead, sections, Timeline

quiet = lambda p, m=None: None


def test_velocity_layers_and_drum_variation():
    assert sampler.available() and "kit" in sampler._meta
    soft = sampler._region("piano", 60, 0.2)
    loud = sampler._region("piano", 60, 0.95)
    assert soft["key"] != loud["key"]                 # דגימה שונה לנגינה רכה וחזקה
    a, b = sampler.drum("snare", 0.8, 0), sampler.drum("snare", 0.8, 1)
    assert not np.array_equal(a[:2000], b[:2000])     # שתי מכות לא זהות
    assert synth.has_drum("tom_hi")


def test_voice_leading_moves_little():
    c = [60, 64, 67]                                  # דו מז'ור
    f = voice_lead([65, 69, 72], c)                   # פה מז'ור -> היפוך קרוב
    assert sum(min(abs(n - q) for q in c) for n in f) <= 4


def test_song_has_sections_and_solo():
    x, _ = sing(bpm=112, repeats=3)
    s = Song(x)
    y = s.make(load_styles()[0], quiet)
    a = s.analysis
    lv = sections(a, Timeline(a), max(n.end for n in a.notes))
    assert lv[0] == 0 and lv[-1] == 1
    assert any(t[0].get("solo") for t in s.last_tracks)
    assert np.isfinite(y).all() and np.abs(y).max() <= 0.9
