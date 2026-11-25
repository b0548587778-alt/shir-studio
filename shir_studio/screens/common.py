"""דברים משותפים לכל המסכים: עיצוב, כפתורים גדולים, הודעות, ועבודה ברקע."""
from ..i18n import tx, is_rtl
from ..i18n import direction
import traceback

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox

from ..audio.fileio import AudioError
from ..log import log_error

STYLE = """
QWidget { font-family: 'Segoe UI', 'Arial'; font-size: 20px; color: #1c2533; background: #f7f5f0; }
QLabel { background: transparent; }
QLabel#title { font-size: 38px; font-weight: bold; color: #1f3a5f; }
QLabel#big { font-size: 64px; font-weight: bold; color: #b3392f; }
QLabel#hint { font-size: 21px; color: #55606e; }
QLabel#tiny { font-size: 15px; color: #717c89; }
QPushButton { border: none; border-radius: 16px; padding: 16px 26px; font-size: 25px; font-weight: bold;
              background: #1f3a5f; color: white; min-height: 58px; }
QPushButton:hover { background: #2a4d7c; }
QPushButton:pressed { background: #182e4c; }
QPushButton:disabled { background: #b4bcc6; color: #eef1f4; }
QPushButton:focus { outline: none; }
QPushButton#huge { font-size: 30px; padding: 10px; min-height: 160px; min-width: 380px; border-radius: 24px; }
QPushButton#red { background: #b3392f; }
QPushButton#red:hover { background: #c9463b; }
QPushButton#green { background: #2e7d4f; }
QPushButton#green:hover { background: #38935e; }
QPushButton#green:pressed { background: #256640; }
QPushButton#light { background: white; color: #1f3a5f; border: 2px solid #ddd6c8; }
QPushButton#light:hover { background: #fbf6e9; border-color: #c8962e; }
QPushButton#light:checked { background: #fdf3d7; color: #5a3d00; border-color: #c8962e; }
QPushButton#small { background: white; color: #1f3a5f; font-size: 18px; min-height: 40px; font-weight: normal;
                    padding: 6px 8px; border-radius: 12px; border: 1px solid #ddd6c8; }
QPushButton#small:hover { background: #fbf6e9; border-color: #c8962e; }
QPushButton#small:disabled { background: #f1eee7; color: #aab2bc; }
QPushButton#link { background: transparent; color: #1f3a5f; font-size: 15px; font-weight: normal;
                   min-height: 24px; padding: 2px 8px; text-decoration: underline; }
QPushButton#link:hover { color: #c8962e; background: transparent; }
QPushButton#style { background: white; color: #1c2533; border: 2px solid #ddd6c8; font-size: 24px;
                    min-height: 72px; text-align: center; padding: 6px; border-radius: 16px; }
QPushButton#style:hover { border-color: #c8962e; background: #fffdf7; }
QPushButton#harm { background: white; color: #1f3a5f; border: 2px dashed #b9c2cd; font-size: 22px; min-height: 56px; }
QPushButton#harm:hover { border-color: #c8962e; background: #fffdf7; }
QPushButton#harm:checked { background: #fdf3d7; border: 2px solid #c8962e; color: #5a3d00; }
QCheckBox { font-size: 20px; background: transparent; }
QSpinBox, QLineEdit, QPlainTextEdit, QComboBox { font-size: 20px; padding: 6px 10px; background: white;
                    border: 2px solid #ddd6c8; border-radius: 10px; }
QSpinBox:focus, QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #c8962e; }
QPushButton#style:checked { border: 3px solid #2e7d4f; background: #e8f4ec; }
QProgressBar { border: 2px solid #ddd6c8; border-radius: 16px; background: white; height: 34px; text-align: center;
               font-weight: bold; }
QProgressBar::chunk { background: #2e7d4f; border-radius: 13px; }
QSlider::groove:horizontal { height: 10px; background: #ddd6c8; border-radius: 5px; }
QSlider::handle:horizontal { width: 26px; margin: -9px 0; border-radius: 13px; background: #1f3a5f; }
QScrollBar:vertical { width: 14px; background: transparent; }
QScrollBar::handle:vertical { background: #cfc8ba; border-radius: 7px; min-height: 40px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #1f3a5f; color: white; border: none; padding: 6px 10px; font-size: 16px; }
QWidget#steps { background: white; border-bottom: 2px solid #e6e0d3; }
QLabel#step { font-size: 18px; color: #8a94a0; padding: 10px 6px; }
QLabel#step[state="now"] { color: #1f3a5f; font-weight: bold; }
QLabel#step[state="done"] { color: #2e7d4f; }
QLabel#stepsep { color: #cfc8ba; font-size: 18px; }
QFrame#card { background: white; border: 2px solid #e6e0d3; border-radius: 18px; }
"""


