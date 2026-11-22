"""גרף תיקון הזיופים: הקו האפור = מה שהזמר שר, הקו הירוק = אחרי התיקון."""
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QSlider

from .music.theory import NOTE_NAMES


class PitchView(QWidget):
    def __init__(self, t, before, after, notes):
        super().__init__()
        self.t, self.before, self.after, self.notes = t, before, after, notes
        self.view = (0.0, min(20.0, float(t[-1]) if len(t) else 1.0))
        self.setMinimumSize(800, 420)
        ok = np.isfinite(before)
        vals = np.concatenate([before[ok], after[np.isfinite(after)]]) if ok.any() else np.array([60.0])
        self.lo, self.hi = np.floor(np.percentile(vals, 1)) - 2, np.ceil(np.percentile(vals, 99)) + 2

    def set_start(self, start):
        w = self.view[1] - self.view[0]
        self.view = (start, start + w)
        self.update()

    def _xy(self, r, t, m):
        x = r.right() - (t - self.view[0]) / (self.view[1] - self.view[0]) * r.width()   # מימין לשמאל
        y = r.bottom() - (m - self.lo) / (self.hi - self.lo) * r.height()
        return QPointF(x, y)

    def _curve(self, p, r, vals, color, width):
        p.setPen(QPen(QColor(color), width))
        p.setBrush(Qt.NoBrush)
        sel = (self.t >= self.view[0]) & (self.t <= self.view[1])
        path, drawing = QPainterPath(), False
        for t, m in zip(self.t[sel], vals[sel]):
            if not np.isfinite(m):
                drawing = False
                continue
            pt = self._xy(r, t, m)
            if drawing:
                path.lineTo(pt)
            else:
                path.moveTo(pt)
                drawing = True
        p.drawPath(path)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        r = QRectF(self.rect()).adjusted(10, 10, -70, -10)
        p.setFont(QFont("Segoe UI", 10))
        for m in range(int(self.lo), int(self.hi) + 1):
            y = self._xy(r, self.view[0], m).y()
            p.setPen(QPen(QColor("#e6ebf0" if m % 12 else "#b9c4cf"), 1))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor("#5a6775"))
            p.drawText(QPointF(r.right() + 6, y + 4), f"{NOTE_NAMES[m % 12]}{m // 12 - 1}")
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(44, 122, 63, 40))
        for s, e, m in self.notes:
            if e < self.view[0] or s > self.view[1]:
                continue
            a, b = self._xy(r, s, round(m) + 0.4), self._xy(r, e, round(m) - 0.4)
            p.drawRect(QRectF(a, b).normalized())
        self._curve(p, r, self.before, "#9aa5b1", 2)
        self._curve(p, r, self.after, "#2c7a3f", 2.5)
        p.end()


class PitchDialog(QDialog):
    def __init__(self, parent, curves):
        super().__init__(parent)
        self.setWindowTitle("תיקון הזיופים - מה השתנה")
        self.setLayoutDirection(Qt.RightToLeft)
        v = QVBoxLayout(self)
        lab = QLabel("אפור = מה ששרת · ירוק = אחרי התיקון · מלבן = הצליל הנקי שזוהה")
        lab.setStyleSheet("font-size:18px;")
        v.addWidget(lab)
        self.view = PitchView(*curves)
        v.addWidget(self.view, 1)
        total = float(curves[0][-1]) if len(curves[0]) else 0
        self.scroll = QSlider(Qt.Horizontal)
        self.scroll.setRange(0, max(0, int((total - (self.view.view[1] - self.view.view[0])) * 10)))
        self.scroll.valueChanged.connect(lambda x: self.view.set_start(x / 10))
        v.addWidget(self.scroll)
        h = QHBoxLayout()
        b = QPushButton("סגור")
        b.clicked.connect(self.accept)
        h.addStretch(); h.addWidget(b)
        v.addLayout(h)
        self.resize(1000, 560)
