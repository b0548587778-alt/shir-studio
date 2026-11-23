"""דברים משותפים לכל המסכים: עיצוב, כפתורים גדולים, הודעות, ועבודה ברקע."""
import traceback

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QMessageBox

from ..audio.fileio import AudioError
from ..log import log_error

STYLE = """
QWidget { font-family: 'Segoe UI', 'Arial'; font-size: 20px; color: #1d2733; background: #f6f3ec; }
QLabel#title { font-size: 40px; font-weight: bold; color: #24466b; }
QLabel#big { font-size: 64px; font-weight: bold; color: #b0322a; }
QLabel#hint { font-size: 22px; color: #4a5664; }
QLabel#tiny { font-size: 15px; color: #6a7684; }
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
QPushButton#light:hover { background: #cfd8e2; }
QPushButton#light:checked { background: #fff4d6; color: #5a3d00; }
QPushButton#small { background: #dfe5ec; color: #24466b; font-size: 18px; min-height: 40px;
                    padding: 6px 8px; border-radius: 12px; }
QPushButton#small:hover { background: #cfd8e2; }
QPushButton#small:disabled { background: #e9edf1; color: #a8b3bf; }
QPushButton#link { background: transparent; color: #24466b; font-size: 15px; font-weight: normal;
                   min-height: 24px; padding: 2px 8px; text-decoration: underline; }
QPushButton#style { background: white; color: #1d2733; border: 3px solid #c9d2dc; font-size: 24px;
                    min-height: 72px; text-align: center; padding: 6px; }
QPushButton#harm { background: white; color: #24466b; border: 3px dashed #9fb0c2; font-size: 22px; min-height: 56px; }
QPushButton#harm:checked { background: #fff4d6; border: 3px solid #d39b1e; color: #5a3d00; }
QCheckBox { font-size: 20px; }
QSpinBox { font-size: 20px; padding: 4px 8px; background: white; }
QPushButton#style:checked { border: 4px solid #2c7a3f; background: #e6f3e9; }
QProgressBar { border: 2px solid #c9d2dc; border-radius: 14px; background: white; height: 34px; text-align: center; }
QProgressBar::chunk { background: #2c7a3f; border-radius: 12px; }
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
    box.setLayoutDirection(Qt.RightToLeft)
    box.setWindowTitle("שים לב")
    box.setIcon(QMessageBox.Warning)
    box.setText(text)
    box.addButton("הבנתי", QMessageBox.AcceptRole)
    box.exec()


def info(parent, title, text, button="אישור"):
    box = QMessageBox(parent)
    box.setLayoutDirection(Qt.RightToLeft)
    box.setWindowTitle(title)
    box.setText(text)
    box.addButton(button, QMessageBox.AcceptRole)
    box.exec()


def ask(parent, title, text, yes="כן", no="לא"):
    """שאלה עם שני כפתורים בעברית. מחזיר True אם נבחר 'כן'."""
    box = QMessageBox(parent)
    box.setLayoutDirection(Qt.RightToLeft)
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

    def __init__(self, fn, fail_text="משהו השתבש בזמן הכנת השיר.\nנסה שוב. אם זה חוזר, הפעל מחדש את התוכנה."):
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
            self.failed.emit("השיר ארוך מדי בשביל הזיכרון של המחשב.\n"
                             "נסו לסגור תוכנות אחרות, או לחלק את השיר לשני חלקים.")
        except Exception:
            log_error(traceback.format_exc())
            self.failed.emit(self.fail_text)
