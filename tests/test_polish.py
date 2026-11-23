"""בדיקות לליטוש הקול, לעוצמה לפי התקן, ולפרטי השיר בקובץ."""
import numpy as np
import pytest

from synth_voice import sing
from shir_studio.audio.fileio import SR, save, load
from shir_studio.audio import polish, loudness
from shir_studio.audio.mix import limiter, rms
from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles
from shir_studio import tags

quiet = lambda p, m=None: None


@pytest.fixture(scope="module")
def voice():
    return sing(bpm=120, repeats=1)[0]


def test_lufs_matches_the_standard():
    t = np.arange(SR * 5) / SR
    x = 0.1 * np.sin(2 * np.pi * 997 * t)
    assert abs(loudness.lufs(np.stack([x, x], axis=1)) - (-20.0)) < 0.2      # שני ערוצים: -20 LUFS
    assert abs(loudness.lufs(x) - (-23.0)) < 0.2                            # ערוץ אחד: 3 פחות
    assert loudness.lufs(np.zeros((SR, 2), np.float32)) == float("-inf")


def test_true_peak_sees_between_samples():
    t = np.arange(SR) / SR
    x = np.sin(2 * np.pi * (SR / 4) * t + np.pi / 4)          # הדגימות נופלות על 0.707, השיא האמיתי 1.0
    assert np.max(np.abs(x)) < 0.72
    assert loudness.true_peak(x) > 0.97


def test_finalize_reaches_target_and_safe_peak(voice):
    st = np.stack([voice, voice], axis=1) * 0.2
    for name, goal in loudness.TARGETS.items():
        out, g = loudness.finalize(st, name, limiter)
        assert abs(loudness.lufs(out) - goal) < 1.0, name
        assert loudness.true_peak(out) <= 10 ** (loudness.PEAK_DB / 20) + 1e-3
        assert g > 0


def test_declick_removes_clicks_and_keeps_singing(voice):
    v = voice.copy()
    spots = [int(SR * s) for s in (1.0, 2.3, 3.7, 5.1)]
    for s in spots:
        v[s] += 0.6
        v[s + 1] -= 0.5
    out, n = polish.declick(v)
    assert n >= len(spots)
    for s in spots:
        assert np.max(np.abs(out[s - 3:s + 4] - voice[s - 3:s + 4])) < 0.12
    clean, n0 = polish.declick(voice)
    assert n0 <= 2 and rms(clean - voice) < 0.002           # שירה נקייה לא נפגעת


def test_deplosive_softens_pops_only(voice):
    v = voice.copy()
    t = np.arange(int(0.06 * SR)) / SR
    pop = 0.8 * np.sin(2 * np.pi * 55 * t) * np.exp(-t / 0.02)
    a = int(0.1 * SR)                                        # בשקט שלפני השירה - כמו פ' בתחילת מילה
    v[a:a + len(pop)] += pop
    out = polish.deplosive(v)
    assert rms(out[a:a + len(pop)]) < 0.6 * rms(v[a:a + len(pop)])
    same = polish.deplosive(voice)
    assert rms(same - voice) < 0.1 * rms(voice)


def test_voice_tone_changes_colour(voice):
    def bright(x):
        spec = np.abs(np.fft.rfft(x))
        f = np.fft.rfftfreq(len(x), 1 / SR)
        return spec[f > 4000].sum() / spec[f < 1000].sum()
    assert bright(polish.tone(voice, "bright")) > bright(voice) > bright(polish.tone(voice, "warm"))
    assert polish.tone(voice, "natural") is voice
    assert np.isfinite(polish.tone(voice, "radio")).all()


def test_song_options_loudness_space_tone(voice):
    style = load_styles()[1]
    song = Song(voice)
    normal = song.make(style, quiet, Settings())
    assert abs(loudness.lufs(normal) - (-14.0)) < 1.0
    loud = song.make(style, quiet, Settings(loudness="loud", voice_tone="bright"))
    assert loudness.lufs(loud) > loudness.lufs(normal) + 1.5
    assert loudness.true_peak(loud) <= 10 ** (loudness.PEAK_DB / 20) + 1e-3
    small = song.make(style, quiet, Settings(space="room", reverb=200))
    big = song.make(style, quiet, Settings(space="big", reverb=200))
    assert len(big) >= len(small) and np.isfinite(big).all()


def test_mp3_carries_hebrew_title_and_artist(tmp_path, voice):
    p = str(tmp_path / "ניגון.mp3")
    save(p, np.stack([voice, voice], axis=1), tags={"title": "ניגון שמחה", "artist": "יוסף כהן", "year": "2026"})
    got = tags.read(p)
    assert got["title"] == "ניגון שמחה" and got["artist"] == "יוסף כהן" and got["year"] == "2026"
    assert abs(len(load(p)) - len(voice)) < SR * 0.2          # הקובץ עדיין נפתח כרגיל
    p2 = str(tmp_path / "בלי.mp3")
    save(p2, voice)
    assert tags.read(p2) == {}


def test_flac_roundtrip(tmp_path, voice):
    p = str(tmp_path / "שיר.flac")
    save(p, voice)
    back = load(p)
    assert len(back) == len(voice) and rms(back - voice) < 1e-3
