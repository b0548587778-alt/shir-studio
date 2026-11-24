"""בדיקות לכלים של 'הפרדת קול ופלייבק': הפרדה לכלים, כמה שירים, גרסה ווקאלית,
שינוי סולם וקצב של פלייבק, ושירה על פלייבק."""
import os
import time

import numpy as np
import pytest

from synth_voice import sing
from shir_studio.audio import separate as sep, stretch, devices
from shir_studio.audio.fileio import SR, save, load_stereo
from shir_studio.music import arrange
from shir_studio.music.styles import load_styles
from shir_studio.pipeline import Song, Settings

quiet = lambda p, m=None: None


def sdr(ref, est):
    return 10 * np.log10(np.sum(ref ** 2) / (np.sum((ref - est) ** 2) + 1e-12))


def tone(freqs, seconds=6):
    t = np.arange(int(SR * seconds)) / SR
    return sum(0.2 * np.sin(2 * np.pi * f * t) for f in freqs).astype(np.float32)


def pitch_of(y):
    seg = y[SR: 3 * SR] * np.hanning(2 * SR)
    return np.argmax(np.abs(np.fft.rfft(seg))) / 2.0


# ---------------------------------------------------------------- סולם וקצב של פלייבק
@pytest.mark.parametrize("semis,tempo", [(2, 1.0), (-3, 1.0), (0, 0.8), (0, 1.25), (4, 0.9)])
def test_change_key_and_tempo(semis, tempo):
    x = tone([440])
    y = stretch.change(x, semis, tempo)
    assert abs(len(y) - len(x) / tempo) <= 2                         # הקצב משנה רק את האורך
    assert abs(pitch_of(y) - 440 * 2 ** (semis / 12)) < 1.5          # הסולם משנה רק את הגובה
    assert abs(np.std(y[SR:-SR]) / np.std(x) - 1) < 0.1              # העוצמה נשמרת


def test_change_keeps_stereo_and_chords():
    x = np.stack([tone([330, 440, 550]), 0.5 * tone([330, 440, 550])], axis=1)
    assert np.array_equal(stretch.change(x, 0, 1.0), x)              # בלי שינוי - אותו קובץ בדיוק
    marks = []
    y = stretch.change(x, -2, 1.1, progress=marks.append)
    assert y.shape[1] == 2 and abs(len(y) - len(x) / 1.1) <= 2 and marks[-1] == 100
    assert abs(np.std(y[:, 1]) / np.std(y[:, 0]) - 0.5) < 0.05       # היחס בין הערוצים נשמר
    spec = np.abs(np.fft.rfft(y[SR: 3 * SR, 0] * np.hanning(2 * SR)))
    top = sorted(np.argsort(spec)[-3:] / 2.0)                        # שלושת צלילי האקורד ירדו יחד
    assert np.allclose(top, [f * 2 ** (-2 / 12) for f in (330, 440, 550)], atol=2)


# ---------------------------------------------------------------- הפרדה לכלים
def test_stems_plumbing_sums_to_the_song():
    rng = np.random.default_rng(0)
    x = (0.1 * rng.standard_normal((SR * 13, 2))).astype(np.float32)
    marks = []
    parts = sep.separate_stems(x, progress=lambda p, m=None: marks.append(p), run=lambda inp: inp * 0.25)
    assert tuple(parts) == sep.STEM_NAMES and all(v.shape == x.shape for v in parts.values())
    assert np.abs(sum(parts.values()) - x).max() < 1e-5              # שום דבר לא הולך לאיבוד
    assert marks == sorted(marks) and marks[-1] == 100


@pytest.fixture(scope="module")
def band():
    """שיר שנבנה מהכלים של התוכנה - כך ידוע בדיוק מה התופים, מה הבס ומה השאר."""
    song = Song(sing(bpm=120, repeats=1, vibrato=0.6)[0])
    style = load_styles()[0]
    song.make(style, quiet, Settings())
    tracks, lead = arrange.render(song.analysis, style)
    n = SR * 14

    def bus(pred):
        out = np.zeros((n, 2), np.float32)
        for spec, buf, _ in tracks:
            if pred(spec["instrument"]):
                b = buf[:n] if buf.ndim == 2 else np.stack([buf[:n]] * 2, axis=1)
                out[:len(b)] += b * spec.get("volume", 0.7) * 0.3
        return out
    low = ("bass", "acoustic_bass")
    drums, bass = bus(lambda i: i == "drums"), bus(lambda i: i in low)
    other = bus(lambda i: i != "drums" and i not in low)
    voice = np.zeros((n, 2), np.float32)
    s0 = int(lead * SR)
    v = song.tuned[: n - s0]
    voice[s0: s0 + len(v)] = v[:, None] * 0.6
    return {"שירה": voice, "תופים": drums, "בס": bass, "כלים אחרים": other}


def test_real_models_split_drums_and_bass(band):
    assert sep.stems_available(), "מודלי התופים והבס חסרים"
    mix = sum(band.values())
    got = sep.separate_stems(mix)
    assert np.abs(sum(got.values()) - mix).max() < 1e-4
    for name in ("תופים", "בס", "כלים אחרים"):
        assert sdr(band[name], got[name]) > sdr(band[name], mix) + 12, name   # כל כלי נקי בהרבה מאשר בשיר


