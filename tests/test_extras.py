"""בדיקות: סולם אדוני מלך, משקל 6/8, סגנון שקובע משקל, המלצת טרנספוזיציה והערכת הזמן שנשאר."""
import numpy as np
import pytest
from synth_voice import sing
from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles
from shir_studio.music import analysis, arrange, theory
from shir_studio.project import settings_to_dict, settings_from_dict

quiet = lambda p, m=None: None


def style(sid):
    return [s for s in load_styles() if s["id"] == sid][0]


@pytest.fixture(scope="module")
def song():
    x, _ = sing(bpm=120, repeats=2)
    s = Song(x)
    s.prepare(quiet)
    return s


def test_adonai_malach_mode():
    w = np.zeros(12)
    for step, d in zip(theory.MODES["adonai"][1], [6, 2, 4, 2.5, 5, 2, 4]):       # סול מיקסולידי
        w[(7 + step) % 12] = d
    t, m, _ = theory.rank_keys(w, final_pc=7)[0]
    assert (t, m) == (7, "adonai")
    assert 5 in theory.scale_pcs(7, "adonai") and 6 not in theory.scale_pcs(7, "adonai")   # פה ולא פה#
    assert {"I", "IV", "VII"} <= {c["degree"] for c in theory.chords_for(7, "adonai")}


def test_adonai_key_and_six_eight_render(song):
    st = Settings(key=(9, "adonai"), meter=6, tempo_mode="manual", bpm=60)
    y = song.make(style("01_hasidi"), quiet, st)
    a = song.analysis
    assert a.mode == "adonai" and a.compound and a.meter == 2
    assert y.ndim == 2 and np.isfinite(y).all()
    # בתיבה של 6/8 התופים נופלים על שלישי הפעמה, ולא על חצי הפעמה
    frac = []
    for spec, _, ev in song.last_tracks:
        if spec["instrument"] == "drums":
            frac += [((t - song.last_lead - a.beats[0]) / 1.0) % 1 for t, *_ in ev]
    frac = np.array(frac)
    near = lambda f: np.minimum(np.abs(frac - f), 1 - np.abs(frac - f)) < 0.06
    assert len(frac) > 20 and np.mean(near(0) | near(1 / 3) | near(2 / 3)) > 0.9
    assert np.mean(near(0.5)) < 0.05
    back = settings_from_dict(settings_to_dict(st))
    assert back.meter == 6 and back.key == (9, "adonai")


def test_to_compound_mapping():
    bar = [{"t": 0, "n": "a"}, {"t": 0.5, "n": "x"}, {"t": 1, "n": "b"}, {"t": 1.5, "n": "c"},
           {"t": 2, "n": "d"}, {"t": 3, "n": "e"}, {"t": 3.5, "n": "f"}]
    out = {e["n"]: round(e["t"], 3) for e in arrange.to_compound(bar)}
    assert out == {"a": 0, "b": 0.333, "c": 0.667, "d": 1, "e": 1.333, "f": 1.667}


def test_style_sets_its_meter_and_new_styles_exist(song):
    assert {"14_waltz", "15_hora", "16_dveikut", "17_six8"} <= {s["id"] for s in load_styles()}
    song.make(style("14_waltz"), quiet, Settings())
    assert song.analysis.meter == 3
    song.make(style("17_six8"), quiet, Settings())
    assert song.analysis.compound
    song.make(style("14_waltz"), quiet, Settings(meter=6))     # בחירה ידנית של המשתמש גוברת
    assert song.analysis.compound
    song.make(style("15_hora"), quiet, Settings())
    assert song.analysis.meter == 4 and not song.analysis.compound
    y = song.preview(style("17_six8"), quiet, Settings(), seconds=10)
    assert np.isfinite(y).all()


def test_vocal_range_and_transpose_suggestion(song):
    song.make(style("02_piano"), quiet, Settings())
    lo, hi, mid = analysis.vocal_range(song.analysis)
    assert 67 <= lo <= 70 and 75 <= hi <= 78 and lo < mid < hi
    assert -4 <= analysis.suggest_transpose(song.analysis) < 0      # שירה גבוהה מאוד - מומלץ להוריד
    v = song.info()["voice"]
    assert v["suggest"] < 0 and v["low"] and v["high"]
    from scipy.signal import resample_poly
    low, _ = sing(bpm=120, repeats=1)
    s2 = Song(resample_poly(low, 3, 2).astype(np.float32))          # אותה מנגינה חמישית נמוך יותר
    s2.prepare(quiet)
    assert abs(analysis.suggest_transpose(s2.analysis)) < abs(analysis.suggest_transpose(song.analysis))


def test_advanced_dialog_new_options(qapp, song):
    from shir_studio.advanced import AdvancedDialog
    song.make(style("02_piano"), quiet, Settings())
    st = Settings(meter=6, key=(0, "adonai"))
    dlg = AdvancedDialog(None, st, song.info(), style=load_styles()[0])
    out = dlg.settings()
    assert out.meter == 6 and out.key == (0, "adonai")
    dlg.meter.setCurrentIndex(dlg.meter.findData(3))
    assert dlg.settings().meter == 3
    dlg.grab()


def test_time_left_estimate(qapp):
    from shir_studio.screens.work import WorkScreen, eta_text
    assert eta_text(1, 50) == "" and eta_text(10, 3) == ""
    assert eta_text(10, 50) == "נשארו בערך 10 שניות"
    assert eta_text(60, 50) == "נשארה בערך דקה"
    assert eta_text(60, 20) == "נשארו בערך 4 דקות"
    assert eta_text(30, 95) == "עוד רגע..."
    w = WorkScreen()
    w.begin()
    w._t0 -= 40
    w.set_progress(35)
    assert w.bar.value() == 35 and "דקה" in w.eta.text()
    w.begin()
    assert w.eta.text() == "" and w.bar.value() == 0
