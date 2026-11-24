"""בדיקות לשדרוגים: ציון דיוק ומצב תרגול, שילוב הקלטות (בחירת המיטב), מילות השיר,
קיצורי מקלדת ובדיקת מיקרופון."""
import os

import numpy as np
import pytest

import synth_voice
from synth_voice import sing
from shir_studio.audio.fileio import SR, save
from shir_studio.audio import devices, edit, takes
from shir_studio.audio.pitch import yin
from shir_studio.music import score, theory
from test_ui import win, wait, ready, sing_into          # noqa: F401  (אותו חלון ראשי כמו בבדיקות המסכים)

A_MINOR = theory.scale_pcs(9, "minor")


def phrased(**kw):
    """ארבעה משפטים עם נשימה ביניהם."""
    old = synth_voice.MELODY
    mel = []
    for i in range(0, len(old), 6):
        mel += old[i:i + 6] + [(None, 3)]
    synth_voice.MELODY = mel
    try:
        return sing(bpm=120, repeats=1, **kw)[0]
    finally:
        synth_voice.MELODY = old


@pytest.fixture(scope="module")
def clean_voice():
    return phrased(wobble=0.02, seed=3)


@pytest.fixture(scope="module")
def rough_voice():
    return phrased(wobble=0.45, seed=5)


# ---------- ציון דיוק ----------
def test_score_follows_how_clean_the_singing_is(clean_voice, rough_voice):
    good = score.grade(score.deviation(yin(clean_voice)[0], A_MINOR))
    bad = score.grade(score.deviation(yin(rough_voice)[0], A_MINOR))
    assert good > 90 and bad < good - 20
    # זמר שכל השיר שלו גבוה ברבע טון (בלי ליווי זה לא נשמע) - לא מפסיד על זה נקודות
    high = phrased(wobble=0.02, seed=3, detune=0.3)
    assert score.grade(score.deviation(yin(high)[0], A_MINOR)) > 88
    assert abs(score.own_tuning(np.array([60.3, 62.3, 64.3])) - 0.3) < 1e-6
    assert score.grade(np.full(100, np.nan)) is None       # אין שירה - אין ציון


def test_vibrato_is_not_counted_as_out_of_tune():
    vib = phrased(wobble=0.02, seed=3, vibrato=0.6)
    assert score.grade(score.deviation(yin(vib)[0], A_MINOR)) > 80


def test_phrase_report_finds_the_weak_phrase(clean_voice):
    from shir_studio.pipeline import Song
    # משפט אחד (השלישי) מושר נמוך בשליש טון
    slots = edit.phrase_slots(clean_voice)
    assert len(slots) == 4
    from shir_studio.audio.psola import shift
    f0 = yin(clean_voice)[0]
    corr = np.zeros(len(f0))
    a, b = score.frames(slots[2][2], slots[2][3])
    corr[a:b] = -0.35
    flat = shift(clean_voice, f0, corr)
    song = Song(flat)
    song.prepare(lambda p, m=None: None)
    rep = score.phrase_report(song.analysis, slots)
    scores = [r["score"] for r in rep]
    assert int(np.argmin(scores)) == 2 and scores[2] < min(scores[0], scores[1], scores[3]) - 20
    assert rep[2]["cents"] < -12 and "נוטה לרדת" in rep[2]["text"]
    assert min(scores[0], scores[1], scores[3]) > 72 and "כדאי לתרגל" not in rep[0]["text"]
    total = score.overall(rep, slots)
    assert min(scores) < total < max(scores)


# ---------- שילוב הקלטות ----------
def test_best_of_takes_the_cleaner_phrases(clean_voice, rough_voice):
    out, picks = takes.best_of(rough_voice, clean_voice, A_MINOR)
    new, kept = takes.summary(picks)
    assert len(picks) == 4 and new >= 3 and len(out) == len(rough_voice)
    for p in picks:
        a, b = int((p["start"] + 0.3) * SR), int((p["end"] - 0.3) * SR)
        src = clean_voice if p["pick"] == "new" else rough_voice
        ratio = out[a:b] / np.where(np.abs(src[a:b]) > 1e-3, src[a:b], np.nan)
        assert np.nanstd(ratio) < 1e-3                   # באמצע המשפט - הקלטה אחת בלבד, בלי ערבוב
    # ההפך: ההקלטה החדשה פחות טובה - השיר נשאר בדיוק כמו שהיה
    out2, picks2 = takes.best_of(clean_voice, rough_voice, A_MINOR)
    assert takes.summary(picks2)[0] == 0 and np.array_equal(out2, clean_voice)


