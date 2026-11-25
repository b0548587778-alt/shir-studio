"""מצב תרגול: ציון דיוק לכל משפט, האזנה למשפט בלולאה ובהאטה, והשוואה ל'כך זה צריך להישמע'."""
from .i18n import tx
from .i18n import direction
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
                               QListWidgetItem, QCheckBox, QComboBox)

from .audio.fileio import SR
from .audio import edit
from .music import score
from .screens.common import fmt_time
from .trimview import CSS

SPEEDS = ((tx("מהירות רגילה"), 1.0), (tx("לאט (75%)"), 0.75), (tx("לאט מאוד (50%)"), 0.5))
LOOPS = 4
GAP = 0.6                  # שניות של שקט בין חזרה לחזרה


def loop_clip(seg, speed=1.0, loops=1):
    """מה שמושמע בתרגול: המשפט בהאטה (בלי לשנות את גובה הצליל), וחוזר כמה פעמים עם הפסקה קצרה."""
    seg = np.asarray(seg, dtype=np.float32)
    if abs(speed - 1.0) > 1e-6 and len(seg) > SR // 4:
        from .audio import stretch
        seg = stretch.change(seg, 0, speed)
    if loops <= 1:
        return seg
    gap = np.zeros(int(GAP * SR), dtype=np.float32)
    return np.concatenate([np.concatenate([seg, gap]) for _ in range(loops)])[: -len(gap)]


def _color(s):
    if s is None:
        return "#6a7684"
    return "#2c7a3f" if s >= 88 else ("#8a6d00" if s >= 72 else "#b0322a")


class PracticeDialog(QDialog):
    """analysis: ניתוח השיר. raw: ההקלטה. tuned: הקול אחרי התיקון (אותו אורך) או None."""

    def __init__(self, parent, raw, analysis, tuned=None, play=None, stop=None):
        super().__init__(parent)
        self.setWindowTitle(tx("מצב תרגול"))
        self.setLayoutDirection(direction())
        self.setStyleSheet(CSS + "QCheckBox, QComboBox { font-size: 19px; } QComboBox { padding: 6px; background: white; }")
        self.raw, self.tuned, self._play, self._stop = raw, tuned, play, stop
        self.gain = np.float32(0.7 / max(float(np.max(np.abs(raw))) if len(raw) else 0.0, 1e-6))
        self.slots = edit.phrase_slots(raw)
        self.report = score.phrase_report(analysis, self.slots)
        self.punch = None                              # המשפט שביקשו להקליט מחדש
        v = QVBoxLayout(self)
        total = score.overall(self.report, self.slots)
        self.total = QLabel(tx("הדיוק של השיר כולו: ") + (tx("{0:.0f} מתוך 100").format(total) if total is not None else tx("לא נמדד")))
        self.total.setStyleSheet(f"font-size:24px; font-weight:bold; color:{_color(total)};")
        v.addWidget(self.total)
        lab = QLabel(tx("לכל משפט יש ציון דיוק (לפני התיקון של התוכנה). בחר משפט, האזן לעצמך, "
                     "ואז האזן איך הוא צריך להישמע. אפשר להאט ולחזור עליו שוב ושוב - ולשיר יחד."))
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.list = QListWidget()
        for i, ((s, e, _, _), r) in enumerate(zip(self.slots, self.report)):
            sc = "—" if r["score"] is None else f"{r['score']:.0f}"
            it = QListWidgetItem(tx("משפט {0}   ⁦{1} – {2}⁩   ציון {3}   ·   {4}").format(i + 1, fmt_time(s), fmt_time(e), sc, r['text']))
            it.setForeground(QColor(_color(r["score"])))
            self.list.addItem(it)
        if self.slots:
            self.list.setCurrentRow(self.weakest())
        self.list.itemDoubleClicked.connect(lambda _: self.play_mine())
        v.addWidget(self.list, 1)
        h = QHBoxLayout()
        self.speed = QComboBox()
        for name, val in SPEEDS:
            self.speed.addItem(name, val)
        self.loop = QCheckBox(tx("חזור על המשפט {0} פעמים").format(LOOPS))
        h.addWidget(self.speed); h.addWidget(self.loop); h.addStretch()
        v.addLayout(h)
        h = QHBoxLayout()
        b_mine = QPushButton(tx("▶  כך שרתי"))
        b_mine.clicked.connect(self.play_mine)
        self.b_fixed = QPushButton(tx("▶  כך זה צריך להישמע"))
        self.b_fixed.setEnabled(tuned is not None)
        self.b_fixed.clicked.connect(self.play_fixed)
        b_stop = QPushButton(tx("⏹  עצור"))
        b_stop.clicked.connect(lambda: self._stop and self._stop())
        h.addWidget(b_mine); h.addWidget(self.b_fixed); h.addWidget(b_stop)
        v.addLayout(h)
        h = QHBoxLayout()
        self.b_punch = QPushButton(tx("🎤  הקלט את המשפט הזה מחדש"))
        self.b_punch.setStyleSheet("background:#b0322a; color:white; font-weight:bold;")
        self.b_punch.setEnabled(bool(self.slots))
        self.b_punch.clicked.connect(self._punch)
        close = QPushButton(tx("סגור"))
        close.clicked.connect(self.reject)
        h.addWidget(self.b_punch, 2); h.addWidget(close, 1)
        v.addLayout(h)
        self.resize(760, 600)

    def weakest(self):
        """המשפט עם הציון הנמוך ביותר - ממנו כדאי להתחיל."""
        scores = [r["score"] if r["score"] is not None else 101 for r in self.report]
        return int(np.argmin(scores)) if scores else 0

    def slot(self):
        i = self.list.currentRow()
        return self.slots[i] if 0 <= i < len(self.slots) else None

    def clip(self, source):
        """הקטע שמושמע עכשיו, לפי המשפט, המהירות והלולאה שנבחרו."""
        sl = self.slot()
        if sl is None or source is None:
            return None
        seg = source[int(sl[2] * SR): int(sl[3] * SR)]
        if source is self.raw:
            seg = seg * self.gain                      # ההקלטה המקורית חלשה - מגבירים אותה להאזנה
        return loop_clip(seg, self.speed.currentData(), LOOPS if self.loop.isChecked() else 1)

    def play_mine(self):
        seg = self.clip(self.raw)
        if seg is not None and self._play:
            self._play(seg)

    def play_fixed(self):
        seg = self.clip(self.tuned)
        if seg is not None and self._play:
            self._play(seg)

    def _punch(self):
        self.punch = self.slot()
        self.accept()

    def done(self, r):
        if self._stop:
            self._stop()
        super().done(r)
