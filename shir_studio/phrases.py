"""עריכת משפטים: להקליט מחדש משפט שלא יצא טוב, לשיר משפט פעם נוספת (חזרה) או למחוק משפט."""
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
                               QProgressBar, QMessageBox)

from .audio import edit
from .audio.fileio import SR, AudioError

CSS = """
QWidget { font-size: 18px; }
QPushButton { font-size: 19px; min-height: 46px; padding: 6px 16px; border-radius: 12px; }
QListWidget { background: white; border: 2px solid #c9d2dc; border-radius: 8px; font-size: 20px; }
QListWidget::item { padding: 8px; }
QListWidget::item:selected { background: #e6f3e9; color: #1d2733; }
QLabel#small { color: #5a6571; font-size: 16px; }
"""


def _fmt(sec):
    sec = int(sec)
    return f"⁦{sec // 60}:{sec % 60:02d}⁩"


class PhraseDialog(QDialog):
    def __init__(self, parent, raw, regions, play, stop, make_recorder):
        super().__init__(parent)
        self.setWindowTitle("עריכת משפטים")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(CSS)
        self.resize(760, 640)
        self.raw = np.array(raw, dtype=np.float32)
        self.regions = [dict(r) for r in regions]
        self.play, self.stop, self.make_recorder = play, stop, make_recorder
        self.recorder = None
        self.take = None
        self.dirty = False
        v = QVBoxLayout(self)
        t = QLabel("בחר משפט מהרשימה. אפשר לשמוע אותו, להקליט אותו מחדש, לחזור עליו פעם נוספת או למחוק אותו.\n"
                   "בסיום לחץ 'אישור' - והשיר יוכן מחדש.")
        t.setObjectName("small")
        t.setWordWrap(True)
        v.addWidget(t)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._selected)
        v.addWidget(self.list, 1)
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        v.addWidget(self.status)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.hide()
        v.addWidget(self.level)
        h1 = QHBoxLayout()
        self.b_play = QPushButton("▶  השמע את המשפט")
        self.b_play.clicked.connect(self._play_phrase)
        self.b_rec = QPushButton("🎤  הקלט מחדש")
        self.b_rec.clicked.connect(self._toggle_record)
        h1.addWidget(self.b_play); h1.addWidget(self.b_rec)
        v.addLayout(h1)
        h2 = QHBoxLayout()
        self.b_take = QPushButton("▶  השמע את ההקלטה החדשה")
        self.b_take.clicked.connect(lambda: self.play(edit.trim(self.take)))
        self.b_use = QPushButton("✔  החלף בהקלטה החדשה")
        self.b_use.setStyleSheet("background:#2c7a3f; color:white; font-weight:bold;")
        self.b_use.clicked.connect(self._use_take)
        h2.addWidget(self.b_take); h2.addWidget(self.b_use)
        v.addLayout(h2)
        h3 = QHBoxLayout()
        self.b_dup = QPushButton("🔁  שיר את המשפט פעם נוספת (חזרה)")
        self.b_dup.clicked.connect(self._duplicate)
        self.b_del = QPushButton("🗑  מחק את המשפט")
        self.b_del.clicked.connect(self._delete)
        h3.addWidget(self.b_dup); h3.addWidget(self.b_del)
        v.addLayout(h3)
        h4 = QHBoxLayout()
        self.b_ok = QPushButton("אישור - הכן את השיר מחדש")
        self.b_ok.setStyleSheet("background:#24466b; color:white; font-weight:bold;")
        self.b_ok.clicked.connect(self.accept)
        cancel = QPushButton("ביטול")
        cancel.clicked.connect(self.reject)
        h4.addWidget(self.b_ok, 2); h4.addWidget(cancel, 1)
        v.addLayout(h4)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._fill()

    # ---------- רשימה ----------
    def _fill(self, row=0):
        self.list.blockSignals(True)
        self.list.clear()
        for i, r in enumerate(self.regions):
            self.list.addItem(f"משפט {i + 1}   ({_fmt(r['start'])} עד {_fmt(r['end'])})")
        self.list.blockSignals(False)
        if self.regions:
            self.list.setCurrentRow(min(row, len(self.regions) - 1))
        self._update()

    def _region(self):
        i = self.list.currentRow()
        return self.regions[i] if 0 <= i < len(self.regions) else None

    def _selected(self, _):
        self.take = None
        self._update()

    def _update(self):
        r = self._region()
        rec = self.recorder is not None
        self.b_play.setEnabled(r is not None and not rec)
        self.b_rec.setEnabled(r is not None)
        self.b_take.setEnabled(self.take is not None and not rec)
        self.b_use.setEnabled(self.take is not None and not rec)
        self.b_dup.setEnabled(r is not None and not rec)
        self.b_del.setEnabled(r is not None and not rec and len(self.regions) > 1)
        self.b_ok.setEnabled(self.dirty and not rec)
        self.list.setEnabled(not rec)

    # ---------- פעולות ----------
    def _play_phrase(self):
        r = self._region()
        if r:
            i0 = max(0, int((r["start"] - 0.15) * SR))
            self.play(self.raw[i0:int((r["end"] + 0.25) * SR)])

    def _toggle_record(self):
        if self.recorder is None:
            self.stop()
            rec = self.make_recorder()
            try:
                rec.start()
            except AudioError as e:
                self._warn(str(e))
                return
            self.recorder = rec
            self.b_rec.setText("⏹  סיום ההקלטה")
            self.status.setText("מקליט... שיר עכשיו את המשפט")
            self.level.show()
            self.timer.start(100)
        else:
            self.timer.stop()
            data = self.recorder.stop()
            self.recorder = None
            self.b_rec.setText("🎤  הקלט מחדש")
            self.level.hide()
            if data is None or len(data) < SR * 0.4 or np.max(np.abs(data)) < 0.003:
                self.take = None
                self.status.setText("לא שמעתי קול בהקלטה. נסה שוב, קרוב יותר למיקרופון.")
            else:
                self.take = np.asarray(data, dtype=np.float32)
                self.status.setText("ההקלטה מוכנה. אפשר לשמוע אותה, ואם היא טובה - להחליף.")
        self._update()

    def _tick(self):
        if self.recorder is not None:
            self.level.setValue(min(100, int(self.recorder.level * 400)))

    def _use_take(self):
        r = self._region()
        if r is None or self.take is None:
            return
        self.raw = edit.replace_phrase(self.raw, r, self.take)
        self.take = None
        self.dirty = True
        self.status.setText("המשפט הוחלף.")
        self._update()

    def _shift(self, i, d):
        for r in self.regions[i:]:
            for k in ("start", "end", "a", "b"):
                r[k] += d

    def _duplicate(self):
        i = self.list.currentRow()
        r = self._region()
        if r is None:
            return
        self.raw = edit.duplicate_phrase(self.raw, r)
        d = r["b"] - r["a"]
        self._shift(i + 1, d)
        self.regions.insert(i + 1, {k: r[k] + d for k in ("start", "end", "a", "b")})
        self.dirty = True
        self.status.setText("המשפט יושר פעמיים ברצף.")
        self._fill(i + 1)

    def _delete(self):
        i = self.list.currentRow()
        r = self._region()
        if r is None or len(self.regions) < 2:
            return
        box = QMessageBox(self)
        box.setLayoutDirection(Qt.RightToLeft)
        box.setWindowTitle("מחיקת משפט")
        box.setText(f"למחוק את משפט {i + 1} מהשיר?")
        yes = box.addButton("כן, מחק", QMessageBox.AcceptRole)
        box.addButton("ביטול", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        self.raw = edit.delete_phrase(self.raw, r)
        del self.regions[i]
        self._shift(i, -(r["b"] - r["a"]))
        self.dirty = True
        self.status.setText("המשפט נמחק.")
        self._fill(i)

    def _warn(self, text):
        box = QMessageBox(self)
        box.setLayoutDirection(Qt.RightToLeft)
        box.setWindowTitle("שים לב")
        box.setIcon(QMessageBox.Warning)
        box.setText(text)
        box.addButton("הבנתי", QMessageBox.AcceptRole)
        box.exec()

    def done(self, code):
        self.timer.stop()
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder = None
        self.stop()
        super().done(code)