def test_best_of_keeps_a_phrase_the_singer_skipped(clean_voice, rough_voice):
    slots = edit.phrase_slots(rough_voice)
    take = clean_voice.copy()
    take[int(slots[1][2] * SR): int(slots[1][3] * SR)] = 0   # במשפט השני הזמר לא שר בהקלטה החדשה
    out, picks = takes.best_of(rough_voice, take, A_MINOR)
    assert picks[1]["pick"] == "old" and picks[0]["pick"] == "new"
    a, b = int(slots[1][0] * SR), int(slots[1][1] * SR)
    assert np.array_equal(out[a:b], rough_voice[a:b])
    # הקלטה חדשה קצרה או ארוכה יותר - מיושרת לאורך השיר
    assert len(takes.best_of(rough_voice, clean_voice[: len(clean_voice) // 2], A_MINOR)[0]) == len(rough_voice)
    with pytest.raises(Exception):
        takes.best_of(np.zeros(5 * SR, np.float32), clean_voice, A_MINOR)


def test_seams_are_smooth(clean_voice, rough_voice):
    out, picks = takes.best_of(rough_voice, clean_voice, A_MINOR)
    for p in picks[1:]:
        i = int(p["start"] * SR)
        assert np.abs(np.diff(out[i - 2000:i + 2000])).max() < 0.05      # אין 'קליק' בנקודת החיבור


# ---------- מילות השיר ----------
LYRICS = "שורה ראשונה\nשורה שנייה\n\nבית שני\nועוד שורה"


def test_lyrics_in_mp3_and_chord_sheet(qapp, tmp_path, clean_voice):
    from shir_studio import tags, chordsheet
    from shir_studio.pipeline import Song
    from shir_studio.music.styles import load_styles
    p = str(tmp_path / "שיר.mp3")
    save(p, clean_voice, tags={"title": "ניגון", "artist": "זמר", "lyrics": LYRICS})
    got = tags.read(p)
    assert got["lyrics"] == LYRICS and got["title"] == "ניגון" and got["artist"] == "זמר"
    assert "lyrics" not in tags.read(_saved(tmp_path, clean_voice, {"title": "בלי מילים"}))
    assert chordsheet.stanzas(LYRICS) == [["שורה ראשונה", "שורה שנייה"], ["בית שני", "ועוד שורה"]]
    assert chordsheet.stanzas("") == [] and chordsheet.stanzas("\n\n  \n") == []
    song = Song(clean_voice)
    song.make(load_styles()[1], lambda p, m=None: None)
    data = chordsheet.sheet_data(song, "ניגון", LYRICS)
    text = chordsheet.as_text(data)
    assert "[מילות השיר]" in text and "בית שני" in text
    assert "[מילות השיר]" not in chordsheet.as_text(chordsheet.sheet_data(song, "ניגון"))
    long = "\n\n".join("\n".join(f"שורה {i} בבית {b}" for i in range(4)) for b in range(30))   # יותר מעמוד
    pdf = str(tmp_path / "דף.pdf")
    chordsheet.write_pdf(pdf, chordsheet.sheet_data(song, "ניגון", long))
    assert open(pdf, "rb").read(4) == b"%PDF" and os.path.getsize(pdf) > 2000


def _saved(tmp_path, voice, tg):
    p = str(tmp_path / "x.mp3")
    save(p, voice, tags=tg)
    return p


def test_lyrics_stay_with_the_song(qapp, win, clean_voice, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from shir_studio import tags, recovery
    from shir_studio.lyricsview import LyricsDialog
    w = win
    ready(qapp, w, clean_voice)
    dlg = LyricsDialog(w, "")
    dlg.edit.setPlainText("  " + LYRICS + "  \n\n")
    assert dlg.text() == LYRICS
    w.dirty = False
    w.set_lyrics(dlg.text())
    assert w.dirty and "✔" in w.done.b_lyrics.text()
    assert recovery.pending()[2]["lyrics"] == LYRICS      # גם אם התוכנה נסגרת עכשיו - המילים שמורות
    mp3, proj = str(w.tmp / "שיר.mp3"), str(w.tmp / "שיר.shir")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (mp3, "")))
    w.save_result()
    assert tags.read(mp3)["lyrics"] == LYRICS
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (proj, "")))
    w.save_project()
    # שיר חדש מתחיל בלי מילים, ופתיחת הפרויקט מחזירה אותן
    w.process(clean_voice.copy())
    assert w.lyrics == "" and "✔" not in w.done.b_lyrics.text()
    w.open_project(proj)
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.lyrics == LYRICS and "✔" in w.done.b_lyrics.text()
    # ביטול שינוי לא מוחק את המילים
    w.done.other_style.emit()
    w.style_page.set_current(2)
    w.style_page.make.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    w.done.undo.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.lyrics == LYRICS


