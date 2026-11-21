"""המסך הראשי של התוכנה. הכול בעברית, מימין לשמאל, כפתורים גדולים."""
import os
import time
import traceback

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QStandardPaths
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QStackedWidget, QProgressBar, QFileDialog, QMessageBox,
)

from . import APP_NAME
from .audio.fileio import load, save, AudioError, SR
from .audio.devices import Recorder, Player
from .audio.denoise import denoise
from .log import log_error

STYLE = """
QWidget { font-family: 'Segoe UI', 'Arial'; font-size: 20px; color: #1d2733; background: #f6f3ec; }
QLabel#title { font-size: 40px; font-weight: bold; color: #24466b; }
QLabel#big { font-size: 64px; font-weight: bold; color: #b0322a; }
QLabel#hint { font-size: 22px; color: #4a5664; }
QPushButton { border: none; border-radius: 18px; padding: 18px 28px; font-size: 26px; font-weight: bold;
              background: #24466b; color: white; min-height: 60px; }
QPushButton:hover { background: #2f5b8a; }
QPushButton:disabled { background: #a8b3bf; }
QPushButton#huge { font-size: 30px; padding: 10px; min-height: 150px; min-width: 380px; }
QPushButton#red { background: #b0322a; }
QPushButton#red:hover { background: #cc3d33; }
QPushButton#green { background: #2c7a3f; }
QPushButton#green:hover { background: #369249; }
QPushButton#light { background: #dfe5ec; color: #24466b; }
QProgressBar { border: 2px solid #24466b; border-radius: 14px; height: 40px; text-align: center;
               font-size: 22px; background: white; }
QProgressBar::chunk { background: #2c7a3f; border-radius: 12px; }
"""


def big_button(text, name=None):
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    b.setCursor(Qt.PointingHandCursor)
    return b


def label(text, name=None):
    l = QLabel(text)
    l.setAlignment(Qt.AlignCenter)
    l.setWordWrap(True)
    if name:
        l.setObjectName(name)
    return l


