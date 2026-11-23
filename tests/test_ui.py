"""בדיקות למסכים עצמם (בלי מסך אמיתי): תיקון ידני, עריכת משפטים, הגדרות מתקדמות והמסך הראשי."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from synth_voice import sing

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles
from shir_studio.audio import edit
from shir_studio.audio.fileio import SR

quiet = lambda p, m=None: None


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def song():
    a, _ = sing(bpm=120, repeats=1, seed=1)
    b, _ = sing(bpm=120, repeats=1, seed=2)
    x = np.concatenate([a, np.zeros(SR, np.float32), b])
    s = Song(x)
    s.make(load_styles()[1], quiet, Settings())
    return s


def test_pitch_dialog_drag_and_reset(app, song):
    from shir_studio.pitchview import PitchDialog
    st = Settings()
    heard = []
    dlg = PitchDialog(None, lambda fixes: song.pitch_curves(st, fixes), 0,
                      lambda fixes, s, e: heard.append((fixes, s, e)))
    v = dlg.view
    v.resize(1000, 500)
    assert not dlg.changed() and not dlg.b_ok.isEnabled()
    i = next(k for k, n in enumerate(v.notes) if n[1] - n[0] > 0.7 and n[0] > 1)
    n = v.notes[i]
    pos = v._xy(v._rect(), (n[0] + n[1]) / 2, n[3])
    assert v.note_at(pos) == i                                  # לחיצה על המלבן בוחרת את הצליל
    t, m = v._at(pos)
    assert abs(t - (n[0] + n[1]) / 2) < 0.05 and abs(m - n[3]) < 0.05
    v.sel = i
    v.set_target(i, n[3] + 2.2)                                 # גרירה - נצמד לחצי הטון הקרוב
    v.changed.emit()
    assert dlg.fixes() == [[round((n[0] + n[1]) / 2, 3), n[3] + 2]]
    assert dlg.changed() and dlg.b_ok.isEnabled() and v.notes[i][4]
    k0, k1 = int(n[0] * 100) + 10, int(n[1] * 100) - 10
    assert abs(np.nanmedian(v.after[k0:k1]) - (n[3] + 2)) < 0.3  # הקו הירוק עבר לצליל החדש
    dlg._hear()
    assert heard and heard[0][0] == dlg.fixes()
    v.nudge(-1)
    assert dlg.fixes()[0][1] == n[3] + 1
    v.clear(i)                                                  # חזרה לאוטומטי
    assert dlg.fixes() == [] and not dlg.changed() and not v.notes[i][4]
    v.grab()                                                    # הציור עצמו לא נופל


def test_pitch_view_accepts_old_notes_format(app):
    from shir_studio.pitchview import PitchView
    t = np.arange(300) * 0.01
    v = PitchView(t, np.full(300, 60.2), np.full(300, 60.0), [(0.5, 1.5, 60.2)])
    assert v.notes[0][3] == 60 and v.fixes() == []
    v.grab()


class FakeRecorder:
    level = 0.2

    def start(self):
        pass

    def stop(self):
        return np.concatenate([np.zeros(SR // 3, np.float32), 0.3 * sing(bpm=120, repeats=1, seed=9)[0][:6 * SR]])


def test_phrase_dialog_record_duplicate_delete(app, song, monkeypatch):
    from shir_studio import phrases
    monkeypatch.setattr(phrases.QMessageBox, "exec", lambda self: None)
    monkeypatch.setattr(phrases.QMessageBox, "clickedButton", lambda self: self.buttons()[0])
    played = []
    raw = song.raw
    rg = edit.regions(song.analysis, len(raw))
    dlg = phrases.PhraseDialog(None, raw, rg, played.append, lambda: None, FakeRecorder)
    k = len(rg)
    assert k >= 2 and dlg.list.count() == k and not dlg.b_ok.isEnabled() and not dlg.b_use.isEnabled()
    dlg._play_phrase()
    assert len(played) == 1 and 2 * SR < len(played[0]) < 20 * SR
    dlg.list.setCurrentRow(1)
    dlg._toggle_record()
    assert dlg.recorder is not None and not dlg.b_dup.isEnabled()
    dlg._toggle_record()
    assert dlg.recorder is None and dlg.take is not None and dlg.b_use.isEnabled()
    dlg._use_take()
    assert dlg.dirty and len(dlg.raw) == len(raw) and not np.allclose(dlg.raw, raw)
    assert np.array_equal(dlg.raw[: int(rg[1]["a"] * SR)], raw[: int(rg[1]["a"] * SR)])
    assert np.array_equal(dlg.raw[int(rg[1]["b"] * SR):], raw[int(rg[1]["b"] * SR):])
    n = len(dlg.raw)
    dlg.list.setCurrentRow(0)
    dlg._duplicate()
    d = rg[0]["b"] - rg[0]["a"]
    assert dlg.list.count() == k + 1 and abs(len(dlg.raw) - n - d * SR) < 2
    assert abs(dlg.regions[1]["start"] - (rg[0]["start"] + d)) < 1e-6
    assert abs(dlg.regions[2]["start"] - (rg[1]["start"] + d)) < 1e-6
    dlg.list.setCurrentRow(1)
    dlg._delete()
    assert dlg.list.count() == k and abs(len(dlg.raw) - n) < 2
    assert abs(dlg.regions[1]["start"] - rg[1]["start"]) < 1e-6
    assert dlg.b_ok.isEnabled()
    # ההקלטה הערוכה עדיין שיר תקין
    s2 = Song(dlg.raw)
    s2.prepare(quiet)
    assert len(edit.regions(s2.analysis, len(dlg.raw))) >= 2


def test_advanced_dialog_keeps_manual_fixes_and_new_options(app, song):
    from shir_studio.advanced import AdvancedDialog
    st = Settings(note_fixes=[[1.0, 62]], lift=2, meter=6, key=(0, "adonai"))
    dlg = AdvancedDialog(None, st, song.info(), style=load_styles()[0])
    out = dlg.settings()
    assert out.note_fixes == [[1.0, 62]] and out.lift == 2 and out.meter == 6 and out.key == (0, "adonai")
    dlg.lift.setCurrentIndex(0)
    dlg.meter.setCurrentIndex(dlg.meter.findData(3))
    out = dlg.settings()
    assert out.lift == 0 and out.meter == 3 and st.lift == 2      # המקור לא השתנה
    assert AdvancedDialog(None, Settings(), None).settings() == Settings(bpm=110)   # 110 = הקצב שמוצג כשאין שיר


def test_main_window_builds_and_eta(app):
    from shir_studio import ui
    w = ui.MainWindow()
    assert w.stack.count() == 5
    w._start_work()
    w._on_progress(40)
    assert w.bar.value() == 40
    assert ui.eta_text(1, 50) == "" and ui.eta_text(10, 3) == ""
    assert ui.eta_text(10, 50) == "נשארו בערך 10 שניות"
    assert ui.eta_text(60, 50) == "נשארה בערך דקה"
    assert ui.eta_text(60, 20) == "נשארו בערך 4 דקות"
    assert ui.eta_text(30, 95) == "עוד רגע..."
    w.show_pitch(); w.edit_phrases(); w.save_chord_sheet()        # בלי שיר - לא עושים כלום ולא נופלים
