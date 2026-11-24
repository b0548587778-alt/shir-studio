"""בדיקות לסינכרון הליווי עם הזמר, לפתיח, לסיום ולקבוצת כלי הנשיפה."""
import numpy as np
import pytest

import synth_voice
from synth_voice import sing
from shir_studio.audio.fileio import SR
from shir_studio.music import arrange, sampler
from shir_studio.music.analysis import analyze, refine_beats
from shir_studio.music.arrange import render, Timeline, brass_voice, third_below
from shir_studio.music.styles import load_styles
from shir_studio.music.theory import scale_pcs


def drifting_singer(bpm0=110, drift=0.0, jitter=0.0, seed=0, repeats=2):
    """זמר שהקצב שלו משתנה לאט לאורך השיר (drift), עם אי-דיוק קטן בכל צליל. מחזיר (קול, זמני הפעמות)."""
    rng = np.random.default_rng(seed)
    seq = synth_voice.MELODY * repeats
    nb = sum(b for _, b in seq)
    periods = 60 / bpm0 / (1 + drift * np.arange(nb + 1) / nb)
    bt = 0.5 + np.concatenate([[0], np.cumsum(periods)])
    n = int((bt[-1] + 1.0) * SR)
    f, amp = np.zeros(n), np.zeros(n)
    pos = 0
    for m, b in seq:
        a, e = int((bt[pos] + rng.normal(0, jitter)) * SR), int((bt[pos] + (bt[pos + b] - bt[pos]) * 0.92) * SR)
        tt = np.arange(e - a) / SR
        f[a:e] = 440 * 2 ** ((m + rng.uniform(-.2, .2) - 69) / 12)
        amp[a:e] = np.minimum(1, tt / 0.04) * np.minimum(1, tt[::-1] / 0.05)
        pos += b
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.zeros(n)
    for k in range(1, 20):
        fk = k * f
        g = np.exp(-((fk - 750) / 250) ** 2) + 0.6 * np.exp(-((fk - 1150) / 300) ** 2) + 0.03
        x += np.where(fk < 16000, g / k ** 0.7, 0) * np.sin(k * ph)
    x = x * amp
    x = x / np.abs(x).max() * 0.5 + 0.004 * rng.standard_normal(n)
    return x.astype(np.float32), bt[:nb + 1]


def beat_errors(a, truth):
    b = np.asarray(a.beats)
    grid = np.sort(np.concatenate([b, (b[:-1] + b[1:]) / 2]))
    tr = truth[(truth > b[0]) & (truth < b[-1])]
    return np.array([grid[np.argmin(np.abs(grid - t))] - t for t in tr]) - 0.012     # הרגע שבו הצליל נשמע


@pytest.mark.parametrize("drift", [0.0, 0.10, -0.06])
def test_beats_follow_a_singer_who_speeds_up(drift):
    x, truth = drifting_singer(drift=drift)
    a = analyze(x)
    assert a.steady
    d = beat_errors(a, truth)
    assert np.sqrt(np.mean(d ** 2)) < 0.012, "הפעמות רחוקות מהזמר"
    assert np.max(np.abs(d)) < 0.045
    assert abs(np.mean(d)) < 0.006                       # בלי איחור או הקדמה קבועים


def test_refine_keeps_grid_when_nothing_to_learn():
    b = 0.5 + 0.5 * np.arange(20)
    assert np.allclose(refine_beats(b, []), b)
    out = refine_beats(b, b + 0.03)                      # כל הצלילים 30 אלפיות אחרי הרשת - הרשת זזה אליהם
    assert np.allclose(out, b + 0.03, atol=0.004)
    assert np.all(np.diff(refine_beats(b, b + np.random.default_rng(0).normal(0, 0.05, 20))) > 0.2)


@pytest.fixture(scope="module")
def song():
    x, _ = sing(bpm=120, repeats=3)
    return analyze(x)


def _style(name):
    return next(s for s in load_styles() if s["name"] == name)


def _track(tracks, inst=None, **flag):
    for spec, buf, events in tracks:
        if (inst is None or spec["instrument"] == inst) and all(spec.get(k) == v for k, v in flag.items()):
            return spec, buf, events
    return None


