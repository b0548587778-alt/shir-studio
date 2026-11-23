"""חלונות עריכת ההקלטה: חיתוך (התחלה/סוף) ובחירת משפט להקלטה מחדש."""
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QListWidget,
                               QListWidgetItem)

from .audio.fileio import SR
from .audio import edit
from .screens.common import fmt_time

CSS = """
QWidget { font-size: 18px; }
QPushButton { font-size: 19px; min-height: 44px; padding: 6px 18px; border-radius: 12px; }
QListWidget { background: white; border: 2px solid #c9d2dc; border-radius: 8px; font-size: 20px; }
QListWidget::item { padding: 10px; }
QListWidget::item:selected { background: #e6f3e9; color: #1d2733; }
"""
MIN_SEC = 2.0


class WaveView(QWidget):
    """צורת הגל של ההקלטה, עם שתי ידיות גרירה: התחלה וסוף. הזמן רץ מימין לשמאל."""
    changed = Signal()

    def __init__(self, x):
        super().__init__()
        self.setMinimumSize(760, 220)
        self.dur = len(x) / SR
        n = 1200
        k = max(1, len(x) // n)
        m = np.abs(np.asarray(x[: (len(x) // k) * k], dtype=np.float32)).reshape(-1, k).max(axis=1)
        self.env = m / max(float(m.max()), 1e-6)
        self.start, self.end = 0.0, self.dur
        self._drag = None

    def set_range(self, start, end):
        self.start = float(np.clip(start, 0, self.dur))
        self.end = float(np.clip(end, self.start, self.dur))
        self.update()
        self.changed.emit()

    def _x(self, t):
        return self.width() - 8 - t / max(self.dur, 1e-6) * (self.width() - 16)

    def _t(self, x):
        return float(np.clip((self.width() - 8 - x) / (self.width() - 16) * self.dur, 0, self.dur))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("white"))
        h, mid = self.height(), self.height() / 2
        xs, xe = self._x(self.start), self._x(self.end)
        p.fillRect(QRectF(xe, 0, xs - xe, h), QColor("#e6f3e9"))
        n = len(self.env)
        for i, v in enumerate(self.env):
            t = i / n * self.dur
            inside = self.start <= t <= self.end
            p.setPen(QPen(QColor("#2c7a3f" if inside else "#b9c4cf"), 1))
            x = self._x(t)
            p.drawLine(QPointF(x, mid - v * (mid - 6)), QPointF(x, mid + v * (mid - 6)))
        for x, c in ((xs, "#24466b"), (xe, "#b0322a")):
            p.setPen(QPen(QColor(c), 4))
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            p.setBrush(QColor(c))
            p.drawEllipse(QPointF(x, 12), 9, 9)
        p.end()

    def mousePressEvent(self, ev):
        x = ev.position().x()
        self._drag = "start" if abs(x - self._x(self.start)) <= abs(x - self._x(self.end)) else "end"
        self.mouseMoveEvent(ev)

    def mouseMoveEvent(self, ev):
        if not self._drag:
            return
        t = self._t(ev.position().x())
        if self._drag == "start":
            self.start = min(t, self.end - MIN_SEC)
        else:
            self.end = max(t, self.start + MIN_SEC)
        self.start, self.end = max(0.0, self.start), min(self.dur, self.end)
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, _):
        self._drag = None


class TrimDialog(QDialog):
    """בוחרים איזה חלק מההקלטה נשאר. נפתח כשהשקט שבהתחלה ובסוף כבר מסומן להורדה."""

    def __init__(self, parent, x, play=None, stop=None):
        super().__init__(parent)
        self.setWindowTitle("חיתוך ההקלטה")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(CSS)
        self.x, self._play, self._stop = x, play, stop
        v = QVBoxLayout(self)
        lab = QLabel("גרור את הקו הכחול (התחלה) ואת הקו האדום (סוף). רק החלק הירוק יישאר.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.wave = WaveView(x)
        v.addWidget(self.wave, 1)
        self.info = QLabel()
        v.addWidget(self.info)
        self.wave.changed.connect(self._show)
        h = QHBoxLayout()
        b_play = QPushButton("▶  השמע את החלק שנבחר")
        b_play.clicked.connect(self.play_selection)
        b_auto = QPushButton("✂  הורד רק את השקט")
        b_auto.clicked.connect(self.auto)
        b_all = QPushButton("הכול")
        b_all.clicked.connect(lambda: self.wave.set_range(0, self.wave.dur))
        h.addWidget(b_play); h.addWidget(b_auto); h.addWidget(b_all); h.addStretch()
        v.addLayout(h)
        h = QHBoxLayout()
        ok = QPushButton("חתוך")
        ok.setStyleSheet("background:#2c7a3f; color:white; font-weight:bold;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("ביטול")
        cancel.clicked.connect(self.reject)
        h.addWidget(ok, 2); h.addWidget(cancel, 1)
        v.addLayout(h)
        self.resize(900, 440)
        self.auto()

    def auto(self):
        s, e = edit.auto_trim_range(self.x)
        if e - s < MIN_SEC:
            s, e = 0.0, self.wave.dur
        self.wave.set_range(s, e)

    def _show(self):
        s, e = self.wave.start, self.wave.end
        self.info.setText(f"נשאר: מ-⁦{fmt_time(s)}⁩ עד ⁦{fmt_time(e)}⁩ "
                          f"(⁦{fmt_time(e - s)}⁩ מתוך ⁦{fmt_time(self.wave.dur)}⁩)")

    def play_selection(self):
        if self._play:
            self._play(self.x[int(self.wave.start * SR): int(self.wave.end * SR)])

    def selection(self):
        """(התחלה, סוף) בשניות, או None אם לא נחתך כלום."""
        s, e = self.wave.start, self.wave.end
        return None if (s < 0.02 and e > self.wave.dur - 0.02) else (s, e)

    def done(self, r):
        if self._stop:
            self._stop()
        super().done(r)


class PunchDialog(QDialog):
    """בוחרים משפט אחד שרוצים לשיר שוב."""

    def __init__(self, parent, x, play=None, stop=None):
        super().__init__(parent)
        self.setWindowTitle("הקלטה מחדש של משפט אחד")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(CSS)
        self.x, self._play, self._stop = x, play, stop
        self.slots = edit.phrase_slots(x)
        v = QVBoxLayout(self)
        lab = QLabel("בחר את המשפט שרוצים לתקן, האזן לו, ולחץ 'הקלט מחדש'.\n"
                     "לפני ההקלטה תשמע את מה שקודם למשפט, כדי להיכנס בקצב ובסולם הנכונים. "
                     "כדאי לשים אוזניות. שאר השיר נשאר כמו שהוא.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.list = QListWidget()
        for i, (s, e, _, _) in enumerate(self.slots):
            self.list.addItem(QListWidgetItem(
                f"משפט {i + 1}   ⁦{fmt_time(s)} – {fmt_time(e)}⁩   ({e - s:.0f} שניות)"))
        if self.slots:
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self.play_phrase())
        v.addWidget(self.list, 1)
        h = QHBoxLayout()
        b_play = QPushButton("▶  האזן למשפט")
        b_play.clicked.connect(self.play_phrase)
        self.ok = QPushButton("🎤  הקלט מחדש")
        self.ok.setStyleSheet("background:#b0322a; color:white; font-weight:bold;")
        self.ok.setEnabled(bool(self.slots))
        self.ok.clicked.connect(self.accept)
        cancel = QPushButton("סגור")
        cancel.clicked.connect(self.reject)
        h.addWidget(b_play); h.addWidget(self.ok, 2); h.addWidget(cancel)
        v.addLayout(h)
        self.resize(620, 520)

    def slot(self):
        i = self.list.currentRow()
        return self.slots[i] if 0 <= i < len(self.slots) else None

    def play_phrase(self):
        sl = self.slot()
        if sl and self._play:
            self._play(self.x[int(sl[2] * SR): int(sl[3] * SR)])

    def done(self, r):
        if self._stop:
            self._stop()
        super().done(r)
