"""בדיקות למסכים עצמם: מריצים את החלון הראשי בלי תצוגה ועם כרטיס קול מדומה,
ועוברים על הפעולות שמשתמש עושה - מהקלטה ועד שמירה."""
import os
import time

import numpy as np
import pytest

import synth_voice
from synth_voice import sing
from shir_studio.audio.fileio import SR, save, load
from shir_studio.audio import devices, edit
from conftest import FakeSD


def _phrased():
    old = synth_voice.MELODY
    mel = []
    for i in range(0, len(old), 6):
        mel += old[i:i + 6] + [(None, 3)]
    synth_voice.MELODY = mel
    try:
        return sing(bpm=120, repeats=1)[0]
    finally:
        synth_voice.MELODY = old


@pytest.fixture(scope="module")
def voice():
    return _phrased()


@pytest.fixture
def win(qapp, appdata, fake_sd, monkeypatch, tmp_path):
    from shir_studio.ui import MainWindow
    from shir_studio import recovery
    log = {"error": [], "info": [], "ask": [], "answer": False}
    monkeypatch.setattr(MainWindow, "error", lambda self, t: log["error"].append(t))
    monkeypatch.setattr(MainWindow, "_info", lambda self, title, text, b="": log["info"].append((title, text)))
    monkeypatch.setattr(MainWindow, "_ask", lambda self, title, text, *a: (log["ask"].append(title), log["answer"])[1])
    monkeypatch.setattr(MainWindow, "_docs", staticmethod(lambda *p: os.path.join(str(tmp_path), "docs", *p)))
    monkeypatch.setattr(MainWindow, "_reveal", staticmethod(lambda path: None))
    w = MainWindow()
    w.log, w.sd, w.tmp = log, fake_sd, tmp_path
    w.show()
    yield w
    w.dirty = False
    w.close()
    recovery.clear()


def wait(qapp, cond, timeout=120):
    t = time.time()
    while not cond():
        qapp.processEvents()
        time.sleep(0.01)
        assert time.time() - t < timeout, "המסך לא הגיע למצב המצופה"
    qapp.processEvents()


def ready(qapp, w, voice):
    """שיר מוכן על המסך."""
    w.process(voice.copy())
    assert w.stack.currentWidget() is w.style_page
    w.style_page.set_current(1)
    w.make_song()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert not w.log["error"]


def sing_into(w, mic, block=1024):
    """מזרים 'שירה' למיקרופון המדומה."""
    stream = w.sd.streams[-1] if not isinstance(w.recorder, devices.Recorder) else w.sd.streams[0]
    for i in range(0, len(mic), block):
        chunk = mic[i:i + block].reshape(-1, 1)
        if isinstance(w.recorder, devices.Overdub):
            stream.callback(chunk, np.zeros((len(chunk), 2), np.float32), len(chunk), None, None)
        else:
            stream.callback(chunk, len(chunk), None, None)


def test_make_listen_compare_undo(qapp, win, voice):
    w = win
    assert w.stack.currentWidget() is w.home
    ready(qapp, w, voice)
    assert w.result is not None and w.result.ndim == 2 and w.dirty
    assert not w.done.b_undo.isEnabled() and "פסנתר" in w.done.hint.text()
    # האזנה והשוואה לפני / אחרי - ממשיכים מאותו מקום בשיר
    w.done.play_result.emit()
    assert w.playing == "result" and len(w.sd.played[-1]) == len(w.result)
    w.player.t0 -= 5.0                                    # 'עברו' חמש שניות
    w.done.compare.emit()
    assert w.playing == "original"
    assert abs(w.player.offset - (5.0 - w.song.last_lead)) < 0.3
    assert np.abs(w.sd.played[-1]).max() > 0.5            # המקור מוגבר להשמעה
    w.done.compare.emit()
    assert w.playing == "result" and abs(w.player.offset - 5.0) < 0.5
    w._update_pos()
    assert "השיר המוכן" in w.done.pos_label.text()
    w.done.stop.emit()
    assert w.playing is None
    # סגנון אחר, ואז ביטול
    first = w.result
    w.done.other_style.emit()
    w.style_page.set_current(2)
    w.style_page.make.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.done.b_undo.isEnabled() and w.result is not first
    w.done.undo.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.style_page.current() == 1 and w.done.b_redo.isEnabled()
    assert w.result.shape == first.shape and np.allclose(w.result, first, atol=1e-4)


