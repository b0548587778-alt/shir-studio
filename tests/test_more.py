"""בדיקות: פתיח וסיום בקצב חופשי, ריצות הבס, ליווי מהיר/איטי פי שניים, ופרטי השיר בעיבוד ברצף."""
import os
import numpy as np
import pytest

from synth_voice import sing
from shir_studio.audio.fileio import SR, save
from shir_studio.music.analysis import analyze, apply_settings
from shir_studio.music.arrange import render, free_plan, step_below, Timeline, PHRASE
from shir_studio.music.styles import load_styles
from shir_studio.music.theory import chords_for, scale_pcs
from shir_studio.pipeline import Song, Settings
from shir_studio import tags
from shir_studio.project import batch

quiet = lambda p, m=None: None


@pytest.fixture(scope="module")
def voice():
    return sing(bpm=120, repeats=3)[0]


@pytest.fixture(scope="module")
def free_song(voice):
    a = analyze(voice)
    apply_settings(a, Settings(tempo_mode="free"))
    return a


def _style(name):
    return next(s for s in load_styles() if s["name"] == name)


def test_free_tempo_intro_and_ending(free_song):
    a = free_song
    assert not a.steady
    tonic = chords_for(a.tonic, a.mode)[0]
    plan = free_plan(a, _style("ניגון שקט עם פסנתר"), tonic)
    first = min(nt.start for nt in a.notes)
    last = max(nt.end for nt in a.notes)
    intro = [n for n in plan["notes"] if n[0] < first]
    echo = [n for n in plan["notes"] if n[0] >= last]
    assert len(intro) >= 3 and len(echo) >= 2                       # מנגינה לפני הזמר, ותשובה אחריו
    assert max(t + d for t, d, m, v in intro) < first - 0.3          # הפתיח נגמר לפני שהזמר נכנס
    assert plan["lead"] > 2.5 and plan["final"][0] > max(t + d for t, d, m, v in echo) - 0.2
    scale = set(scale_pcs(a.tonic, a.mode))
    assert all(m % 12 in scale for t, d, m, v in plan["notes"])
    segs = plan["segs"]
    assert all(e > s for s, e, c in segs) and segs[-1][2]["root"] == a.tonic
    # האקורד שלפני הכניסה 'מזמין' (דרגה חמישית) כשהשיר מתחיל בטוניקה
    before = [c for s, e, c in segs if s < first - 0.1 <= e][0]
    if a.chords[0][2]["root"] == a.tonic:
        assert before["root"] == (a.tonic + 7) % 12 and before.get("seventh") == 10
    tracks, lead = render(a, _style("ניגון שקט עם פסנתר"))
    assert lead == plan["lead"]
    solo = [ev for spec, buf, ev in tracks if spec.get("solo")][0]
    assert len(solo) == len(plan["notes"]) + 1                       # + הטוניקה עם אקורד הסיום
    # סגנון ווקאלי: בלי כלי מוביל - נשאר פתיח קצר
    vocal = free_plan(a, _style("ווקאלי - בלי כלים"), tonic)
    assert vocal["notes"] == [] and vocal["lead"] == 1.5
    for st in load_styles():
        tr, _ = render(a, st)
        assert all(np.isfinite(buf).all() for _, buf, _ in tr), st["name"]


def test_bass_runs_into_next_phrase(voice):
    a = analyze(voice)
    style = _style("חסידי קצבי")
    tracks, lead = render(a, style)
    bass = sorted([ev for spec, buf, ev in tracks if spec["instrument"] == "bass"][0])
    tl = Timeline(a, intro_bars=6)
    scale = set(scale_pcs(a.tonic, a.mode))
    runs = 0
    for ph in range(1, 3):
        t_next = tl.beat_time(tl.bar0 + (6 + ph * PHRASE) * tl.meter)          # תחילת המשפט הבא
        pair = [(t, m) for t, m, d, v in bass if t_next - tl.period * 1.1 < t < t_next - 0.05]
        target = [m for t, m, d, v in bass if abs(t - t_next) < 0.08]
        if len(pair) == 2 and target:
            runs += 1
            assert pair[0][1] < pair[1][1] and all(m % 12 in scale for _, m in pair)   # עולים בצלילי הסולם
            assert 0 < target[0] - pair[1][1] <= 2 or target[0] - pair[1][1] in (-10, -11)
    assert runs >= 1
    assert step_below(60, {0, 2, 4, 5, 7, 9, 11}) == 59 and step_below(65, {0, 2, 4, 5, 7, 9, 11}) == 64
    plain = sorted([ev for spec, buf, ev in render(a, dict(style, bass_runs=False))[0]
                    if spec["instrument"] == "bass"][0])
    assert len(plain) < len(bass)


def test_accompaniment_twice_as_fast_or_slow(voice):
    a = analyze(voice)
    apply_settings(a, Settings())
    n, tempo = len(a.beats), a.tempo
    apply_settings(a, Settings(tempo_scale=2.0))
    assert len(a.beats) == 2 * n - 1 and abs(a.tempo - 2 * tempo) < 0.1
    apply_settings(a, Settings(tempo_scale=0.5))
    assert abs(len(a.beats) - n / 2) <= 1 and abs(a.tempo - tempo / 2) < 0.1
    assert np.all(np.diff(a.beats) > 0)
    apply_settings(a, Settings())
    assert len(a.beats) == n                                         # חוזרים לקצב שזוהה


def test_batch_writes_song_details(tmp_path, voice):
    src = str(tmp_path / "ניגון ראשון.wav")
    save(src, voice[: 12 * SR])
    res = batch([src], load_styles()[1], Settings(), str(tmp_path), "mp3", artist="יוסף כהן")
    assert res[0][1] and res[0][2] is None
    got = tags.read(res[0][1])
    assert got["title"] == "ניגון ראשון" and got["artist"] == "יוסף כהן"


def test_tempo_buttons_on_done_screen(qapp, appdata, fake_sd, monkeypatch, tmp_path, voice):
    from shir_studio.ui import MainWindow
    from shir_studio import recovery
    errors = []
    monkeypatch.setattr(MainWindow, "error", lambda self, t: errors.append(t))
    monkeypatch.setattr(MainWindow, "_ask", lambda self, *a: False)
    monkeypatch.setattr(MainWindow, "_info", lambda self, *a: None)
    w = MainWindow()
    try:
        import time
        def wait(cond, timeout=180):
            t0 = time.time()
            while not cond():
                qapp.processEvents(); time.sleep(0.01)
                assert time.time() - t0 < timeout
        w._set_raw(voice[: 20 * SR])
        w.make_song()
        wait(lambda: w.stack.currentWidget() is w.done)
        tempo = w.song.analysis.tempo
        w.done.b_slower.click()
        wait(lambda: w.stack.currentWidget() is w.done and w.settings.tempo_scale == 0.5 and w.worker is None or
             (w.stack.currentWidget() is w.done and abs(w.song.analysis.tempo - tempo / 2) < 1))
        assert abs(w.song.analysis.tempo - tempo / 2) < 1 and not errors
        w.undo()                                                     # ביטול מחזיר את הקצב הקודם
        wait(lambda: w.stack.currentWidget() is w.done and abs(w.song.analysis.tempo - tempo) < 1)
        w.settings.tempo_scale = 2.0
        w.song.analysis.tempo = 200.0
        w.scale_tempo(2.0)                                           # מהיר מדי - הודעה ולא שינוי
        assert errors and w.settings.tempo_scale == 2.0
    finally:
        w.dirty = False
        w.close()
        recovery.clear()
