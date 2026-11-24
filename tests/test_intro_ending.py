"""בדיקות לפתיח ולסיום: האקורדים שמתחת לסולו הסיום, סוגי הסיום (מלא, שלוש מכות, דעיכה, קצר),
סוגי הפתיח (מתחילת השיר, מהפזמון, ארוך, קצר), והבחירה שלהם בהגדרות."""
import numpy as np
import pytest

from synth_voice import sing
from shir_studio.audio.fileio import SR
from shir_studio.music import arrange
from shir_studio.music.analysis import analyze
from shir_studio.music.arrange import render, Timeline, sections, PHRASE, INTROS, ENDINGS
from shir_studio.music.styles import load_styles
from shir_studio.pipeline import Song, Settings

quiet = lambda p, m=None: None


@pytest.fixture(scope="module")
def song():
    x, _ = sing(bpm=120, repeats=3)
    return analyze(x)


def _style(name, **kw):
    return dict(next(s for s in load_styles() if s["name"] == name), **kw)


def _track(tracks, inst=None, **flag):
    for spec, buf, events in tracks:
        if (inst is None or spec["instrument"] == inst) and all(spec.get(k) == v for k, v in flag.items()):
            return spec, buf, events
    return None


def _last_voice(a):
    return max(nt.end for nt in a.notes)


def _final_time(tracks):
    return max(t for t, n, d, v in _track(tracks, "drums")[2] if n == "crash")


# ---------- הסיום ----------
def test_closing_solo_gets_the_chords_of_the_last_phrase(song):
    a = song
    tracks, lead = render(a, _style("חסידי קצבי", ritardando=False))
    lv, t_final = _last_voice(a), _final_time(tracks)
    tl = Timeline(a)
    bar = tl.period * tl.meter
    acc = _track(tracks, "accordion")[2]
    outro = [(t - lead, m % 12) for t, m, d, v in acc if lv + 0.4 < t - lead < t_final - lead - 0.1]
    tonic = {a.tonic, (a.tonic + 3) % 12, (a.tonic + 4) % 12, (a.tonic + 7) % 12}
    assert len(outro) > 8 and not {pc for _, pc in outro} <= tonic       # לא נשארים על אקורד אחד
    # בכל רגע של הסולו מנוגן האקורד שהיה שם כמה תיבות קודם, מתחת לאותה מנגינה
    _, solo_from = arrange.outro_melody(a, Timeline(a, intro_bars=6), lv)
    shift = int(np.ceil((lv - solo_from) / bar + 0.25)) * bar
    known = hits = 0
    for t, pc in outro:
        src = [c for s0, e0, c in a.chords if s0 - 0.05 <= t - shift < e0]
        known += bool(src)
        hits += bool(src) and pc in {(src[0]["root"] + k) % 12 for k in (0, 3, 4, 7, 10, 11)}
    assert known > 0.7 * len(outro) and hits >= 0.97 * known


def test_three_hits_ending(song):
    a = song
    tracks, lead = render(a, _style("חסידי קצבי", ending="hits"))
    drums = _track(tracks, "drums")[2]
    t_final = _final_time(tracks)
    period = Timeline(a).period
    kicks = sorted(t for t, n, d, v in drums if n == "kick" and t_final - 2.2 * period < t <= t_final + 0.01)
    assert len(kicks) >= 3 and np.allclose(np.diff(kicks[-3:]), period, rtol=0.04)   # שלוש מכות בקצב, בלי האטה
    bass = sorted((t, d) for t, m, d, v in _track(tracks, "bass")[2] if t > kicks[-3] - 0.05)
    starts = sorted({round(t, 1) for t, d in bass})
    assert len(starts) == 3 and max(d for t, d in bass if t < kicks[-1] - 0.05) < period    # שתי הראשונות קצרות
    solo = [t for t, m, d, v in _track(tracks, solo=True)[2] if t > kicks[-3] - 0.05]
    assert len(solo) == 3                                    # גם הכלי המוביל מכה שלוש פעמים
    steady, _ = render(a, _style("חסידי קצבי", ritardando=False))
    assert abs(_final_time(steady) - kicks[-3]) < 0.05       # המכה הראשונה - בדיוק במקום של אקורד הסיום, בלי האטה
    for name in ("כלייזמר", "הורה"):                         # סגנונות הריקוד מסתיימים כך כברירת מחדל
        assert _style(name)["ending"] == "hits"