def test_trim_then_undo_brings_back_the_recording(qapp, win, voice):
    from shir_studio.trimview import TrimDialog
    w = win
    padded = np.concatenate([np.zeros(3 * SR, np.float32), voice, np.zeros(2 * SR, np.float32)])
    ready(qapp, w, padded)
    dlg = TrimDialog(w, w.original, play=w._play, stop=w.stop_playing)
    s, e = dlg.selection()                                 # נפתח כשהשקט כבר מסומן להורדה
    assert 2.5 < s < 3.6 and e < len(padded) / SR - 1.0
    dlg.play_selection()
    assert abs(len(w.sd.played[-1]) / SR - (e - s)) < 0.05
    dlg.wave.set_range(0, dlg.wave.dur)
    assert dlg.selection() is None                         # לא נחתך כלום
    dlg.auto()
    w.apply_trim(edit.cut(w.original, *dlg.selection()))
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert abs(len(w.original) / SR - (e - s)) < 0.05 and w.done.b_undo.isEnabled()
    w.done.undo.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert len(w.original) == len(padded)


def test_pitch_graph_manual_fix(qapp, win, voice):
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from shir_studio.pitchview import PitchDialog
    w = win
    ready(qapp, w, voice)
    dlg = PitchDialog(w, w.song.pitch_curves(w.settings), w.settings.note_edits)
    dlg.show()
    qapp.processEvents()
    v = dlg.view
    i = next(k for k, n in enumerate(v.notes) if n[1] - n[0] > 0.4 and n[1] < v.view[1])
    n = v.notes[i]
    pt = v._xy(v._area(), (n[0] + n[1]) / 2, v.target(i)).toPoint()
    assert v.note_at(pt) == i
    step = v._area().height() / (v.hi - v.lo)
    QTest.mousePress(v, Qt.LeftButton, Qt.NoModifier, pt)
    QTest.mouseMove(v, QPoint(pt.x(), int(pt.y() - 2 * step)))
    QTest.mouseRelease(v, Qt.LeftButton, Qt.NoModifier, QPoint(pt.x(), int(pt.y() - 2 * step)))
    assert dlg.edits() == {n[4]: 2} and dlg.changed()          # גרירה למעלה = שני חצאי טונים
    j = next(k for k, m in enumerate(v.notes) if k > i and m[1] - m[0] > 0.4 and m[1] < v.view[1])
    QTest.mouseDClick(v, Qt.LeftButton, Qt.NoModifier, v._xy(v._area(), sum(v.notes[j][:2]) / 2, v.target(j)).toPoint())
    assert dlg.edits()[v.notes[j][4]] == "off"                 # לחיצה כפולה = בלי תיקון
    dlg.clear()
    assert not dlg.changed()
    dlg.close()
    w.apply_note_edits({n[4]: 2})
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.settings.note_edits == {n[4]: 2}
    assert dict((x[4], x[3]) for x in w.song.pitch_curves()[3])[n[4]] == n[5] + 2
    w.done.undo.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.settings.note_edits is None


def test_rerecord_one_phrase(qapp, win, voice):
    from shir_studio.trimview import PunchDialog
    w = win
    ready(qapp, w, voice)
    key = (w.song.analysis.tonic, w.song.analysis.mode)
    dlg = PunchDialog(w, w.original, play=w._play, stop=w.stop_playing)
    assert len(dlg.slots) == 4
    dlg.list.setCurrentRow(2)
    dlg.play_phrase()
    s, e, lo, hi = dlg.slot()
    assert abs(len(w.sd.played[-1]) / SR - (hi - lo)) < 0.05
    before = w.original.copy()
    w.start_punch(dlg.slot())
    assert w.stack.currentWidget() is w.rec and isinstance(w.recorder, devices.Overdub)
    back = w.recorder.backing[:, 0]                      # לפני המשפט שומעים את מה שקודם לו
    assert len(back) == 3 * SR and np.abs(back[-SR:]).max() > 0
    take = before[int(s * SR):int(e * SR)] * 0.5
    sing_into(w, np.concatenate([np.zeros(int(3.3 * SR), np.float32), take]))
    w.countdown_end = 0
    w._tick()
    assert w.rec.title.text() == "שיר עכשיו את המשפט"
    w.rec.stop.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert not w.log["error"] and len(w.original) == len(before)
    a, b = int(lo * SR), int(hi * SR)
    assert np.array_equal(w.original[:a], before[:a]) and np.array_equal(w.original[b:], before[b:])
    assert not np.array_equal(w.original[a:b], before[a:b])
    assert w.settings.key == key and w.song.grid is not None      # אותו סולם ואותו קצב
    # הקלטה שקטה: הודעה ברורה, והשיר נשאר כמו שהיה
    cur = w.original
    w.start_punch(dlg.slot())
    sing_into(w, np.zeros(5 * SR, np.float32))
    w.countdown_end = 0
    w._tick()
    w.rec.stop.emit()
    assert w.log["error"] and w.stack.currentWidget() is w.done and w.original is cur


