"""בדיקות להפרדת הקול משיר מוכן, ולעדכון מתוך התוכנה."""
import hashlib
import io
import os
import time

import numpy as np
import pytest

from synth_voice import sing
from shir_studio.audio import separate as sep
from shir_studio.audio.fileio import SR, AudioError, save, load_stereo
from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles
from shir_studio import update

quiet = lambda p, m=None: None


def sdr(ref, est):
    return 10 * np.log10(np.sum(ref ** 2) / (np.sum((ref - est) ** 2) + 1e-12))


@pytest.fixture(scope="module")
def stems():
    """שיר שהתוכנה עצמה הכינה - כך ידועים בדיוק הקול והנגינה שבתוכו.
    הזמר שר עם ויברטו, כמו זמר אמיתי: המודל למד על קולות אנושיים, וצליל ישר לגמרי אינו נשמע לו כשירה."""
    song = Song(sing(bpm=120, repeats=1, vibrato=0.6)[0])
    song.keep_stems = True
    song.make(load_styles()[0], quiet, Settings())
    return song.last_stems["קול"], song.last_stems["ליווי"]


def test_transform_round_trip():
    rng = np.random.default_rng(0)
    x = rng.standard_normal((2, sep.CHUNK)).astype(np.float32)
    back = sep._istft(sep._stft(x))
    assert np.abs(back - x)[:, sep.TRIM:-sep.TRIM].max() < 1e-4
    assert sep._stft(x).shape == (2, sep.N_BINS, sep.DIM_T)


def test_separate_plumbing_with_fake_models():
    t = np.arange(SR * 14) / SR
    x = np.stack([0.3 * np.sin(2 * np.pi * 440 * t), 0.2 * np.sin(2 * np.pi * 660 * t)], axis=1).astype(np.float32)
    marks = []
    voice, music = sep.separate(x, progress=lambda p, m=None: marks.append(p), run=lambda inp: inp)
    assert voice.shape == music.shape == x.shape and voice.dtype == np.float32
    # מודל ש'מחזיר הכול': כל השיר הוא שירה (עד כדי תיקון העוצמה של המודל), בלי תפרים בין הקטעים
    assert np.abs(voice / sep.COMPENSATE - x)[SR:-SR].max() < 2e-3
    assert marks[0] == 0 and marks[-1] == 100 and marks == sorted(marks)
    voice, music = sep.separate(x[:, 0], run=lambda inp: inp * 0)                   # מודל ש'לא מוצא שירה'
    assert np.abs(voice).max() < 1e-6 and np.allclose(music[:, 0], x[:, 0], atol=1e-6)
    with pytest.raises(AudioError):
        sep.separate(x[: SR // 2], run=lambda inp: inp)


def test_real_model_pulls_the_voice_out(stems):
    assert sep.available(), "מודל ההפרדה או onnxruntime חסרים"
    voice, music = stems
    n = SR * 20
    voice, music = voice[:n], music[:n]
    mix = voice + music
    got_voice, got_music = sep.separate(mix)
    assert np.allclose(got_voice + got_music, mix, atol=1e-5)          # שום דבר לא הולך לאיבוד
    assert sdr(voice, got_voice) > sdr(voice, mix) + 10                # הקול נקי פי 10 ויותר מאשר בשיר המעורבב
    assert sdr(music, got_music) > sdr(music, mix) + 10
    # בקטע שהזמר שותק (המבוא) - כמעט שום דבר לא נשאר ב'שירה'
    intro = slice(int(0.5 * SR), int(2.5 * SR))
    assert np.std(mix[intro]) > 0 and np.std(got_voice[intro]) < 0.1 * np.std(mix[intro])


def test_separation_screen_saves_two_files_and_continues(qapp, appdata, fake_sd, monkeypatch, tmp_path, stems):
    from shir_studio.ui import MainWindow
    from shir_studio import recovery
    voice, music = stems
    n = SR * 12
    src = str(tmp_path / "שיר מוכן.wav")
    save(src, np.clip(voice[:n] + music[:n], -1, 1))
    log = {"error": [], "ask": [], "answer": True}
    monkeypatch.setattr(MainWindow, "error", lambda self, t: log["error"].append(t))
    monkeypatch.setattr(MainWindow, "_info", lambda self, *a: None)
    monkeypatch.setattr(MainWindow, "_ask", lambda self, title, *a: (log["ask"].append(title), log["answer"])[1])
    monkeypatch.setattr(MainWindow, "_docs", staticmethod(lambda *p: os.path.join(str(tmp_path), "docs", *p)))
    monkeypatch.setattr(MainWindow, "_reveal", staticmethod(lambda path: None))
    # מודל מדומה ומהיר: מחזיר את הקול הידוע של השיר
    monkeypatch.setattr(sep, "separate", lambda mix, progress=None, run=None: (
        voice[:len(mix)].astype(np.float32), (mix - voice[:len(mix)]).astype(np.float32)))
    w = MainWindow()
    try:
        from PySide6.QtWidgets import QFileDialog
        from shir_studio.toolsview import ToolsDialog
        monkeypatch.setattr(ToolsDialog, "exec", lambda self: (setattr(self, "action", ("separate", self.mode())), 1)[1])
        monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([], "")))
        w.home.separate.emit()                                           # בחירת הקובץ בוטלה - לא קורה כלום
        assert w.stack.currentWidget() is w.home
        monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([src], "")))
        w.home.separate.emit()
        t0 = time.time()
        while w.stack.currentWidget() is not w.style_page:
            qapp.processEvents(); time.sleep(0.01)
            assert time.time() - t0 < 120 and not log["error"], log["error"]
        folder = os.path.join(str(tmp_path), "docs", "הפרדת קול")
        files = sorted(os.listdir(folder))
        assert files == ["שיר מוכן - נגינה.mp3", "שיר מוכן - שירה.mp3"]
        assert len(load_stereo(os.path.join(folder, files[1]))) > SR * 10
        assert "ההפרדה מוכנה" in log["ask"]
        assert w.song is not None and abs(len(w.original) - n) < SR      # ממשיכים עם השירה לליווי חדש
        w.go_home()
        log["answer"] = False
        w.separate_voice(src)                                            # 'לא, זה מספיק' - נשארים במסך הפתיחה
        t0 = time.time()
        while log["ask"].count("ההפרדה מוכנה") < 2:
            qapp.processEvents(); time.sleep(0.01)
            assert time.time() - t0 < 120
        assert w.stack.currentWidget() is w.home
        monkeypatch.setattr(sep, "available", lambda: False)
        w.separate_voice(src)
        assert log["error"] and "לא זמינה" in log["error"][-1]
    finally:
        w.dirty = False
        w.close()
        recovery.clear()