# ---------- מצב תרגול ----------
def test_practice_dialog(qapp, win, rough_voice):
    from shir_studio.practiceview import PracticeDialog, loop_clip, LOOPS, GAP
    w = win
    ready(qapp, w, rough_voice)
    dlg = PracticeDialog(w, w.original, w.song.analysis, w.song.tuned, play=w._play, stop=w.stop_playing)
    assert len(dlg.slots) == 4 and dlg.list.count() == 4 and "מתוך 100" in dlg.total.text()
    scores = [r["score"] for r in dlg.report]
    assert dlg.list.currentRow() == int(np.argmin(scores))     # נפתח על המשפט החלש ביותר
    s, e, lo, hi = dlg.slot()
    dlg.play_mine()
    assert abs(len(w.sd.played[-1]) / SR - (hi - lo)) < 0.05 and np.abs(w.sd.played[-1]).max() > 0.5
    dlg.speed.setCurrentIndex(2)                               # לאט מאוד: פי שניים יותר ארוך, אותו גובה צליל
    dlg.play_mine()
    slow = w.sd.played[-1]
    assert abs(len(slow) / SR - 2 * (hi - lo)) < 0.1
    f_slow, f_norm = yin(slow)[0], yin(w.original[int(lo * SR):int(hi * SR)])[0]
    assert abs(np.median(f_slow[f_slow > 0]) / np.median(f_norm[f_norm > 0]) - 1) < 0.03
    dlg.speed.setCurrentIndex(0)
    dlg.loop.setChecked(True)
    dlg.play_fixed()
    assert abs(len(w.sd.played[-1]) / SR - (LOOPS * (hi - lo) + (LOOPS - 1) * GAP)) < 0.1
    assert len(loop_clip(np.ones(SR, np.float32), 1.0, 1)) == SR
    # 'הקלט את המשפט מחדש' מתוך התרגול
    dlg.b_punch.click()
    assert dlg.punch == (s, e, lo, hi) and dlg.result() == 1
    w.start_punch(dlg.punch)
    assert w.stack.currentWidget() is w.rec and w.rec_mode == "punch"
    w.rec.cancel.emit()
    assert w.stack.currentWidget() is w.done


# ---------- בחירת המיטב דרך המסך ----------
def test_sing_again_and_keep_the_best(qapp, win, clean_voice, rough_voice):
    w = win
    ready(qapp, w, rough_voice)
    w.set_lyrics(LYRICS)
    w.log["answer"] = True
    w.done.best_take.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.rec)
    assert isinstance(w.recorder, devices.Overdub) and w._best_take
    assert w.rec.lyrics.isVisible() and "בית שני" in w.rec.lyrics.toPlainText()   # המילים מול העיניים
    lead = w.overdub_lead
    lat = int(sum(w.sd.streams[-1].latency) * SR)
    sing_into(w, np.concatenate([np.zeros(int((3 + lead) * SR) + lat, np.float32), clean_voice]))
    w.countdown_end = 0
    w._tick()
    w.rec.stop.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert not w.log["error"]
    title, text = [i for i in w.log["info"] if i[0] == "בחירת המיטב"][-1]
    assert "נלקחו" in text and len(w.original) == len(rough_voice)
    assert not np.array_equal(w.original, rough_voice) and w.done.b_undo.isEnabled()
    assert w.lyrics == LYRICS
    # 'ביטול שינוי' מחזיר את ההקלטה הקודמת
    w.done.undo.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert np.array_equal(w.original, rough_voice)