# ---------------------------------------------------------------- שירה על פלייבק (הצליל)
def test_song_over_a_backing_track():
    voice = sing(bpm=120, repeats=1, vibrato=0.5)[0]
    t = np.arange(len(voice) + 3 * SR) / SR
    backing = np.stack([0.2 * np.sin(2 * np.pi * 220 * t), 0.2 * np.sin(2 * np.pi * 277 * t)], axis=1).astype(np.float32)
    song = Song(voice)
    song.backing = backing
    song.keep_stems = True
    out = song.make(load_styles()[0], quiet, Settings(transpose=3, modulate=True))
    assert out.shape[1] == 2 and abs(len(out) - len(backing)) <= SR and song.last_lead == 0.0
    music = song.last_stems["ליווי"]
    # הליווי הוא הפלייבק עצמו (בלי כלים של התוכנה): אותם שני צלילים, כל אחד בצד שלו
    spec = np.abs(np.fft.rfft(music[2 * SR: 4 * SR, 0] * np.hanning(2 * SR)))
    assert abs(np.argmax(spec) / 2.0 - 220) < 1
    assert song.last_tracks == [] and song.analysis.transpose == 0   # הקול נשאר בסולם של הפלייבק
    assert song.analysis.modulate_at is None
    assert np.std(song.last_stems["קול"]) > 0.01


# ---------------------------------------------------------------- המסכים
@pytest.fixture
def win(qapp, appdata, fake_sd, monkeypatch, tmp_path):
    from shir_studio.ui import MainWindow
    from shir_studio import recovery
    log = {"error": [], "info": [], "ask": [], "answer": True}
    monkeypatch.setattr(MainWindow, "error", lambda self, t: log["error"].append(t))
    monkeypatch.setattr(MainWindow, "_info", lambda self, title, text, b="": log["info"].append((title, text)))
    monkeypatch.setattr(MainWindow, "_ask", lambda self, title, text, *a: (log["ask"].append(title), log["answer"])[1])
    monkeypatch.setattr(MainWindow, "_docs", staticmethod(lambda *p: os.path.join(str(tmp_path), "docs", *p)))
    monkeypatch.setattr(MainWindow, "_reveal", staticmethod(lambda path: None))
    w = MainWindow()
    w.log, w.sd, w.tmp, w.qapp = log, fake_sd, tmp_path, qapp
    w.show()
    yield w
    w.dirty = False
    w.close()
    recovery.clear()


def wait(w, cond, timeout=180):
    t0 = time.time()
    while not cond():
        w.qapp.processEvents()
        time.sleep(0.01)
        assert time.time() - t0 < timeout, "המסך לא הגיע למצב המצופה"
        assert not w.log["error"], w.log["error"]
    w.qapp.processEvents()


@pytest.fixture(scope="module")
def voice():
    return sing(bpm=120, repeats=1, vibrato=0.5)[0][: 14 * SR]


def fake_models(monkeypatch, voice):
    """מודלים מדומים ומהירים: 'השירה' היא הקול הידוע."""
    def two(mix, progress=None, run=None):
        v = np.zeros_like(mix)
        k = min(len(mix), len(voice))
        v[:k] = voice[:k, None]
        return v, mix - v

    def stems(mix, progress=None, run=None):
        v, m = two(mix)
        return dict(zip(sep.STEM_NAMES, (v, m * 0.5, m * 0.3, m * 0.2)))
    monkeypatch.setattr(sep, "separate", two)
    monkeypatch.setattr(sep, "separate_stems", stems)


def test_tools_dialog_choices(qapp):
    from shir_studio.toolsview import ToolsDialog
    dlg = ToolsDialog(None)
    assert dlg.mode() == "two" and dlg.action is None
    dlg.mode_buttons["stems"].setChecked(True)
    dlg.b_separate.click()
    assert dlg.action == ("separate", "stems")
    dlg = ToolsDialog(None, stems=False)
    assert not dlg.mode_buttons["stems"].isEnabled()                 # בלי מודלי הכלים - האפשרות כבויה
    dlg.semitones.setValue(-2)
    dlg.tempo.setValue(90)
    dlg.b_shift.click()
    assert dlg.action == ("shift", -2, 90)
    dlg = ToolsDialog(None)
    dlg.b_sing.click()
    assert dlg.action == ("sing",)


def test_vocal_version_in_one_step(win, voice, monkeypatch):
    w = win
    fake_models(monkeypatch, voice)
    src = str(w.tmp / "שיר עם כלים.wav")
    save(src, np.stack([voice, voice], axis=1) * 0.5 + 0.1 * np.sin(np.arange(len(voice)) / 20)[:, None])
    w.separate_voice(src, mode="vocal")
    wait(w, lambda: w.stack.currentWidget() is w.done)
    assert w.styles[w.style_page.current()]["name"].startswith("ווקאלי")       # בלי כלי נגינה
    assert w.result is not None and "ההפרדה מוכנה" not in w.log["ask"]          # בלי שאלות בדרך
    assert sorted(os.listdir(os.path.join(str(w.tmp), "docs", "הפרדת קול"))) == [
        "שיר עם כלים - נגינה.mp3", "שיר עם כלים - שירה.mp3"]


