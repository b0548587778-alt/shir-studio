"""בדיקת מיקרופון לפני ההקלטה: שרים כמה שניות, והתוכנה אומרת אם חלש מדי, חזק מדי או רועש."""
from .i18n import tx
from .i18n import direction
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QProgressBar

from .audio.devices import Recorder, mic_verdict
from .audio.fileio import AudioError
from .trimview import CSS

COLORS = {"good": "#2c7a3f", "loud": "#b0322a", "silent": "#b0322a", "quiet": "#8a6d00", "noisy": "#8a6d00"}
MIN_TICKS = 25             # מודדים לפחות שתי שניות וחצי לפני שאומרים משהו


class MicMeter:
    """אוסף את מה שהמיקרופון שומע, ונותן חוות דעת."""

    def __init__(self):
        self.levels, self.peak = [], 0.0

    def add(self, level, peak):
        self.levels.append(float(level))
        self.peak = max(self.peak, float(peak))

    def verdict(self):
        if len(self.levels) < MIN_TICKS:
            return None
        lv = np.array(self.levels)
        return mic_verdict(self.peak, float(np.percentile(lv, 90)), float(np.percentile(lv, 10)))


class MicDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tx("בדיקת מיקרופון"))
        self.setLayoutDirection(direction())
        self.setStyleSheet(CSS + "QProgressBar { min-height: 34px; }")
        self.meter = MicMeter()
        self.recorder = Recorder()
        self.failed = None
        v = QVBoxLayout(self)
        lab = QLabel(tx("שיר כמה שניות בקול הרגיל שלך, מהמקום שבו תקליט - ואז שתוק רגע.\n"
                     "התוכנה תגיד אם העוצמה מתאימה."))
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        v.addWidget(self.bar)
        self.result = QLabel(tx("מקשיב..."))
        self.result.setWordWrap(True)
        self.result.setAlignment(Qt.AlignCenter)
        self.result.setStyleSheet("font-size:24px; font-weight:bold; padding:14px;")
        v.addWidget(self.result, 1)
        again = QPushButton(tx("בדוק שוב"))
        again.clicked.connect(self.restart)
        close = QPushButton(tx("סגור"))
        close.clicked.connect(self.accept)
        v.addWidget(again)
        v.addWidget(close)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.resize(560, 400)
        try:
            self.recorder.start()
            self.timer.start(100)
        except AudioError as e:
            self.recorder.stop()
            self.failed = str(e)
            self.result.setText(self.failed)
            self.result.setStyleSheet("font-size:22px; color:#b0322a; padding:14px;")

    def restart(self):
        self.meter = MicMeter()
        self.result.setText(tx("מקשיב..."))
        self.result.setStyleSheet("font-size:24px; font-weight:bold; padding:14px;")

    def tick(self):
        r = self.recorder
        self.bar.setValue(min(100, int(r.level * 400)))
        self.meter.add(r.level, r.peak)
        r.reset()                                          # לא שומרים כלום - רק מודדים
        v = self.meter.verdict()
        if v:
            self.result.setText(v[1])
            self.result.setStyleSheet(f"font-size:24px; font-weight:bold; padding:14px; color:{COLORS[v[0]]};")

    def done(self, r):
        self.timer.stop()
        try:
            self.recorder.stop()
        except Exception:
            pass
        super().done(r)
