"""מסך בחירת סגנון הליווי."""
from ..i18n import tx
from PySide6.QtCore import Qt, Signal

from ..i18n import is_rtl
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QButtonGroup,
                               QScrollArea, QSizePolicy)

from .common import big_button, label

PREVIEW_TEXT = tx("🎧  האזנה מהירה (25 שניות)")


class StyleScreen(QWidget):
    make = Signal()
    back = Signal()
    advanced = Signal()
    preview = Signal()
    trim = Signal()
    harmony = Signal(bool)

    def __init__(self, styles):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 26, 40, 26)
        v.setSpacing(16)
        v.addWidget(label(tx("בחר סגנון ליווי"), "title"))
        grid = QGridLayout()
        grid.setSpacing(16)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, st in enumerate(styles):
            b = QPushButton(f"{st['name']}\n{st.get('description', '')}")
            b.setObjectName("style")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton#style { font-size: %dpx; min-height: 58px; }" % (17 if is_rtl() else 15))
            self.group.addButton(b, i)
            b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)   # לא רחב מהמסך
            grid.addWidget(b, i // 2, i % 2)
            if i == 0:
                b.setChecked(True)
        for c in range(2):
            grid.setColumnStretch(c, 1)
        # הרשימה בתוך אזור גלילה - שגם במסך קטן של מחשב נייד הכול ייכנס
        box = QWidget()
        box.setLayout(grid)
        grid.setContentsMargins(18, 4, 4, 4)            # מקום לפס הגלילה
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(box)
        v.addWidget(scroll, 1)
        self.harm_btn = QPushButton(tx("🎶  הוסף קול שני (מקהלה)"))
        self.harm_btn.setCheckable(True)
        self.harm_btn.toggled.connect(self.harmony)
        self.prev_btn = QPushButton(PREVIEW_TEXT)
        self.prev_btn.clicked.connect(self.preview)
        self.trim_btn = QPushButton(tx("✂  חיתוך ההקלטה"))
        self.trim_btn.setToolTip(tx("הורדת השקט שבהתחלה ובסוף, או בחירת קטע מתוך הקלטה ארוכה"))
        self.trim_btn.clicked.connect(self.trim)
        hb = QHBoxLayout()
        for b in (self.harm_btn, self.prev_btn, self.trim_btn):
            b.setObjectName("harm")
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("font-size: 18px; min-height: 44px; padding: 6px;")
            hb.addWidget(b)
        v.addLayout(hb)
        h = QHBoxLayout()
        go = big_button(tx("✨  הכן את השיר"), "green")
        go.setMinimumHeight(100)
        go.clicked.connect(self.make)
        b_back = big_button(tx("חזרה"), "light")
        b_back.clicked.connect(self.back)
        adv = big_button("⚙", "light")
        adv.setToolTip(tx("אפשרויות מתקדמות"))
        adv.clicked.connect(self.advanced)
        h.addWidget(go, 3); h.addWidget(b_back, 1); h.addWidget(adv)
        v.addLayout(h)

    def current(self):
        return max(0, self.group.checkedId())

    def set_current(self, index):
        b = self.group.button(index)
        if b:
            b.setChecked(True)

    def set_harmony(self, on):
        self.harm_btn.blockSignals(True)
        self.harm_btn.setChecked(bool(on))
        self.harm_btn.blockSignals(False)

    def set_preview_busy(self, busy):
        self.prev_btn.setEnabled(not busy)
        self.prev_btn.setText(tx("⏳  מכין האזנה מהירה...") if busy else PREVIEW_TEXT)
