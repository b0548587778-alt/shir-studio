"""גרף תיקון הזיופים: הקו האפור = מה שהזמר שר, הקו הירוק = אחרי התיקון.
אפשר גם לתקן ביד: לוחצים על צליל (מלבן) וגוררים אותו למעלה או למטה."""
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QSlider

from .music.theory import NOTE_NAMES


class PitchView(QWidget):
    changed = Signal()          # תיקון ידני השתנה
    selected = Signal()         # נבחר צליל אחר

    def __init__(self, t, before, after, notes, transpose=0, editable=False):
        super().__init__()
        self.t, self.before, self.after = t, before, after
        self.notes = [self._norm(n) for n in notes]
        self.tp = transpose
        self.editable = editable
        self.fix = {i: n[3] - transpose for i, n in enumerate(self.notes) if n[4]}   # מספר צליל -> יעד
        self.sel = None
        self._drag = False
        self.view = (0.0, min(20.0, float(t[-1]) if len(t) else 1.0))
        self.setMinimumSize(800, 420)
        self.setFocusPolicy(Qt.StrongFocus)
        ok = np.isfinite(before)
        vals = np.concatenate([before[ok], after[np.isfinite(after)]]) if ok.any() else np.array([60.0])
        self.lo, self.hi = np.floor(np.percentile(vals, 1)) - 3, np.ceil(np.percentile(vals, 99)) + 3

    @staticmethod
    def _norm(n):
        """(התחלה, סוף, מה שהושר, צליל היעד, ידני?) - מקבל גם את הצורה הישנה בלי יעד."""
        n = tuple(n)
        return n if len(n) >= 5 else (n[0], n[1], n[2], int(round(n[2])), False)

    # ---------- נתונים ----------
    def set_curves(self, t, before, after, notes):
        self.t, self.before, self.after = t, before, after
        self.notes = [self._norm(n) for n in notes]
        self.update()

    def fixes(self):
        """התיקונים הידניים בצורה שנשמרת בהגדרות: [[זמן באמצע הצליל, צליל היעד], ...]."""
        out = []
        for i in sorted(self.fix):
            s, e = self.notes[i][0], self.notes[i][1]
            out.append([round((s + e) / 2, 3), int(self.fix[i])])
        return out

    def set_target(self, i, midi):
        """קובע צליל יעד ידני (midi כפי שמוצג בגרף, כולל טרנספוזיציה)."""
        if i is None or not (0 <= i < len(self.notes)):
            return
        m = int(np.clip(round(midi), self.lo, self.hi)) - self.tp
        if self.fix.get(i) == m:
            return
        self.fix[i] = m
        n = self.notes[i]
        self.notes[i] = (n[0], n[1], n[2], m + self.tp, True)
        self.update()

    def clear(self, i=None):
        """מחזיר צליל אחד (או את כולם) לתיקון האוטומטי."""
        if i is None:
            self.fix.clear()
        else:
            self.fix.pop(i, None)
        self.changed.emit()

    def nudge(self, d):
        if self.sel is not None:
            self.set_target(self.sel, self.notes[self.sel][3] + d)
            self.changed.emit()

    # ---------- תצוגה ----------
    def set_start(self, start):
        w = self.view[1] - self.view[0]
        self.view = (start, start + w)
        self.update()

    def set_width(self, seconds):
        self.view = (self.view[0], self.view[0] + seconds)
        self.update()

    def _rect(self):
        return QRectF(self.rect()).adjusted(10, 10, -70, -10)

    def _xy(self, r, t, m):
        x = r.right() - (t - self.view[0]) / (self.view[1] - self.view[0]) * r.width()   # מימין לשמאל
        y = r.bottom() - (m - self.lo) / (self.hi - self.lo) * r.height()
        return QPointF(x, y)

    def _at(self, pos):
        """(זמן, גובה צליל) של נקודה על המסך."""
        r = self._rect()
        t = self.view[0] + (r.right() - pos.x()) / r.width() * (self.view[1] - self.view[0])
        m = self.lo + (r.bottom() - pos.y()) / r.height() * (self.hi - self.lo)
        return t, m

    def note_at(self, pos):
        t, m = self._at(pos)
        best, dist = None, 2.5
        for i, n in enumerate(self.notes):
            if n[0] - 0.03 <= t <= n[1] + 0.03:
                d = min(abs(m - n[3]), abs(m - (n[2] + self.tp)))
                if d < dist:
                    best, dist = i, d
        return best

    def _curve(self, p, r, vals, color, width):
        p.setPen(QPen(QColor(color), width))
        p.setBrush(Qt.NoBrush)
        sel = (self.t >= self.view[0]) & (self.t <= self.view[1])
        path, drawing, last = QPainterPath(), False, 0.0
        for t, m in zip(self.t[sel], vals[sel]):
            if not np.isfinite(m):
                drawing = False
                continue
            pt = self._xy(r, t, m)
            if drawing and abs(m - last) > 5:           # קפיצה של רגע (טעות זיהוי) - לא מציירים קו אנכי
                drawing = False
            last = m
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
        r = self._rect()
        p.setFont(QFont("Segoe UI", 10))
        for m in range(int(self.lo), int(self.hi) + 1):
            y = self._xy(r, self.view[0], m).y()
            p.setPen(QPen(QColor("#e6ebf0" if m % 12 else "#b9c4cf"), 1))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor("#5a6775"))
            p.drawText(QPointF(r.right() + 6, y + 4), f"{NOTE_NAMES[m % 12]}{m // 12 - 1}")
        for i, n in enumerate(self.notes):
            s, e, m, manual = n[0], n[1], n[3], n[4]
            if e < self.view[0] or s > self.view[1]:
                continue
            a, b = self._xy(r, s, m + 0.4), self._xy(r, e, m - 0.4)
            p.setBrush(QColor(211, 155, 30, 110) if manual else QColor(44, 122, 63, 40))
            p.setPen(QPen(QColor("#24466b"), 2.5) if i == self.sel else Qt.NoPen)
            p.drawRect(QRectF(a, b).normalized())
        self._curve(p, r, self.before, "#9aa5b1", 2)
        self._curve(p, r, self.after, "#2c7a3f", 2.5)
        p.end()

    # ---------- עריכה ----------
    def mousePressEvent(self, ev):
        if not self.editable or ev.button() != Qt.LeftButton:
            return
        self.setFocus()
        self.sel = self.note_at(ev.position())
        self._drag = self.sel is not None
        self.selected.emit()
        self.update()

    def mouseMoveEvent(self, ev):
        if self._drag and self.sel is not None:
            self.set_target(self.sel, self._at(ev.position())[1])

    def mouseReleaseEvent(self, ev):
        if self._drag:
            self._drag = False
            if self.sel in self.fix:
                self.changed.emit()

    def mouseDoubleClickEvent(self, ev):
        if self.editable and self.sel is not None and self.sel in self.fix:
            self._drag = False
            self.clear(self.sel)

    def keyPressEvent(self, ev):
        if self.editable and ev.key() in (Qt.Key_Up, Qt.Key_Down):
            self.nudge(1 if ev.key() == Qt.Key_Up else -1)
        else:
            super().keyPressEvent(ev)