def test_intro_builds_up_and_invites_the_singer(song):
    a = song
    tracks, lead = render(a, _style("חסידי קצבי"))
    tl = Timeline(a, intro_bars=6)
    sing0 = tl.beat_time(tl.bar0 + 6 * tl.meter)
    dominant = (a.tonic + 7) % 12
    # בפעמה האחרונה לפני הכניסה האקורדיון מנגן את הדרגה החמישית (עם ספטימה) - 'מזמין' את הזמר
    v7 = {dominant, (dominant + 4) % 12, (dominant + 7) % 12, (dominant + 10) % 12}
    acc = _track(tracks, "accordion")[2]
    last_beat = [m for t, m, d, v in acc if sing0 - tl.period * 1.0 < t < sing0 - 0.05]
    assert last_beat and all(m % 12 in v7 for m in last_beat)
    bass = _track(tracks, "bass")[2]
    # הפתיח מתחזק: התחלה רכה, סוף חזק
    intro = [(t, v) for t, m, d, v in bass if t < sing0 - tl.period]
    early = np.mean([v for t, v in intro[: len(intro) // 3]])
    late = np.mean([v for t, v in intro[-len(intro) // 3:]])
    assert late > early + 0.05
    # קול שני בטרצה בחצי השני של הפתיח
    solo = _track(tracks, solo=True)[2]
    mel = [(round(t, 1), m) for t, m, d, v in solo if t < sing0]
    half = sing0 - 2 * tl.period * tl.meter
    pairs = {t for t, m in mel if sum(1 for t2, _ in mel if abs(t2 - t) < 0.06) == 2}
    assert pairs and all(t >= half - 0.3 for t in pairs)
    scale = set(scale_pcs(a.tonic, a.mode))
    assert third_below(72, {0, 2, 4, 5, 7, 9, 11}) == 69 and all(
        m % 12 in scale for t, m in mel if t in pairs)


def test_ending_roll_final_chord_and_held_lead(song):
    a = song
    tracks, lead = render(a, _style("חסידי קצבי"))
    drums = _track(tracks, "drums")[2]
    t_final = max(t for t, n, d, v in drums if n == "crash")
    roll = [(t, v) for t, n, d, v in drums if n == "snare" and t_final - 0.9 < t < t_final - 0.01]
    assert len(roll) >= 5 and roll[-1][1] > roll[0][1] + 0.25           # גלגול שמתגבר אל תוך אקורד הסיום
    bass = [m for t, m, d, v in _track(tracks, "bass")[2] if abs(t - t_final) < 0.2]
    assert len(bass) >= 2 and max(bass) - min(bass) >= 12                # הבס מסיים גם באוקטבה הנמוכה
    solo = _track(tracks, solo=True)[2]
    held = [(m, d) for t, m, d, v in solo if abs(t - t_final) < 0.2]
    assert held and held[0][0] % 12 == a.tonic and held[0][1] > 1.5      # הכלי המוביל מחזיק את הטוניקה
    # פסנתר פורט את אקורד הסיום מלמטה למעלה
    tracks2, _ = render(a, _style("ניגון שקט עם פסנתר"))
    piano = _track(tracks2, "piano")[2]
    tf = max(t for t, m, d, v in piano) - 0.2
    fin = sorted((t, m) for t, m, d, v in piano if t > tf)
    assert len(fin) >= 3 and [m for _, m in fin] == sorted(m for _, m in fin) and fin[-1][0] - fin[0][0] > 0.05


def test_brass_section(song):
    a = song
    assert brass_voice("brass", 70) == "trumpet" and brass_voice("brass", 55) == "brass"
    assert brass_voice("trumpet", 48) == "brass" and brass_voice("piano", 90) == "piano"
    tracks, _ = render(a, _style("חסידי קצבי"))
    hits = _track(tracks, hits=True)
    assert hits is not None and len(hits[2]) >= 4
    tl = Timeline(a, intro_bars=6)
    sing0 = tl.beat_time(tl.bar0 + 6 * tl.meter)
    assert min(t for t, *_ in hits[2]) > sing0                           # לא בפתיח - רק מהפזמון
    assert all(52 <= m <= 84 for t, m, d, v in hits[2])                   # במנעד של החצוצרה
    assert np.isfinite(hits[1]).all() and np.abs(hits[1]).max() > 0.01
    assert _track(render(a, _style("ניגון שקט עם פסנתר"))[0], hits=True) is None       # בלי נשיפה - בלי דקירות
    assert _track(render(a, dict(_style("חסידי קצבי"), brass_hits=False))[0], hits=True) is None


def test_all_styles_still_render_with_new_arrangement(song):
    for st in load_styles():
        tracks, lead = render(song, st)
        assert tracks and all(np.isfinite(buf).all() for _, buf, _ in tracks), st["name"]