# ---------------------------------------------------------------- עדכון מתוך התוכנה
PAYLOAD = b"MZ" + bytes(range(256)) * 4000
GOOD = hashlib.sha256(PAYLOAD).hexdigest()


def _release(**over):
    asset = {"name": "ShirStudio-Setup.exe", "size": len(PAYLOAD), "digest": "sha256:" + GOOD,
             "browser_download_url": update.TRUSTED + "latest/ShirStudio-Setup.exe"}
    asset.update(over)
    return {"name": "גרסה 1.0.99", "tag_name": "latest", "assets": [asset]}


def test_release_info_only_trusts_our_installer():
    info = update.release_info(lambda t: _release())
    assert info == {"version": "1.0.99", "url": update.TRUSTED + "latest/ShirStudio-Setup.exe",
                    "size": len(PAYLOAD), "sha256": GOOD}
    assert update.release_info(lambda t: _release(browser_download_url="https://example.com/x.exe")) is None
    assert update.release_info(lambda t: _release(digest="")) is None            # בלי טביעה - לא מתקינים
    assert update.release_info(lambda t: _release(name="other.exe")) is None
    assert update.release_info(lambda t: {"name": "גרסה 1.0.99"}) is None

    def offline(t):
        raise OSError
    assert update.release_info(offline) is None


def test_download_verifies_the_file(tmp_path):
    info = update.release_info(lambda t: _release())
    marks = []
    path = update.download(info, str(tmp_path), progress=marks.append, opener=lambda url, t: io.BytesIO(PAYLOAD))
    assert open(path, "rb").read() == PAYLOAD and marks[-1] == 100
    # קובץ ששונה בדרך, קובץ קטוע, והורדה שנכשלה - לא נשאר שום קובץ להתקנה
    for bad in (PAYLOAD[:-1] + b"x", PAYLOAD[:1000]):
        folder = str(tmp_path / f"bad{len(bad)}{bad[-1]}")
        with pytest.raises(update.UpdateError):
            update.download(info, folder, opener=lambda url, t, b=bad: io.BytesIO(b))
        assert os.listdir(folder) == []

    def broken(url, t):
        raise OSError("אין אינטרנט")
    with pytest.raises(update.UpdateError):
        update.download(info, str(tmp_path / "off"), opener=broken)
    with pytest.raises(update.UpdateError):
        update.download(dict(info, url="https://example.com/evil.exe"), str(tmp_path / "evil"),
                        opener=lambda url, t: io.BytesIO(PAYLOAD))
    calls = []
    update.install(path, launch=calls.append)
    assert calls == [[path, "/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS"]]


def test_update_from_inside_the_app(qapp, appdata, fake_sd, monkeypatch, tmp_path):
    from shir_studio.ui import MainWindow
    from shir_studio import recovery
    log = {"ask": [], "launched": []}
    monkeypatch.setattr(MainWindow, "error", lambda self, t: None)
    monkeypatch.setattr(MainWindow, "_info", lambda self, *a: None)
    monkeypatch.setattr(MainWindow, "_ask", lambda self, title, text, *a: (log["ask"].append((title, text)), True)[1])
    monkeypatch.setattr(update, "latest_version", lambda *a, **k: "9.9.9")
    monkeypatch.setattr(update, "can_install", lambda: True)
    monkeypatch.setattr(update, "release_info", lambda *a, **k: {
        "version": "9.9.9", "url": update.TRUSTED + "latest/ShirStudio-Setup.exe",
        "size": len(PAYLOAD), "sha256": GOOD})
    monkeypatch.setattr(update, "_open", lambda url, t: io.BytesIO(PAYLOAD))
    monkeypatch.setattr(update, "install", lambda path, launch=None: log["launched"].append(path))
    w = MainWindow()
    try:
        w.home.check_update.emit()
        t0 = time.time()
        while not log["launched"]:
            qapp.processEvents(); time.sleep(0.01)
            assert time.time() - t0 < 60
        assert "להוריד ולהתקין" in log["ask"][0][1]
        assert open(log["launched"][0], "rb").read() == PAYLOAD
        qapp.processEvents()
        assert not w.isVisible()                                          # התוכנה נסגרה כדי להתעדכן
    finally:
        w.dirty = False
        w.close()
        recovery.clear()