def test_worse_take_changes_nothing(qapp, win, clean_voice, rough_voice):
    w = win
    ready(qapp, w, clean_voice)
    before, result = w.original, w.result
    w.log["answer"] = True
    w.done.best_take.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.rec)
    lat = int(sum(w.sd.streams[-1].latency) * SR)
    sing_into(w, np.concatenate([np.zeros(int((3 + w.overdub_lead) * SR) + lat, np.float32), rough_voice]))
    w.countdown_end = 0
    w._tick()
    w.rec.stop.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.original is before and w.result is result
    assert "נשאר כמו שהיה" in [i for i in w.log["info"] if i[0] == "בחירת המיטב"][-1][1]


def test_singing_again_uses_the_key_that_was_sung(qapp, win, clean_voice):
    """שיר שהועבר לסולם אחר: הליווי להקלטה החוזרת מנוגן בסולם שבו שרו, והשיר לא עולה פעמיים."""
    import dataclasses
    w = win
    ready(qapp, w, clean_voice)
    plain = w.song.stems_in_sung_key()["ליווי"].copy()
    w.settings = dataclasses.replace(w.settings, transpose=3)
    w.make_song()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    last = w.song._last_make
    back = w.song.stems_in_sung_key()["ליווי"]
    n = min(len(plain), len(back))
    assert np.allclose(plain[:n], back[:n], atol=1e-3)
    assert w.song._last_make is not None and w.song._last_make[1].transpose == 3
    assert w.song._last_make[0] is last[0] and w.song.analysis.transpose == 3 and w.song.last_stems is None


# ---------- קיצורי מקלדת ----------
def test_shortcuts_follow_the_screen(qapp, win, clean_voice):
    from shir_studio import shortcuts
    w = win
    on = lambda key: next(sc for sc, _, k, _ in w.shortcuts if k == key).isEnabled()
    assert on("Ctrl+R") and on("F1") and not on("Space") and not on("Ctrl+S")
    ready(qapp, w, clean_voice)
    assert on("Space") and on("Ctrl+Z") and on("Ctrl+S") and not on("Ctrl+R")
    shortcuts.toggle_play(w)
    assert w.playing == "result"
    w.player.t0 -= 10.0
    shortcuts.skip(w, 5.0)
    assert 14.5 < w.player.offset < 15.5 and w.playing == "result"
    shortcuts.skip(w, -100.0)
    assert w.player.offset == 0.0
    shortcuts.toggle_play(w)
    assert w.playing is None
    shortcuts.skip(w, 5.0)                                 # לא מנגן - לא קורה כלום
    assert w.playing is None
    shortcuts.show_help(w)
    assert w.log["info"][-1][0] == "קיצורי מקלדת" and "רווח" in w.log["info"][-1][1]
    w.home.shortcuts.emit()
    assert len([i for i in w.log["info"] if i[0] == "קיצורי מקלדת"]) == 2
    w.go_home()
    assert not on("Space")
    keys = [k for _, _, k, _ in w.shortcuts]
    assert len(keys) == len(set(keys))                     # אין שני קיצורים על אותו מקש


# ---------- בדיקת מיקרופון ----------
def test_mic_verdict():
    assert devices.mic_verdict(0.0005, 0.0003, 0.0002)[0] == "silent"
    assert devices.mic_verdict(1.0, 0.3, 0.001)[0] == "loud"
    assert devices.mic_verdict(0.05, 0.008, 0.0005)[0] == "quiet"
    assert devices.mic_verdict(0.5, 0.08, 0.03)[0] == "noisy"
    assert devices.mic_verdict(0.5, 0.1, 0.002)[0] == "good"
    assert devices.clipped_share(np.array([0.1, 1.0, -1.0, 0.2])) == 0.5 and devices.clipped_share(np.zeros(0)) == 0.0


def test_mic_check_dialog(qapp, fake_sd):
    from shir_studio.micview import MicDialog, MIN_TICKS
    dlg = MicDialog()
    cb = fake_sd.streams[-1].callback
    assert dlg.failed is None and dlg.result.text() == "מקשיב..."
    rng = np.random.default_rng(0)

    def feed(amp, ticks):
        for _ in range(ticks):
            x = (amp * rng.standard_normal((2048, 1))).astype(np.float32)
            cb(np.clip(x, -1, 1), len(x), None, None)
            dlg.tick()
    feed(0.1, MIN_TICKS - 5)
    assert dlg.result.text() == "מקשיב..."
    feed(0.001, 10)
    assert "מצוין" in dlg.result.text()
    dlg.restart()
    feed(0.9, MIN_TICKS + 2)
    assert "חזק מדי" in dlg.result.text()
    dlg.restart()
    feed(0.004, MIN_TICKS + 2)
    assert "חלש מדי" in dlg.result.text()
    dlg.accept()
    assert not fake_sd.streams[-1].active and not dlg.timer.isActive()