def test_fade_out_ending(song):
    a = song
    tracks, lead = render(a, _style("חסידי קצבי", ending="fade"))
    lv = _last_voice(a)
    bar = Timeline(a).period * Timeline(a).meter
    mix = sum(buf if buf.ndim == 1 else buf.mean(axis=1) for _, buf, _ in tracks)
    rms = lambda t0, t1: float(np.sqrt(np.mean(mix[int(t0 * SR):int(t1 * SR)] ** 2)))
    start = lead + lv
    end = max(t + 0.0 for _, _, ev in tracks for t, *_ in ev)
    assert end > start + 3 * bar                             # הליווי ממשיך אחרי השירה...
    q = (end - start) / 4
    levels = [rms(start + k * q, start + (k + 1) * q) for k in range(4)]
    assert levels[0] > levels[1] > levels[2] > levels[3] and levels[3] < 0.25 * levels[0]   # ...והולך ונחלש
    assert np.abs(mix[int((end + bar) * SR):]).max() == 0
    drums = _track(tracks, "drums")[2]
    assert not [1 for t, n, d, v in drums if n == "crash" and t > start + bar]            # בלי אקורד סיום
    # גם בסגנון שאין בו סולו הליווי ממשיך ארבע תיבות ונחלש
    t2, lead2 = render(a, _style("חסידי קצבי", ending="fade", solo=False))
    assert max(t for _, _, ev in t2 for t, *_ in ev) > lead2 + lv + 3 * bar


def test_short_ending_has_no_solo(song):
    a = song
    lv = _last_voice(a)
    bar = Timeline(a).period * Timeline(a).meter
    short, lead = render(a, _style("חסידי קצבי", ending="short"))
    full, _ = render(a, _style("חסידי קצבי"))
    assert _final_time(short) - lead < lv + 2.5 * bar < _final_time(full) - lead
    after = [(t, d) for t, m, d, v in _track(short, solo=True)[2] if t - lead > lv]
    assert len(after) == 1 and after[0][1] > 1.5             # רק הטוניקה שמוחזקת עם אקורד הסיום


def test_final_chord_swell_and_piano_climb(song):
    a = song
    tracks, lead = render(a, _style("ניגון שקט עם פסנתר"))
    piano = sorted(_track(tracks, "piano")[2])
    t_chord = max(t for t, m, d, v in piano if v > 0.5) - 0.3
    climb = [(t, m) for t, m, d, v in piano if t > t_chord and v <= 0.5]
    assert len(climb) >= 3 and [m for _, m in climb] == sorted(m for _, m in climb)
    assert climb[-1][1] % 12 == a.tonic and climb[0][1] > max(m for t, m, d, v in piano if t > t_chord and v > 0.5)
    none, _ = render(a, _style("ניגון שקט עם פסנתר", flourish=False))
    assert not [1 for t, m, d, v in _track(none, "piano")[2] if t > t_chord and v <= 0.5]
    # המצילה מתגברת אל תוך אקורד הסיום
    sw = arrange.cymbal_swell()
    env = np.abs(sw if sw.ndim == 1 else sw.mean(axis=1))
    third = len(env) // 3
    assert 0.8 * SR < len(sw) <= 1.2 * SR and env[:third].mean() < 0.2 * env[-third:].mean()
    drums = _track(render(a, _style("חסידי קצבי"))[0], "drums")
    assert max(t for t, n, d, v in drums[2] if n == "crash") == max(t for t, n, d, v in drums[2])   # המכה - בסוף


# ---------- הפתיח ----------
def _intro_notes(tracks, lead, a):
    first = min(nt.start for nt in a.notes)
    ev = sorted(e for e in _track(tracks, solo=True)[2] if e[0] < lead + first - 0.05)
    return [e for e in ev if e[3] > 0.5]                     # בלי הקול השני (הטרצה) שמצטרף בחצי השני