def test_sing_again_over_the_accompaniment(qapp, win, voice):
    w = win
    ready(qapp, w, voice)
    w.done.overdub.emit()                                  # ענו 'ביטול' על שאלת האוזניות
    assert w.stack.currentWidget() is w.done and w.log["ask"]
    w.log["answer"] = True
    old_beats = w.song.analysis.beats.copy()
    w.done.overdub.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.rec)
    assert isinstance(w.recorder, devices.Overdub)
    lead = w.overdub_lead
    assert w.recorder.backing.shape[1] == 2 and np.abs(w.recorder.backing[:3 * SR]).max() == 0
    assert np.abs(w.recorder.backing[3 * SR:]).max() > 0.05      # אחרי הספירה - הליווי
    lat = int(sum(w.sd.streams[-1].latency) * SR)
    sing_into(w, np.concatenate([np.zeros(int((3 + lead) * SR) + lat, np.float32), voice]))
    w.countdown_end = 0
    w._tick()
    w.rec.stop.emit()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert not w.log["error"]
    assert abs(len(w.original) - len(voice)) < 2048 and np.allclose(w.original[:SR], voice[:SR], atol=1e-6)
    assert np.allclose(w.song.analysis.beats, old_beats)         # הקצב של הליווי נשמר בדיוק
    assert os.listdir(os.path.join(str(w.tmp), "docs", "הקלטות"))


def test_recording_with_live_backup(qapp, win, voice):
    from shir_studio import recovery
    w = win
    w.home.record.emit()
    assert w.stack.currentWidget() is w.rec and w.rec.time.text() == "3"
    sing_into(w, np.ones(SR, np.float32) * 0.5)            # רעש בזמן הספירה - לא נכנס להקלטה
    w.countdown_end = 0
    w._tick()
    sing_into(w, voice)
    w._last_flush = 0
    w._tick()
    assert w.rec.level.value() >= 0
    # אילו התוכנה נסגרה עכשיו - ההקלטה כבר שמורה בדיסק
    assert os.path.getsize(os.path.join(recovery.folder(), recovery.REC)) > 0.9 * 2 * len(voice)
    w.rec.stop.emit()
    assert w.stack.currentWidget() is w.style_page and abs(len(w.original) - len(voice)) < 2048
    assert recovery.pending() is None and w.backup is None
    assert os.listdir(os.path.join(str(w.tmp), "docs", "הקלטות"))
    # ביטול באמצע הספירה
    w.go_home()
    w.home.record.emit()
    w.rec.stop.emit()
    assert w.stack.currentWidget() is w.home and recovery.pending() is None


def test_drag_files_and_project(qapp, win, voice, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    w = win
    p = str(w.tmp / "ניגון.wav")
    save(p, voice)
    w.open_paths([str(w.tmp / "מכתב.docx")])
    assert w.log["error"] and w.stack.currentWidget() is w.home
    w.open_paths([p])
    assert w.stack.currentWidget() is w.style_page and w.original is not None
    w.style_page.set_current(2)
    w.settings.reverb = 140
    w.make_song()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    proj = str(w.tmp / "שיר.shir")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (proj, "")))
    w.done.save_project.emit()
    assert os.path.exists(proj) and not w.dirty
    w.done.new_song.emit()
    w.style_page.set_current(0)
    w.settings.reverb = 100
    w.open_paths([proj])                                    # גרירת פרויקט - נפתח ומוכן מיד
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.style_page.current() == 2 and w.settings.reverb == 140


def test_save_chord_sheet_and_share(qapp, win, voice, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    w = win
    ready(qapp, w, voice)
    pdf = str(w.tmp / "אקורדים")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, "")))
    w.done.chords.emit()
    with open(pdf + ".pdf", "rb") as f:
        assert f.read(5) == b"%PDF-"
    mp3 = str(w.tmp / "שיר")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (mp3, "")))
    assert w.dirty
    w.done.save.emit()
    assert len(load(mp3 + ".mp3")) > 10 * SR and not w.dirty
    w.done.share.emit()
    assert os.listdir(os.path.join(str(w.tmp), "docs", "לשליחה"))
    assert not w.log["error"] and len(w.log["info"]) == 3


def test_unsaved_song_is_offered_after_restart(qapp, win, voice):
    from shir_studio.ui import MainWindow
    from shir_studio import recovery
    w = win
    ready(qapp, w, voice)
    w.style_page.set_current(2)
    w.make_song()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    w.close()                                               # נסגר בלי לשמור
    assert recovery.pending()[0] == "session"
    w.log["answer"] = True
    w2 = MainWindow()
    try:
        wait(qapp, lambda: w2.stack.currentWidget() is w2.done)        # ההצעה לשחזר מופיעה לבד בהפעלה
        assert "נמצא שיר שלא נשמר" in w.log["ask"]
        assert w2.style_page.current() == 2 and np.array_equal(w2.original, voice)
        w2.dirty = False
        w2.close()                                          # הפעם הכול 'נשמר' - אין מה לשחזר
        assert recovery.pending() is None
    finally:
        w2.dirty = False
        w2.close()


