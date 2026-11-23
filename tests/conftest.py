import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")       # המסכים נבדקים בלי תצוגה
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(Qt.RightToLeft)
    return app


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    """תיקיית הנתונים של התוכנה (העדפות, גיבוי) - זמנית לכל בדיקה."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


class FakeStream:
    latency = (0.010, 0.020)

    def __init__(self, callback=None, **kw):
        self.callback, self.kw, self.active = callback, kw, False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def close(self):
        pass


class FakeSD:
    """כרטיס קול מדומה - בבדיקות אין מיקרופון ורמקולים."""

    def __init__(self):
        self.streams, self.played = [], []

    def Stream(self, **kw):
        self.streams.append(FakeStream(**kw))
        return self.streams[-1]

    InputStream = OutputStream = Stream

    def query_devices(self, kind=None):
        return {"name": "fake"}

    def play(self, data, sr):
        self.played.append(data)

    def stop(self):
        pass


@pytest.fixture
def fake_sd(monkeypatch):
    from shir_studio.audio import devices
    sd = FakeSD()
    monkeypatch.setattr(devices, "_sd", lambda: sd)
    return sd
