"""המסך הראשי של התוכנה. הכול בעברית, מימין לשמאל, כפתורים גדולים."""
import os
import time
import traceback

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QStandardPaths
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QStackedWidget, QProgressBar, QFileDialog, QMessageBox, QGridLayout, QButtonGroup, QSlider,
)

from . import APP_NAME
from .audio.fileio import load, save, AudioError, SR
from .audio.devices import Recorder, Player
from .pipeline import Song, Settings
from .advanced import AdvancedDialog
from .music.styles import load_styles
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
QPushButton#style { background: white; color: #1d2733; border: 3px solid #c9d2dc; font-size: 24px;
                    min-height: 72px; text-align: center; padding: 6px; }
QPushButton#harm { background: white; color: #24466b; border: 3px dashed #9fb0c2; font-size: 22px; min-height: 56px; }
QPushButton#harm:checked { background: #fff4d6; border: 3px solid #d39b1e; color: #5a3d00; }
QSlider::groove:horizontal { height: 12px; background: #dfe5ec; border-radius: 6px; }
QSlider::handle:horizontal { width: 26px; margin: -8px 0; background: #2c7a3f; border-radius: 13px; }
QSlider::sub-page:horizontal { background: #2c7a3f; border-radius: 6px; }
QPushButton#style:checked { border: 4px solid #2c7a3f; background: #e6f3e9; }
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
    message = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            def report(p, msg=None):
                self.progress.emit(int(p))
                if msg:
                    self.message.emit(msg)
            self.finished_ok.emit(self.fn(report))
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
        self.resize(1000, 740)
        self.recorder = None
        self.player = Player()
        self.original = None
        self.result = None
        self.worker = None
        self.song = None
        self.styles = load_styles()
        self.settings = Settings()
        self.save_extras = False
        self.save_fmt = "mp3"
        self.style_index = 0

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home = self._build_home()
        self.rec = self._build_record()
        self.style_page = self._build_styles()
        self.work = self._build_work()
        self.done = self._build_done()
        for w in (self.home, self.rec, self.style_page, self.work, self.done):
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

    def _build_styles(self):
        w, v = self._page()
        v.addWidget(label("בחר סגנון ליווי", "title"))
        grid = QGridLayout()
        grid.setSpacing(16)
        self.style_group = QButtonGroup(self)
        self.style_group.setExclusive(True)
        for i, st in enumerate(self.styles):
            b = QPushButton(f"{st['name']}\n{st.get('description', '')}")
            b.setObjectName("style")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton#style { font-size: 20px; }")
            self.style_group.addButton(b, i)
            grid.addWidget(b, i // 2, i % 2)
            if i == 0:
                b.setChecked(True)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        self.harm_btn = QPushButton("🎶  הוסף קול שני (הרמוניה) - כמו מקהלה")
        self.harm_btn.setObjectName("harm")
        self.harm_btn.setCheckable(True)
        self.harm_btn.setCursor(Qt.PointingHandCursor)
        self.harm_btn.toggled.connect(lambda on: setattr(self.settings, "harmony",
                                                         ("auto" if on else "off")))
        v.addWidget(self.harm_btn)
        v.addStretch()
        h = QHBoxLayout()
        go = big_button("✨  הכן את השיר", "green")
        go.setMinimumHeight(100)
        go.clicked.connect(self.make_song)
        back = big_button("חזרה", "light")
        back.clicked.connect(self.go_home)
        adv = big_button("⚙", "light")
        adv.setToolTip("אפשרויות מתקדמות")
        adv.clicked.connect(lambda: self.open_advanced(remake=False))
        h.addWidget(go, 3); h.addWidget(back, 1); h.addWidget(adv)
        v.addLayout(h)
        return w

    def _build_work(self):
        w, v = self._page()
        v.addStretch()
        self.work_title = label("מכין את השיר...", "title")
        v.addWidget(self.work_title)
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
        self.done_hint = label("לחץ כדי להאזין ולהשוות", "hint")
        v.addWidget(self.done_hint)
        pr = QHBoxLayout()
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderReleased.connect(self._seek)
        self.pos_label = QLabel("0:00")
        self.pos_label.setMinimumWidth(110)
        pr.addWidget(self.pos_label); pr.addWidget(self.seek, 1)
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._update_pos)
        self.play_timer.start(200)
        b_res = big_button("▶  האזן לשיר המוכן", "green")
        b_res.setMinimumHeight(90)
        b_res.clicked.connect(lambda: self._play(self.result))
        b_org = big_button("▶  האזן להקלטה המקורית", "light")
        b_org.clicked.connect(lambda: self._play(self.original))
        b_stop = big_button("⏹  עצור השמעה", "light")
        b_stop.clicked.connect(self.player.stop)
        b_other = big_button("🎵  נסה סגנון ליווי אחר", "light")
        b_other.clicked.connect(self.choose_style)
        b_key = big_button("🔄  הליווי לא מתאים לשיר?\nנסה התאמה אחרת", "light")
        b_key.clicked.connect(self.other_key)
        h2 = QHBoxLayout()
        h2.addWidget(b_org); h2.addWidget(b_stop)
        h3 = QHBoxLayout()
        h3.addWidget(b_other); h3.addWidget(b_key)
        v.addWidget(b_res); v.addLayout(pr); v.addLayout(h2); v.addLayout(h3)
        v.addStretch()
        h = QHBoxLayout()
        b_save = big_button("💾  שמור", None)
        b_save.setMinimumHeight(90)
        b_save.clicked.connect(self.save_result)
        b_new = big_button("שיר חדש", "light")
        b_new.clicked.connect(self.go_home)
        b_adv = big_button("⚙  מתקדם", "light")
        b_adv.clicked.connect(lambda: self.open_advanced(remake=True))
        h.addWidget(b_save, 3); h.addWidget(b_new, 1); h.addWidget(b_adv, 1)
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
        self._keep_recording(data)
        self.process(data)

    def _keep_recording(self, data):
        """שומר עותק של ההקלטה המקורית בתיקייה 'מסמכים\\שיר סטודיו\\הקלטות'."""
        try:
            d = os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation),
                             "שיר סטודיו", "הקלטות")
            os.makedirs(d, exist_ok=True)
            save(os.path.join(d, time.strftime("הקלטה %Y-%m-%d %H-%M-%S.mp3")), data)
        except Exception:
            log_error(traceback.format_exc())

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
        self.song = Song(data)
        self.settings.key = None
        self.settings.chords_text = ""
        self.choose_style()

    def choose_style(self):
        self.player.stop()
        self.stack.setCurrentWidget(self.style_page)

    def open_advanced(self, remake):
        info = self.song.info() if (self.song and self.song.analysis) else None
        dlg = AdvancedDialog(self, self.settings, info, self.save_extras, self.save_fmt)
        r = dlg.exec()
        if r == 1:
            self.settings = dlg.settings()
            self.save_extras = dlg.extras.isChecked()
            self.save_fmt = dlg.fmt.currentData()
        elif r == 2:
            self.settings, self.save_extras, self.save_fmt = Settings(), False, "mp3"
        else:
            return
        self.harm_btn.blockSignals(True)
        self.harm_btn.setChecked(self.settings.harmony != "off")
        self.harm_btn.blockSignals(False)
        if remake and self.song:
            self.make_song()

    def other_key(self):
        self.make_song(change_key=True)

    def make_song(self, change_key=False):
        st = self.styles[max(0, self.style_group.checkedId())]
        self.bar.setValue(0)
        self.work_title.setText("מכין את השיר...")
        self.stack.setCurrentWidget(self.work)
        song = self.song
        settings = self.settings
        if change_key:
            settings.key = None          # 'התאמה אחרת' עוקפת סולם שנקבע ידנית
            settings.chords_text = ""

        def job(p):
            if change_key:
                p(5, "מחפש התאמה אחרת...")
                song.next_key()
            return song.make(st, p, settings)
        self.worker = Worker(job)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.message.connect(self.work_title.setText)
        self.worker.finished_ok.connect(lambda r: self._processed(r, st))
        self.worker.failed.connect(lambda m: (self.error(m), self.go_home()))
        self.worker.start()

    def _processed(self, result, st):
        self.result = result
        self.bar.setValue(100)
        hint = f"סגנון: {st['name']}"
        if not self.song.info()["steady"]:
            hint += "\nהשיר מושר בקצב חופשי, לכן הליווי רך ובלי תופים."
        self.done_hint.setText(hint)
        self.stack.setCurrentWidget(self.done)

    def _play(self, data, start=0.0):
        try:
            self.player.play(data, start)
        except AudioError as e:
            self.error(str(e))

    @staticmethod
    def _fmt(sec):
        sec = int(sec)
        return f"{sec // 60}:{sec % 60:02d}"

    def _update_pos(self):
        if self.stack.currentWidget() is not self.done or self.seek.isSliderDown():
            return
        p = self.player.position()
        total = self.player.length() or (len(self.result) / SR if self.result is not None else 0)
        if p is None:
            self.pos_label.setText(f"{self._fmt(0)} / {self._fmt(total)}")
            return
        self.seek.setValue(int(1000 * p / max(total, 1e-6)))
        self.pos_label.setText(f"{self._fmt(p)} / {self._fmt(total)}")

    def _seek(self):
        data = self.player.data if self.player.data is not None else self.result
        if data is None:
            return
        self._play(data, self.seek.value() / 1000 * len(data) / SR)

    def save_result(self):
        ext = self.save_fmt
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.MusicLocation), f"השיר שלי.{ext}")
        flt = "קובץ MP3 (*.mp3)" if ext == "mp3" else "קובץ WAV (*.wav)"
        path, _ = QFileDialog.getSaveFileName(self, "שמור את השיר", start, flt)
        if not path:
            return
        if not path.lower().endswith("." + ext):
            path += "." + ext
        extra = []
        try:
            save(path, self.result)
            if self.save_extras:
                folder = os.path.dirname(path)
                base = os.path.splitext(os.path.basename(path))[0]
                extra = self.song.export_extras(folder, base)
        except AudioError as e:
            self.error(str(e))
            return
        box = QMessageBox(self)
        box.setLayoutDirection(Qt.RightToLeft)
        box.setWindowTitle("נשמר")
        msg = f"השיר נשמר בהצלחה!\n\n{path}"
        if extra:
            msg += "\n\nנשמרו גם:\n" + "\n".join(os.path.basename(p) for p in extra)
        box.setText(msg)
        box.addButton("מעולה", QMessageBox.AcceptRole)
        box.exec()
