"""בדיקות לזיהוי בתנאים קשים: זמזום חשמל, שיר מהיר, וואלס."""
import numpy as np
import pytest

import synth_voice
from synth_voice import sing
from shir_studio.audio.fileio import SR
from shir_studio.audio.denoise import denoise, remove_hum, hum_frequencies
from shir_studio.music.analysis import analyze, double_time, detect_meter
from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles

quiet = lambda p, m=None: None
WALTZ = [(69, 2), (72, 1), (76, 2), (74, 1), (72, 3), (71, 2), (69, 1), (68, 2), (71, 1), (69, 3)] * 2


def melody(mel, **kw):
    old = synth_voice.MELODY
    synth_voice.MELODY = mel
    try:
        return sing(**kw)[0]
    finally:
        synth_voice.MELODY = old


@pytest.fixture(scope="module")
def voice():
    return sing(bpm=120, repeats=2)[0]


@pytest.fixture(scope="module")
def waltz():
    return melody(WALTZ, bpm=120, repeats=2)


def test_mains_hum_is_found_and_removed(voice):
    t = np.arange(len(voice)) / SR
    assert hum_frequencies(voice) == []                              # הקלטה נקייה - לא נוגעים בה
    clean, found = remove_hum(voice)
    assert found == [] and np.array_equal(clean, voice)
    for base, amps in ((50, (0.08, 0.0, 0.03)), (60, (0.05, 0.04, 0.02))):
        hum = sum(a * np.sin(2 * np.pi * base * (k + 1) * t) for k, a in enumerate(amps))
        noisy = (voice + hum).astype(np.float32)
        out, found = remove_hum(noisy)
        assert found and found[0] == base and all(f % base == 0 for f in found)
        left = np.std((out - voice)[SR:-SR]) / np.std(hum)
        assert left < 0.02, "הזמזום לא הוסר"                           # נשאר פחות מ-2% (35dB-)
        a = analyze(denoise(noisy))
        assert (a.tonic, a.mode) == (9, "minor")                       # הסולם מזוהה נכון למרות הזמזום


def test_fast_song_is_not_taken_at_half_speed():
    for bpm in (168, 184):
        a = analyze(sing(bpm=bpm, repeats=2)[0])
        assert abs(a.tempo - bpm) < 6, f"שיר ב-{bpm} זוהה כ-{a.tempo:.0f}"
    for bpm in (66, 84, 96):                                           # שירים איטיים באמת נשארים איטיים
        a = analyze(sing(bpm=bpm, repeats=2)[0])
        assert abs(a.tempo - bpm) < 4
    b = 0.5 + 0.7 * np.arange(20)
    on_beats = b[:16]
    assert len(double_time(b, 85.7, on_beats)[0]) == len(b)            # שרים רק על הפעמות - לא מכפילים
    between = np.sort(np.concatenate([b[:16], b[:16] + 0.35]))
    nb, tempo = double_time(b, 85.7, between)
    assert len(nb) == 2 * len(b) - 1 and abs(tempo - 171.4) < 0.1


def test_waltz_is_detected(voice, waltz):
    assert analyze(waltz).auto["meter"] == 3
    assert analyze(voice).auto["meter"] == 4
    for bpm in (84, 150):
        assert analyze(sing(bpm=bpm, repeats=2)[0]).auto["meter"] == 4
    assert analyze(melody(WALTZ, bpm=150, repeats=2)).auto["meter"] == 3
    assert detect_meter(np.arange(10.0), [], []) == 4                  # מעט מדי מידע - משקל רגיל


def test_waltz_song_gets_three_four_unless_user_decides(waltz, voice):
    style = load_styles()[1]
    song = Song(waltz)
    out = song.make(style, quiet, Settings())
    assert song.analysis.meter == 3 and song.analysis.auto_waltz and np.isfinite(out).all()
    song.make(style, quiet, Settings(auto_meter=False))                # המשתמש בחר 4/4 במפורש
    assert song.analysis.meter == 4 and not song.analysis.auto_waltz
    song.make(style, quiet, Settings(meter=6))
    assert song.analysis.compound and not song.analysis.auto_waltz
    regular = Song(voice)
    regular.make(style, quiet, Settings())
    assert regular.analysis.meter == 4 and not regular.analysis.auto_waltz


def test_meter_choice_in_advanced_dialog(qapp):
    from shir_studio.advanced import AdvancedDialog
    dlg = AdvancedDialog(None, Settings())
    assert dlg.meter.currentData() == 0                                # ברירת המחדל: אוטומטי
    st = dlg.settings()
    assert st.meter == 4 and st.auto_meter
    dlg.meter.setCurrentIndex(dlg.meter.findData(4))
    st = dlg.settings()
    assert st.meter == 4 and not st.auto_meter
    again = AdvancedDialog(None, st)
    assert again.meter.currentData() == 4                              # הבחירה המפורשת נשמרת
    dlg.meter.setCurrentIndex(dlg.meter.findData(3))
    assert dlg.settings().meter == 3
