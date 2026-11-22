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


def test_intro_counter_and_last_chorus():
    from shir_studio.pipeline import Settings
    import synth_voice
    old = synth_voice.MELODY
    # מנגינה עם נשימות בין המשפטים - שם נכנסות מנגינות הנגד
    synth_voice.MELODY = old[:6] + [(None, 3)] + old[6:12] + [(None, 3)] + old[12:18] + [(None, 3)] + old[18:]
    try:
        x, _ = sing(bpm=112, repeats=3)
    finally:
        synth_voice.MELODY = old
    s = Song(x)
    st = load_styles()[0]
    s.make(st, quiet)
    a = s.analysis
    first = min(n.start for n in a.notes)
    solo = [t for t in s.last_tracks if t[0].get("solo")][0]
    intro_notes = [e for e in solo[2] if e[0] < s.last_lead + first - 0.05]
    assert len(intro_notes) >= 4                           # כלי מנגן את המנגינה לפני הזמר
    assert any(t[0].get("counter") for t in s.last_tracks)  # מנגינות נגד בין המשפטים
    # עריכה ידנית של חלקי השיר
    auto = [p[2] for p in s.phrases()]
    manual = [1 - v for v in auto]
    s.make(st, quiet, Settings(sections=manual))
    from shir_studio.music.arrange import sections, Timeline
    assert sections(a, Timeline(a, intro_bars=6), max(n.end for n in a.notes)) == manual
    assert [p[2] for p in s.phrases()] == auto            # הניחוש האוטומטי לא השתנה


def test_rich_chords_and_parse_sevenths():
    from shir_studio.music.arrange import enrich, _note_for
    from shir_studio.music.theory import chords_for
    from shir_studio.music.analysis import parse_chord
    V = [c for c in chords_for(9, "minor") if c["degree"] == "V"][0]
    assert len(_note_for("chord", enrich(V, "minor"), 4)) == 4          # E7 בלה מינור
    i = chords_for(9, "minor")[0]
    assert len(_note_for("chord", enrich(i, "minor"), 4)) == 3
    assert len(_note_for("chord", enrich(i, "minor", rich=True), 4)) == 4
    assert parse_chord("E7")["seventh"] == 10 and parse_chord("Fmaj7")["seventh"] == 11
    assert parse_chord("Am")["seventh"] is None


def test_vocal_style_builds_choir_from_singer():
    x, _ = sing(bpm=112, repeats=1)
    s = Song(x)
    vocal = [st for st in load_styles() if st["id"] == "05_vocal"][0]
    y = s.make(vocal, quiet)
    assert isinstance(s.harmony, list) and len(s.harmony) == 2
    assert np.isfinite(y).all()


def test_new_orchestral_instruments_in_tune():
    from shir_studio.audio.pitch import yin, hz_to_midi
    for inst, m in (("violin", 67), ("strings", 64), ("trumpet", 67), ("flute", 74), ("cello", 50)):
        x = sampler.note(inst, m, 1.2, 0.8)
        f, _ = yin(x[11025:44100])
        assert abs(np.median(hz_to_midi(f[f > 0])) - m) < 0.3, inst