class PitchDialog(QDialog):
    """גרף + תיקון ידני. curves_fn(fixes) מחזיר את העקומות עם התיקונים; hear_fn(fixes, התחלה, סוף) משמיע."""

    def __init__(self, parent, curves_fn, transpose=0, hear_fn=None):
        super().__init__(parent)
        self.setWindowTitle("תיקון הזיופים - גרף ותיקון ידני")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("QPushButton { font-size:18px; min-height:40px; padding:6px 14px; border-radius:10px; }")
        self.curves_fn, self.hear_fn = curves_fn, hear_fn
        v = QVBoxLayout(self)
        lab = QLabel("אפור = מה ששרת · ירוק = אחרי התיקון · מלבן = הצליל שאליו מתקנים (כתום = תיקון ידני שלך)\n"
                     "התיקון טעה? לחץ על מלבן וגרור אותו למעלה או למטה (או בחיצים ↑ ↓). לחיצה כפולה מחזירה לאוטומטי.")
        lab.setStyleSheet("font-size:17px;")
        lab.setWordWrap(True)
        v.addWidget(lab)
        curves = curves_fn(None)
        self.view = PitchView(*curves, transpose=transpose, editable=True)
        self._start = self.view.fixes()
        self.view.changed.connect(self._recompute)
        self.view.selected.connect(self._update_buttons)
        v.addWidget(self.view, 1)
        self.total = float(curves[0][-1]) if len(curves[0]) else 0
        self.scroll = QSlider(Qt.Horizontal)
        self.scroll.setInvertedAppearance(True)            # הזמן מתקדם מימין לשמאל, כמו בגרף
        self.scroll.valueChanged.connect(lambda x: self.view.set_start(x / 10))
        v.addWidget(self.scroll)
        self._set_range()
        h = QHBoxLayout()
        self.b_hear = QPushButton("▶  השמע את הצליל")
        self.b_hear.clicked.connect(self._hear)
        self.b_auto = QPushButton("החזר צליל זה לאוטומטי")
        self.b_auto.clicked.connect(lambda: self.view.clear(self.view.sel))
        self.b_all = QPushButton("בטל את כל התיקונים הידניים")
        self.b_all.clicked.connect(lambda: self.view.clear())
        b_in = QPushButton("🔍 +")
        b_in.clicked.connect(lambda: self._zoom(0.5))
        b_out = QPushButton("🔍 −")
        b_out.clicked.connect(lambda: self._zoom(2.0))
        ok = QPushButton("אישור - הכן את השיר מחדש")
        ok.setStyleSheet("background:#2c7a3f; color:white; font-weight:bold;")
        ok.clicked.connect(self.accept)
        self.b_ok = ok
        b = QPushButton("סגור")
        b.clicked.connect(self.reject)
        for w in (self.b_hear, self.b_auto, self.b_all, b_in, b_out):
            h.addWidget(w)
        h.addStretch(); h.addWidget(ok); h.addWidget(b)
        v.addLayout(h)
        self.resize(1100, 620)
        self._update_buttons()

    def _set_range(self):
        w = self.view.view[1] - self.view.view[0]
        self.scroll.setRange(0, max(0, int((self.total - w) * 10) + 5))

    def _zoom(self, k):
        w = float(np.clip((self.view.view[1] - self.view.view[0]) * k, 5.0, 80.0))
        self.view.set_width(w)
        self._set_range()

    def _recompute(self):
        self.view.set_curves(*self.curves_fn(self.view.fixes()))
        self._update_buttons()

    def _update_buttons(self):
        s = self.view.sel
        self.b_hear.setEnabled(s is not None and self.hear_fn is not None)
        self.b_auto.setEnabled(s is not None and s in self.view.fix)
        self.b_all.setEnabled(bool(self.view.fix))
        self.b_ok.setEnabled(self.changed())

    def _hear(self):
        s = self.view.sel
        if s is not None and self.hear_fn:
            n = self.view.notes[s]
            self.hear_fn(self.view.fixes(), n[0], n[1])

    def fixes(self):
        return self.view.fixes()

    def changed(self):
        return self.view.fixes() != self._start
