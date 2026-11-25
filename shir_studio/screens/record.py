"""מסך ההקלטה: ספירה לאחור, שעון, ופס שמראה שהמיקרופון שומע."""
from ..i18n import tx
from ..i18n import direction
from PySide6.QtCore import Signal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QProgressBar, QPlainTextEdit

from .common import big_button, label

TITLE = tx("מקליט... שיר עכשיו")
HINT = tx("הפס הירוק זז כשהמיקרופון שומע אותך")
TOO_LOUD = tx("חזק מדי! התרחק מעט מהמיקרופון")
NOT_HEARD = tx("לא שומע אותך - התקרב למיקרופון ובדוק שהוא מחובר")


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
        self.hint = label(HINT, "hint")
        v.addWidget(self.hint)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        v.addWidget(self.level)
        self.lyrics = QPlainTextEdit()                 # מילות השיר - כששרים שוב שיר שכבר יש לו מילים
        self.lyrics.setReadOnly(True)
        self.lyrics.setFocusPolicy(Qt.NoFocus)
        self.lyrics.setStyleSheet("background: white; font-size: 24px; border: 2px solid #c9d2dc; "
                                  "border-radius: 10px; padding: 8px;")
        opt = self.lyrics.document().defaultTextOption()
        opt.setTextDirection(direction())
        opt.setAlignment(Qt.AlignHCenter)
        self.lyrics.document().setDefaultTextOption(opt)
        self.lyrics.hide()
        v.addWidget(self.lyrics, 1)
        v.addStretch()
        h = QHBoxLayout()
        b_stop = big_button(tx("⏹  סיום"), "red")
        b_stop.setMinimumHeight(110)
        b_stop.clicked.connect(self.stop)
        b_cancel = big_button(tx("ביטול"), "light")
        b_cancel.clicked.connect(self.cancel)
        h.addWidget(b_stop, 3); h.addWidget(b_cancel, 1)
        v.addLayout(h)

    def set_level(self, rms):
        self.level.setValue(min(100, int(rms * 400)))

    def set_warning(self, text=None):
        """אזהרה בזמן ההקלטה (חזק מדי / לא שומע), או None = ההסבר הרגיל."""
        want = text or HINT
        if self.hint.text() != want:
            self.hint.setText(want)
            self.hint.setStyleSheet("color:#b0322a; font-weight:bold;" if text else "")

    def set_lyrics(self, text=""):
        self.lyrics.setPlainText(text or "")
        self.lyrics.setVisible(bool(text))
