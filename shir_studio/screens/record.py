"""מסך ההקלטה: ספירה לאחור, שעון, ופס שמראה שהמיקרופון שומע."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QProgressBar

from .common import big_button, label

TITLE = "מקליט... שיר עכשיו"


class RecordScreen(QWidget):
    stop = Signal()
    cancel = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 26, 40, 26)
        v.setSpacing(18)
        self.title = label(TITLE, "title")
        v.addWidget(self.title)
        self.time = label("0:00", "big")
        v.addWidget(self.time)
        self.hint = label("הפס הירוק זז כשהמיקרופון שומע אותך", "hint")
        v.addWidget(self.hint)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        v.addWidget(self.level)
        v.addStretch()
        h = QHBoxLayout()
        b_stop = big_button("⏹  סיום", "red")
        b_stop.setMinimumHeight(110)
        b_stop.clicked.connect(self.stop)
        b_cancel = big_button("ביטול", "light")
        b_cancel.clicked.connect(self.cancel)
        h.addWidget(b_stop, 3); h.addWidget(b_cancel, 1)
        v.addLayout(h)

    def set_level(self, rms):
        self.level.setValue(min(100, int(rms * 400)))