def test_personal_taste_and_advanced_dialog(qapp, win, voice, monkeypatch):
    from shir_studio.ui import MainWindow
    from shir_studio.advanced import AdvancedDialog
    w = win
    ready(qapp, w, voice)
    dlg = AdvancedDialog(w, w.settings, w.song.info(), style=w.style())
    dlg.modulate.setChecked(True)
    dlg.reverb.slider.setValue(150)
    st = dlg.settings()
    assert st.modulate and st.reverb == 150

    def fake_exec(self):
        self.modulate.setChecked(True)
        self.reverb.slider.setValue(150)
        return 3                                             # 'שמור כטעם שלי'
    monkeypatch.setattr(AdvancedDialog, "exec", fake_exec)
    w.open_advanced(remake=True)
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.settings.modulate and "קצר מדי לעליית סולם" in w.done.hint.text()
    w2 = MainWindow()                                        # הפעלה חדשה של התוכנה
    try:
        assert w2.settings.reverb == 150 and w2.settings.modulate and w2.style_page.current() == 1
    finally:
        w2.close()


def test_medley_and_update_check(qapp, win, voice, monkeypatch):
    from shir_studio import update
    from shir_studio.medleyview import MedleyDialog
    w = win
    p1, p2 = str(w.tmp / "א.wav"), str(w.tmp / "ב.wav")
    save(p1, voice[: 6 * SR])
    save(p2, voice[6 * SR: 12 * SR])
    dlg = MedleyDialog(w, "חסידי")
    dlg.add_paths([p1])
    assert not dlg.ok.isEnabled()
    dlg.add_paths([p2])
    dlg.list.setCurrentRow(1)
    dlg.move(-1)
    assert dlg.paths() == [p2, p1] and dlg.ok.isEnabled()
    out = str(w.tmp / "מחרוזת.mp3")
    w.make_medley(dlg.paths(), out, False, 1.0)
    wait(qapp, lambda: w.stack.currentWidget() is w.home)
    assert os.path.getsize(out) > 20000 and w.log["info"][-1][0] == "מחרוזת"
    # בדיקת גרסה - רק בלחיצה, וגם בלי אינטרנט לא קורה כלום רע
    monkeypatch.setattr(update, "latest_version", lambda *a, **k: None)
    w.home.check_update.emit()
    wait(qapp, lambda: w.log["info"][-1][0] == "בדיקת גרסה")
    assert "אינטרנט" in w.log["info"][-1][1] and w.home.b_update.isEnabled()
    monkeypatch.setattr(update, "latest_version", lambda *a, **k: "9.9.9")
    w.home.check_update.emit()
    wait(qapp, lambda: "יש גרסה חדשה" in w.log["ask"])


def test_sound_options_and_song_details(qapp, win, voice, monkeypatch):
    """אופי הקול, גודל האולם, עוצמת השיר, FLAC - ושם השיר והזמר בתוך הקובץ."""
    from PySide6.QtWidgets import QFileDialog
    from shir_studio.advanced import AdvancedDialog
    from shir_studio.audio import loudness
    from shir_studio import tags, prefs
    w = win
    ready(qapp, w, voice)
    w.make_song()
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    before = loudness.lufs(w.result)

    def fake_exec(self):
        self.voice_tone.setCurrentIndex(self.voice_tone.findData("warm"))
        self.space.setCurrentIndex(self.space.findData("big"))
        self.loudness.setCurrentIndex(self.loudness.findData("loud"))
        self.artist.setText("יוסף כהן")
        return 1
    monkeypatch.setattr(AdvancedDialog, "exec", fake_exec)
    w.open_advanced(remake=True)
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    st = w.settings
    assert (st.voice_tone, st.space, st.loudness) == ("warm", "big", "loud")
    assert loudness.lufs(w.result) > before + 1.5
    assert prefs.load()["artist"] == "יוסף כהן"                # שם הזמר נשמר לפעם הבאה
    mp3 = str(w.tmp / "ניגון של שבת.mp3")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (mp3, "")))
    w.save_result()
    got = tags.read(mp3)
    assert got["title"] == "ניגון של שבת" and got["artist"] == "יוסף כהן"
    w.save_fmt = "flac"
    flac = str(w.tmp / "ניגון")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (flac, "")))
    w.save_result()
    assert os.path.getsize(flac + ".flac") > 20000 and not w.log["error"]
    w.undo()                                                # ביטול מחזיר גם את ההגדרות החדשות
    wait(qapp, lambda: w.stack.currentWidget() is w.done)
    assert w.settings.loudness == "normal"