def test_recording_warns_when_too_loud(qapp, win, clean_voice):
    from shir_studio.screens.record import HINT, TOO_LOUD, NOT_HEARD
    w = win
    w.home.record.emit()
    w.countdown_end = 0
    w._tick()
    assert w.rec.hint.text() == HINT
    sing_into(w, np.ones(4096, np.float32))                # הקול נחתך
    w._tick()
    assert w.rec.hint.text() == TOO_LOUD
    w._loud_until = 0
    sing_into(w, clean_voice)
    w._tick()
    assert w.rec.hint.text() == HINT
    # ההקלטה נחתכה במקומות: שואלים אם להקליט שוב (כאן עונים 'הקלט שוב')
    sing_into(w, np.ones(SR // 2, np.float32))
    w.rec.stop.emit()
    assert "ההקלטה חזקה מדי" in w.log["ask"] and w.stack.currentWidget() is w.rec and w.rec_mode == "new"
    # מיקרופון שלא שומע כלום
    w.countdown_end = 0
    w._tick()
    w.rec_start -= 6
    w._tick()
    assert w.rec.hint.text() == NOT_HEARD
    w.rec.cancel.emit()
    assert w.stack.currentWidget() is w.home


# ---------- קול נקי: תיקון הזיופים לא מוסיף צרידות, והרעש מונמך יותר ----------
def _harmonic_to_noise(x, lo=200, hi=6000):
    """כמה הקול 'נקי': האנרגיה שבהרמוניות מול מה שביניהן (dB), בצלילים יציבים."""
    f0 = yin(x)[0]
    n, out = 4096, []
    freqs = np.fft.rfftfreq(n, 1 / SR)
    for i in range(0, len(x) - n, n):
        fr = f0[i * 100 // SR: (i + n) * 100 // SR]
        if len(fr) < 5 or (fr <= 0).any() or fr.max() / fr.min() > 1.02:
            continue
        f = np.median(fr)
        sp = np.abs(np.fft.rfft(x[i:i + n] * np.hanning(n))) ** 2
        near = np.abs(freqs - np.round(freqs / f) * f) < 0.18 * f
        sel = (freqs > lo) & (freqs < hi)
        out.append(10 * np.log10(sp[sel & near].sum() / max(sp[sel & ~near].sum(), 1e-20)))
    return float(np.median(out))


def test_pitch_correction_keeps_the_voice_clean():
    from shir_studio.audio.psola import shift
    x = phrased(wobble=0.2, seed=2, vibrato=0.4)
    f0 = yin(x)[0]
    clean = _harmonic_to_noise(x)
    same = shift(x, f0, np.zeros(len(f0)))
    assert np.mean(np.abs(same - x) > 1e-4) < 0.005                  # בלי תיקון - הקול יוצא כמו שנכנס
    up = shift(x, f0, np.full(len(f0), 0.3))
    assert _harmonic_to_noise(up) > clean - 6                        # עם תיקון - בלי שכבת רעש מתחת לקול
    got, want = yin(up)[0], f0 * 2 ** (0.3 / 12)
    ok = (got > 0) & (f0 > 0)
    assert abs(np.median(12 * np.log2(got[ok] / want[ok]))) < 0.03   # והצליל עלה בדיוק כמה שביקשו


def test_noise_between_phrases_is_pushed_down():
    from shir_studio.audio.denoise import denoise
    x = phrased(wobble=0.1, seed=4)
    ph = edit.voice_phrases(x)
    gap, act = np.ones(len(x), bool), np.zeros(len(x), bool)
    for a, b in ph:
        gap[int((a - 0.25) * SR):int((b + 0.35) * SR)] = False
        act[int((a + 0.1) * SR):int((b - 0.1) * SR)] = True
    rms = lambda v: float(np.sqrt(np.mean(np.square(v))))
    noisy = (x + 0.03 * np.random.default_rng(7).standard_normal(len(x))).astype(np.float32)
    before = 20 * np.log10(rms(noisy[gap]) / rms(noisy[act]))
    y = denoise(noisy)
    after = 20 * np.log10(rms(y[gap]) / rms(y[act]))
    assert after < before - 19                                       # הרחש שבין המשפטים יורד ב-19dB לפחות