class Worker(QThread):
    progress = Signal(int)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.finished_ok.emit(self.fn(self.progress.emit))
        except AudioError as e:
            self.failed.emit(str(e))
        except Exception:
            log_error(traceback.format_exc())
            self.failed.emit("משהו השתבש בזמן הכנת השיר.\nנסה שוב. אם זה חוזר, הפעל מחדש את התוכנה.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(STYLE)
        self.resize(900, 650)
        self.recorder = None
        self.player = Player()
        self.original = None
        self.result = None
        self.worker = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home = self._build_home()
        self.rec = self._build_record()
        self.work = self._build_work()
        self.done = self._build_done()
        for w in (self.home, self.rec, self.work, self.done):
            self.stack.addWidget(w)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    # ---------- מסכים ----------
    def _page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(40, 30, 40, 30)
        v.setSpacing(22)
        return w, v

    def _build_home(self):
        w, v = self._page()
        v.addWidget(label(APP_NAME, "title"))
        v.addWidget(label("שר שיר - ואנחנו נהפוך אותו לשיר מוכן", "hint"))
        v.addStretch()
        h = QHBoxLayout()
        h.setSpacing(30)
        b1 = big_button("🎤  הקלט שיר", "huge")
        b1.setObjectName("huge")
        b1.clicked.connect(self.start_recording)
        b2 = big_button("📁  בחר קובץ\nמהמחשב", "huge")
        b2.setStyleSheet("background:#2c7a3f;")
        b2.clicked.connect(self.choose_file)
        h.addStretch(); h.addWidget(b1); h.addWidget(b2); h.addStretch()
        v.addLayout(h)
        v.addStretch()
        return w

    def _build_record(self):
        w, v = self._page()
        v.addWidget(label("מקליט... שיר עכשיו", "title"))
        self.rec_time = label("0:00", "big")
        v.addWidget(self.rec_time)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        v.addWidget(label("הפס הירוק זז כשהמיקרופון שומע אותך", "hint"))
        v.addWidget(self.level)
        v.addStretch()
        h = QHBoxLayout()
        stop = big_button("⏹  סיום", "red")
        stop.setMinimumHeight(110)
        stop.clicked.connect(self.stop_recording)
        cancel = big_button("ביטול", "light")
        cancel.clicked.connect(self.cancel_recording)
        h.addWidget(stop, 3); h.addWidget(cancel, 1)
        v.addLayout(h)
        return w

    def _build_work(self):
        w, v = self._page()
        v.addStretch()
        v.addWidget(label("מכין את השיר...", "title"))
        v.addWidget(label("זה ייקח רגע. אין צורך ללחוץ על כלום.", "hint"))
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setFormat("%p%")
        v.addWidget(self.bar)
        v.addStretch()
        return w

    def _build_done(self):
        w, v = self._page()
        v.addWidget(label("השיר מוכן! ✔", "title"))
        v.addWidget(label("לחץ כדי להאזין ולהשוות", "hint"))
        b_res = big_button("▶  האזן לשיר המוכן", "green")
        b_res.setMinimumHeight(90)
        b_res.clicked.connect(lambda: self._play(self.result))
        b_org = big_button("▶  האזן להקלטה המקורית", "light")
        b_org.clicked.connect(lambda: self._play(self.original))
        b_stop = big_button("⏹  עצור השמעה", "light")
        b_stop.clicked.connect(self.player.stop)
        v.addWidget(b_res); v.addWidget(b_org); v.addWidget(b_stop)
        v.addStretch()
        h = QHBoxLayout()
        b_save = big_button("💾  שמור", None)
        b_save.setMinimumHeight(90)
        b_save.clicked.connect(self.save_result)
        b_new = big_button("שיר חדש", "light")
        b_new.clicked.connect(self.go_home)
        h.addWidget(b_save, 3); h.addWidget(b_new, 1)
        v.addLayout(h)
        return w

    # ---------- פעולות ----------
    def error(self, text):
        box = QMessageBox(self)
        box.setLayoutDirection(Qt.RightToLeft)
        box.setWindowTitle("שים לב")
        box.setIcon(QMessageBox.Warning)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("הבנתי")
        box.exec()

    def go_home(self):
        self.player.stop()
        self.stack.setCurrentWidget(self.home)

    def start_recording(self):
        self.recorder = Recorder()
        try:
            self.recorder.start()
        except AudioError as e:
            self.error(str(e))
            return
        self.rec_start = time.time()
        self.rec_time.setText("0:00")
        self.stack.setCurrentWidget(self.rec)
        self.timer.start(100)

    def _tick(self):
        s = int(time.time() - self.rec_start)
        self.rec_time.setText(f"{s // 60}:{s % 60:02d}")
        self.level.setValue(min(100, int(self.recorder.level * 400)))
        if s >= 15 * 60:
            self.stop_recording()

    def cancel_recording(self):
        self.timer.stop()
        if self.recorder:
            self.recorder.stop()
        self.go_home()

    def stop_recording(self):
        self.timer.stop()
        data = self.recorder.stop()
        if len(data) < SR * 2:
            self.error("ההקלטה קצרה מדי.\nלחץ 'הקלט שיר' ושיר לפחות כמה שניות.")
            self.go_home()
            return
        if np.max(np.abs(data)) < 0.003:
            self.error("לא שמעתי קול בהקלטה.\nבדוק שהמיקרופון מחובר ודבר קרוב אליו.")
            self.go_home()
            return
        self.process(data)

    def choose_file(self):
        start = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
        path, _ = QFileDialog.getOpenFileName(self, "בחר שיר", start,
                                              "קבצי שיר (*.mp3 *.wav *.flac *.ogg *.m4a);;כל הקבצים (*.*)")
        if not path:
            return
        try:
            data = load(path)
        except AudioError as e:
            self.error(str(e))
            return
        self.process(data)

    def process(self, data):
        self.original = data
        self.bar.setValue(0)
        self.stack.setCurrentWidget(self.work)
        self.worker = Worker(lambda p: denoise(data, progress=p))
        self.worker.progress.connect(self.bar.setValue)
        self.worker.finished_ok.connect(self._processed)
        self.worker.failed.connect(lambda m: (self.error(m), self.go_home()))
        self.worker.start()

    def _processed(self, result):
        self.result = result
        self.bar.setValue(100)
        self.stack.setCurrentWidget(self.done)

    def _play(self, data):
        try:
            self.player.play(data)
        except AudioError as e:
            self.error(str(e))

    def save_result(self):
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.MusicLocation), "השיר שלי.mp3")
        path, _ = QFileDialog.getSaveFileName(self, "שמור את השיר", start, "קובץ MP3 (*.mp3)")
        if not path:
            return
        if not path.lower().endswith(".mp3"):
            path += ".mp3"
        try:
            save(path, self.result)
        except AudioError as e:
            self.error(str(e))
            return
        box = QMessageBox(self)
        box.setLayoutDirection(Qt.RightToLeft)
        box.setWindowTitle("נשמר")
        box.setText(f"השיר נשמר בהצלחה!\n\n{path}")
        box.addButton("מעולה", QMessageBox.AcceptRole)
        box.exec()