def big_button(text, name=None):
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    b.setCursor(Qt.PointingHandCursor)
    return b


def small_button(text, tip=None):
    b = big_button(text, "small")
    if tip:
        b.setToolTip(tip)
    return b


def label(text, name=None):
    l = QLabel(text)
    l.setAlignment(Qt.AlignCenter)
    l.setWordWrap(True)
    if name:
        l.setObjectName(name)
    return l


STEPS = (tx("הקלטה או קובץ"), tx("בחירת סגנון"), tx("השיר מוכן"))


class StepBar(QWidget):
    """פס שלושת הצעדים בראש החלון: איפה אני עכשיו, ומה נשאר."""

    def __init__(self):
        super().__init__()
        self.setObjectName("steps")
        self.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(20, 0, 20, 0)
        h.addStretch()
        self.labels = []
        for i, text in enumerate(STEPS):
            if i:
                sep = QLabel("\u2190" if is_rtl() else "\u2192")
                sep.setObjectName("stepsep")
                h.addWidget(sep)
            l = QLabel()
            l.setObjectName("step")
            self.labels.append((l, text))
            h.addWidget(l)
        h.addStretch()
        self.set_step(0)

    def set_step(self, now):
        """now: 0, 1 או 2 - הצעד הנוכחי."""
        self.now = now
        for i, (l, text) in enumerate(self.labels):
            state = "done" if i < now else ("now" if i == now else "later")
            l.setText(("✔  " if i < now else f"{i + 1}.  ") + text)
            l.setProperty("state", state)
            l.style().unpolish(l)
            l.style().polish(l)


def page():
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(40, 26, 40, 26)
    v.setSpacing(18)
    return w, v


def fmt_time(sec):
    sec = int(max(0, sec))
    return f"{sec // 60}:{sec % 60:02d}"


def warn(parent, text):
    box = QMessageBox(parent)
    box.setLayoutDirection(direction())
    box.setWindowTitle(tx("שים לב"))
    box.setIcon(QMessageBox.Warning)
    box.setText(text)
    box.addButton(tx("הבנתי"), QMessageBox.AcceptRole)
    box.exec()


def info(parent, title, text, button=tx("אישור")):
    box = QMessageBox(parent)
    box.setLayoutDirection(direction())
    box.setWindowTitle(title)
    box.setText(text)
    box.addButton(button, QMessageBox.AcceptRole)
    box.exec()


def ask(parent, title, text, yes=tx("כן"), no=tx("לא")):
    """שאלה עם שני כפתורים בעברית. מחזיר True אם נבחר 'כן'."""
    box = QMessageBox(parent)
    box.setLayoutDirection(direction())
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Question)
    box.setText(text)
    b_yes = box.addButton(yes, QMessageBox.AcceptRole)
    box.addButton(no, QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is b_yes


class Worker(QThread):
    """עבודה ארוכה ברקע, כדי שהמסך לא ייתקע."""
    progress = Signal(int)
    message = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, fail_text=tx("משהו השתבש בזמן הכנת השיר.\nנסה שוב. אם זה חוזר, הפעל מחדש את התוכנה.")):
        super().__init__()
        self.fn = fn
        self.fail_text = fail_text

    def run(self):
        try:
            def report(p, msg=None):
                self.progress.emit(int(p))
                if msg:
                    self.message.emit(msg)
            self.finished_ok.emit(self.fn(report))
        except AudioError as e:
            self.failed.emit(str(e))
        except MemoryError:
            log_error(traceback.format_exc())
            self.failed.emit(tx("השיר ארוך מדי בשביל הזיכרון של המחשב.\n"
                             "נסו לסגור תוכנות אחרות, או לחלק את השיר לשני חלקים."))
        except Exception:
            log_error(traceback.format_exc())
            self.failed.emit(self.fail_text)
