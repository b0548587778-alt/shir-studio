"""חלון 'הפרדת קול ופלייבק': הפרדת שירה מנגינה, גרסה ווקאלית, הפרדה לכלים, שינוי סולם וקצב של פלייבק,
ושירה על פלייבק קיים."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton, QButtonGroup,
                               QPushButton, QSpinBox, QLabel, QFormLayout)

from .advanced import CSS

MODES = (("two", "שירה + נגינה (פלייבק) - שני קבצים"),
         ("vocal", "גרסה ווקאלית - השירה עם ליווי של קולות בלבד, בלי כלי נגינה"),
         ("stems", "הפרדה לכלים - שירה, תופים, בס ושאר הכלים (לוקח יותר זמן)"))


class ToolsDialog(QDialog):
    """בסיום: self.action = ("separate", מצב) / ("shift", חצאי טונים, אחוזי קצב) / ("sing",) או None."""

    def __init__(self, parent=None, stems=True):
        super().__init__(parent)
        self.setWindowTitle("הפרדת קול ופלייבק")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(CSS)
        self.resize(680, 560)
        self.action = None
        v = QVBoxLayout(self)

        g = QGroupBox("הפרדת קול משיר מוכן")
        gv = QVBoxLayout(g)
        self.modes = QButtonGroup(self)
        self.mode_buttons = {}
        for key, text in MODES:
            rb = QRadioButton(text)
            rb.setEnabled(key != "stems" or stems)
            self.modes.addButton(rb)
            self.mode_buttons[key] = rb
            gv.addWidget(rb)
        self.mode_buttons["two"].setChecked(True)
        self.b_separate = QPushButton("בחר שיר (אפשר לבחור כמה שירים יחד)")
        self.b_separate.clicked.connect(lambda: self._finish(("separate", self.mode())))
        gv.addWidget(self.b_separate)
        v.addWidget(g)

        g = QGroupBox("פלייבק בסולם ובקצב שלי")
        f = QFormLayout(g)
        self.semitones = QSpinBox()
        self.semitones.setRange(-6, 6)
        self.semitones.setSuffix(" חצאי טונים")
        self.semitones.setToolTip("מספר חיובי = גבוה יותר, שלילי = נמוך יותר")
        self.tempo = QSpinBox()
        self.tempo.setRange(70, 130)
        self.tempo.setValue(100)
        self.tempo.setSuffix("%")
        self.tempo.setToolTip("100% = כמו שהוא. פחות = איטי יותר, יותר = מהיר יותר")
        f.addRow("סולם:", self.semitones)
        f.addRow("קצב:", self.tempo)
        self.b_shift = QPushButton("בחר קובץ נגינה ושמור אותו בסולם ובקצב החדשים")
        self.b_shift.clicked.connect(lambda: self._finish(("shift", self.semitones.value(), self.tempo.value())))
        f.addRow(self.b_shift)
        v.addWidget(g)

        g = QGroupBox("שירה על פלייבק")
        gv = QVBoxLayout(g)
        hint = QLabel("בוחרים קובץ נגינה, שרים עליו עם אוזניות - והתוכנה מנקה את הקול, מתקנת זיופים ומערבבת.")
        hint.setObjectName("small")
        hint.setWordWrap(True)
        gv.addWidget(hint)
        self.b_sing = QPushButton("🎧  בחר פלייבק והתחל לשיר")
        self.b_sing.clicked.connect(lambda: self._finish(("sing",)))
        gv.addWidget(self.b_sing)
        v.addWidget(g)

        row = QHBoxLayout()
        cancel = QPushButton("סגור")
        cancel.clicked.connect(self.reject)
        row.addStretch(); row.addWidget(cancel)
        v.addLayout(row)

    def mode(self):
        return next(k for k, rb in self.mode_buttons.items() if rb.isChecked())

    def _finish(self, action):
        self.action = action
        self.accept()