def test_intro_from_the_chorus(song):
    a = song
    start, lead = render(a, _style("חסידי קצבי"))
    chorus, lead_c = render(a, _style("חסידי קצבי", intro_kind="chorus"))
    assert abs(lead - lead_c) < 1e-6                         # אותו אורך - רק המנגינה אחרת
    tl = Timeline(a, intro_bars=6)
    lv = _last_voice(a)
    pos = arrange.chorus_source(a, tl, sections(a, tl, lv), 4, lv)
    assert pos is not None
    a0, a1 = tl.beat_time(pos) - tl.lead, tl.beat_time(pos + 4 * tl.meter) - tl.lead
    want = [int(round(nt.pitch)) % 12 for nt in a.notes if a0 - 0.05 <= nt.start < a1 - 0.05 and nt.end - nt.start > 0.08]
    got = [m % 12 for t, m, d, v in _intro_notes(chorus, lead_c, a)]
    assert len(got) >= 4 and got == want[: len(got)]
    sing0 = tl.beat_time(tl.bar0 + 6 * tl.meter)
    times = [t for t, m, d, v in _intro_notes(chorus, lead_c, a)]
    assert min(times) > sing0 - 4.2 * tl.period * tl.meter and max(times) < sing0
    # האקורדים שמתחת לפתיח הם של אותן תיבות בפזמון
    acc = [(t - lead_c, m % 12) for t, m, d, v in _track(chorus, "accordion")[2]
           if sing0 - 4 * tl.period * tl.meter + 0.05 < t < sing0 - 1.1 * tl.period]
    ok = 0
    for t, pc in acc:
        src = tl.beat_time(tl.pos_of(t) + (pos - (tl.bar0 + 2 * tl.meter))) - tl.lead
        ch = [c for s0, e0, c in a.chords if s0 - 0.05 <= src < e0]
        ok += bool(ch) and pc in {(ch[0]["root"] + k) % 12 for k in (0, 3, 4, 7, 10, 11)}
    assert acc and ok > 0.9 * len(acc)
    # שיר בלי פזמון שלם - חוזרים לפתיח הרגיל
    assert arrange.chorus_source(a, tl, [0, 0, 0], 4, lv) is None


def test_long_and_short_intro(song):
    a = song
    bar = Timeline(a).period * Timeline(a).meter
    _, lead = render(a, _style("חסידי קצבי"))
    long, lead_long = render(a, _style("חסידי קצבי", intro_kind="long"))
    short, lead_short = render(a, _style("חסידי קצבי", intro_kind="short"))
    assert abs(lead_long - lead - 4 * bar) < 0.05 and abs(lead - lead_short - 4 * bar) < 0.05
    assert len(_intro_notes(long, lead_long, a)) > len(_intro_notes(render(a, _style("חסידי קצבי"))[0], lead, a))
    assert not [e for e in _track(short, solo=True)[2] if e[0] < lead_short]
    # שיר קצר: פתיח ארוך מתקצר מעצמו
    tiny = analyze(sing(bpm=120, repeats=1)[0])
    _, lead_tiny = render(tiny, _style("חסידי קצבי", intro_kind="long"))
    assert lead_tiny < lead_long - 3 * bar
    _, lead_bad = render(a, _style("חסידי קצבי", intro_kind="משהו אחר", ending="לא קיים"))
    assert abs(lead_bad - lead) < 1e-6                       # ערך לא מוכר = הרגיל


# ---------- הבחירה בהגדרות ----------
def test_user_choice_overrides_the_style(qapp, appdata):
    from shir_studio.advanced import AdvancedDialog
    from shir_studio import prefs
    st = _style("הורה")
    assert Song._open_close(st, Settings())["ending"] == "hits"
    chosen = Song._open_close(st, Settings(intro="chorus", ending="fade"))
    assert chosen["ending"] == "fade" and chosen["intro_kind"] == "chorus" and st["ending"] == "hits"
    vocal = _style("ווקאלי - בלי כלים")
    assert vocal.get("intro") is False and Song._open_close(vocal, Settings(intro="start"))["intro"] is True
    dlg = AdvancedDialog(None, Settings())
    assert dlg.intro.count() == 1 + len(INTROS) and dlg.ending.count() == 1 + len(ENDINGS)
    assert dlg.settings().intro == "auto" and dlg.settings().ending == "auto"
    dlg.intro.setCurrentIndex(dlg.intro.findData("long"))
    dlg.ending.setCurrentIndex(dlg.ending.findData("hits"))
    got = dlg.settings()
    assert (got.intro, got.ending) == ("long", "hits")
    again = AdvancedDialog(None, got)
    assert again.intro.currentData() == "long" and again.ending.currentData() == "hits"
    p = prefs.store_personal({}, got)                        # חלק מ'הטעם שלי'
    mine = prefs.personal_settings(p)
    assert (mine.intro, mine.ending) == ("long", "hits")


def test_song_is_made_with_the_chosen_ending():
    x, _ = sing(bpm=120, repeats=3)
    s = Song(x)
    st = _style("חסידי קצבי")
    full = s.make(st, quiet)
    short = s.make(st, quiet, Settings(ending="short", intro="short"))
    assert np.isfinite(short).all() and len(short) < len(full) - 10 * SR
    fade = s.make(st, quiet, Settings(ending="fade"))
    assert np.isfinite(fade).all() and np.abs(fade).max() <= 0.9
    tail = fade[-3 * SR:]
    assert np.sqrt(np.mean(tail ** 2)) < 0.3 * np.sqrt(np.mean(fade[len(fade) // 2: len(fade) // 2 + 3 * SR] ** 2))
