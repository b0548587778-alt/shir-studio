"""גרף תיקון הזיופים: הקו האפור = מה שהזמר שר, הקו הירוק = אחרי התיקון.
אפשר גם לתקן ביד: לגרור צליל למעלה או למטה, או לבטל את התיקון שלו בלחיצה כפולה."""
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QSlider

from .music.theory import NOTE_NAMES


class PitchView(QWidget):
    def __init__(self, t, before, after, notes, edits=None):
        super().__init__()
        # notes: (התחלה, סוף, מה שהושר, היעד הנוכחי, מפתח, היעד האוטומטי)
        self.t, self.before, self.after, self.notes = t, before, after, notes
        self.edits = dict(edits or {})        # {מפתח: חצאי טונים מהיעד האוטומטי, או "off"}
        self._drag = None                     # (מספר הצליל, y בתחילת הגרירה, הערך בתחילת הגרירה)
        self.setMouseTracking(True)
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
        for i, nt in enumerate(self.notes):
            s, e = nt[0], nt[1]
            if e < self.view[0] or s > self.view[1]:
                continue
            ed = self.edits.get(nt[4])
            if ed == "off":                              # בלי תיקון: מסגרת מקווקות במקום שהושר
                p.setPen(QPen(QColor("#b0322a"), 2, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
            elif ed is not None:                         # צליל שהוזז ביד
                p.setPen(QPen(QColor("#d39b1e"), 2))
                p.setBrush(QColor(211, 155, 30, 90))
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(44, 122, 63, 40))
            m = self.target(i)
            a, b = self._xy(r, s, m + 0.4), self._xy(r, e, m - 0.4)
            p.drawRect(QRectF(a, b).normalized())
        self._curve(p, r, self.before, "#9aa5b1", 2)
        self._curve(p, r, self.after, "#2c7a3f", 2.5)
        p.end()


    # ---------- תיקון ידני ----------
    def _area(self):
        return QRectF(self.rect()).adjusted(10, 10, -70, -10)

    def target(self, i):
        """הצליל שאליו מתוקן צליל מספר i (לפי העריכה הנוכחית)."""
        nt = self.notes[i]
        ed = self.edits.get(nt[4])
        if ed == "off":
            return round(nt[2])
        auto = nt[5] if len(nt) > 5 else round(nt[2])
        return auto + (int(ed) if ed is not None else 0)

    def note_at(self, pos):
        r = self._area()
        t = self.view[0] + (r.right() - pos.x()) / r.width() * (self.view[1] - self.view[0])
        m = self.lo + (r.bottom() - pos.y()) / r.height() * (self.hi - self.lo)
        best = None
        for i, nt in enumerate(self.notes):
            if nt[0] - 0.03 <= t <= nt[1] + 0.03 and abs(m - self.target(i)) < 1.2:
                if best is None or abs(m - self.target(i)) < abs(m - self.target(best)):
                    best = i
        return best

    def set_edit(self, i, value):
        """value: מספר חצאי טונים מהיעד האוטומטי, "off" = בלי תיקון, None/0 = אוטומטי."""
        key = self.notes[i][4]
        if value in (None, 0):
            self.edits.pop(key, None)
        else:
            self.edits[key] = value
        self.update()

    def mousePressEvent(self, ev):
        i = self.note_at(ev.position())
        if i is not None and len(self.notes[i]) > 5:
            ed = self.edits.get(self.notes[i][4])
            self._drag = (i, ev.position().y(), 0 if ed in (None, "off") else int(ed))

    def mouseMoveEvent(self, ev):
        if self._drag is None:
            self.setCursor(Qt.SizeVerCursor if self.note_at(ev.position()) is not None else Qt.ArrowCursor)
            return
        i, y0, v0 = self._drag
        step = self._area().height() / (self.hi - self.lo)          # פיקסלים לחצי טון
        v = int(np.clip(v0 + round((y0 - ev.position().y()) / step), -12, 12))
        self.set_edit(i, v)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def mouseDoubleClickEvent(self, ev):
        i = self.note_at(ev.position())
        if i is not None and len(self.notes[i]) > 5:
            self._drag = None
            self.set_edit(i, None if self.edits.get(self.notes[i][4]) == "off" else "off")


class PitchDialog(QDialog):
    def __init__(self, parent, curves, edits=None):
        super().__init__(parent)
        self.setWindowTitle("תיקון הזיופים - מה השתנה")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("QPushButton { font-size: 19px; min-height: 44px; padding: 6px 18px; border-radius: 12px; }")
        v = QVBoxLayout(self)
        lab = QLabel("אפור = מה ששרת · ירוק = אחרי התיקון · מלבן = הצליל שאליו מתקנים\n"
                     "תיקון ידני: גרור מלבן למעלה או למטה כדי לשנות את הצליל (נצבע כתום). "
                     "לחיצה כפולה = לא לתקן את הצליל הזה (מסגרת אדומה), ושוב לחיצה כפולה = חזרה לאוטומטי.")
        lab.setStyleSheet("font-size:17px;")
        lab.setWordWrap(True)
        v.addWidget(lab)
        self._start_edits = dict(edits or {})
        self.view = PitchView(*curves, edits=edits)
        v.addWidget(self.view, 1)
        total = float(curves[0][-1]) if len(curves[0]) else 0
        self.scroll = QSlider(Qt.Horizontal)
        self.scroll.setRange(0, max(0, int((total - (self.view.view[1] - self.view.view[0])) * 10)))
        self.scroll.valueChanged.connect(lambda x: self.view.set_start(x / 10))
        v.addWidget(self.scroll)
        h = QHBoxLayout()
        ok = QPushButton("✔  החל את התיקונים")
        ok.setStyleSheet("background:#2c7a3f; color:white; font-weight:bold;")
        ok.clicked.connect(self.accept)
        clear = QPushButton("בטל את כל התיקונים הידניים")
        clear.clicked.connect(self.clear)
        b = QPushButton("סגור")
        b.clicked.connect(self.reject)
        h.addWidget(ok); h.addWidget(clear); h.addStretch(); h.addWidget(b)
        v.addLayout(h)
        self.resize(1000, 600)

    def clear(self):
        self.view.edits.clear()
        self.view.update()

    def edits(self):
        return dict(self.view.edits)

    def changed(self):
        return self.view.edits != self._start_edits