def test_stems_and_several_songs(win, voice, monkeypatch):
    w = win
    fake_models(monkeypatch, voice)
    files = []
    for name in ("ראשון", "שני"):
        files.append(str(w.tmp / f"{name}.wav"))
        save(files[-1], np.stack([voice, voice], axis=1) * 0.5)
    broken = str(w.tmp / "שבור.wav")
    open(broken, "wb").write(b"not audio")
    w.separate_voice(files + [broken], mode="stems")
    wait(w, lambda: w.log["info"] and w.log["info"][-1][0] == "ההפרדה מוכנה")
    assert w.stack.currentWidget() is w.home
    got = sorted(os.listdir(os.path.join(str(w.tmp), "docs", "הפרדת קול")))
    assert got == sorted(f"{n} - {part}.mp3" for n in ("ראשון", "שני") for part in sep.STEM_NAMES)
    text = w.log["info"][-1][1]
    assert "8 קבצים" in text and "שבור.wav" in text                  # שיר שנכשל לא עוצר את השאר
    assert "ההפרדה מוכנה" not in w.log["ask"]                         # כמה שירים - רק שומרים


def test_playback_in_my_key(win):
    w = win
    src = str(w.tmp / "פלייבק.wav")
    save(src, np.stack([tone([440], 5), tone([440], 5)], axis=1))
    w.shift_playback(src, 0, 100)
    assert w.log["info"][-1][0] == "פלייבק" and w.stack.currentWidget() is w.home     # לא נבחר שינוי
    w.shift_playback(src, 2, 80)
    wait(w, lambda: w.log["info"][-1][0] == "הפלייבק מוכן")
    out = os.path.join(str(w.tmp), "docs", "פלייבק", "פלייבק (2 חצאי טונים למעלה, קצב 80%).mp3")
    y = load_stereo(out)
    assert abs(len(y) / SR - 5 / 0.8) < 0.15 and abs(pitch_of(y[:, 0]) - 440 * 2 ** (2 / 12)) < 2


def test_sing_over_a_playback(win, voice):
    w = win
    t = np.arange(len(voice) + 2 * SR) / SR
    playback = np.stack([0.2 * np.sin(2 * np.pi * 220 * t)] * 2, axis=1).astype(np.float32)
    src = str(w.tmp / "ניגון - נגינה.wav")
    save(src, playback)
    w.log["answer"] = False
    w.sing_on_playback(src)                                          # 'ביטול' בשאלת האוזניות
    assert w.stack.currentWidget() is w.home and w.recorder is None
    w.log["answer"] = True
    w.sing_on_playback(src)
    assert w.stack.currentWidget() is w.rec and isinstance(w.recorder, devices.Overdub)
    assert np.abs(w.recorder.backing[:3 * SR]).max() == 0            # שלוש שניות של ספירה, ואז הפלייבק
    lat = int(sum(w.sd.streams[-1].latency) * SR)
    mic = np.concatenate([np.zeros(3 * SR + lat, np.float32), voice])
    stream = w.sd.streams[-1]
    for i in range(0, len(mic), 1024):
        chunk = mic[i:i + 1024].reshape(-1, 1)
        stream.callback(chunk, np.zeros((len(chunk), 2), np.float32), len(chunk), None, None)
    w.countdown_end = 0
    w._tick()
    w.rec.stop.emit()
    wait(w, lambda: w.stack.currentWidget() is w.done)
    assert np.allclose(w.original[:SR], voice[:SR], atol=1e-6)       # השירה מיושרת לתחילת הפלייבק
    assert w.song.backing is not None and "פלייבק" in w.done.hint.text()
    assert abs(len(w.result) - len(playback)) <= SR
    spec = np.abs(np.fft.rfft(w.result[: 2 * SR, 0] * np.hanning(2 * SR)))
    assert abs(np.argmax(spec[: 600]) / 2.0 - 220) < 1               # הפלייבק עצמו נמצא בשיר המוכן
    w.done.other_style.emit()                                        # אין סגנון להחליף - הודעה, ונשארים
    assert w.stack.currentWidget() is w.done and w.log["info"][-1][0] == "סגנון ליווי"
    w.done.other_key.emit()                                          # 'התאמה אחרת' עדיין עובדת, עם אותו פלייבק
    wait(w, lambda: w.stack.currentWidget() is w.done and w.worker is not None and w.worker.isFinished())
    assert w.song.backing is not None
    w.trim()
    assert w.log["error"] and "פלייבק" in w.log["error"][-1]
    w.log["error"].clear()
    w.new_song()
    w.process(voice.copy())                                          # שיר חדש רגיל - בלי הפלייבק הקודם
    assert w.backing is None and w.song.backing is None and w.stack.currentWidget() is w.style_page
