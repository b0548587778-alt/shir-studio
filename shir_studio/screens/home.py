"""מסך הפתיחה: הקלטה, בחירת קובץ, פרויקט שמור, כמה שירים ברצף, מחרוזת והפרדת קול."""
from ..i18n import tx
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QSpinBox

from .. import APP_NAME, APP_VERSION
from .common import big_button, label


class HomeScreen(QWidget):
    record = Signal()
    choose = Signal()
    open_project = Signal()
    batch = Signal()
    medley = Signal()
    separate = Signal()
    check_update = Signal()
    mic_check = Signal()
    shortcuts = Signal()
    license = Signal()
    language = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 26, 40, 16)
        v.setSpacing(18)
        v.addWidget(label(APP_NAME, "title"))
        v.addWidget(label(tx("שר שיר - ואנחנו נהפוך אותו לשיר מוכן"), "hint"))
        v.addStretch()
        h = QHBoxLayout()
        h.setSpacing(30)
        b1 = big_button(tx("🎤  הקלט שיר"), "huge")
        b1.clicked.connect(self.record)
        b2 = big_button(tx("📁  בחר קובץ\nמהמחשב"), "huge")
        b2.setStyleSheet("background:#2c7a3f;")
        b2.clicked.connect(self.choose)
        h.addStretch(); h.addWidget(b1); h.addWidget(b2); h.addStretch()
        v.addLayout(h)
        v.addWidget(label(tx("אפשר גם לגרור קובץ שיר לכאן"), "tiny"))
        m = QHBoxLayout()
        self.metro_on = QCheckBox(tx("🥁 מטרונום בזמן ההקלטה (עדיף עם אוזניות)"))
        self.metro_bpm = QSpinBox()
        self.metro_bpm.setRange(40, 220)
        self.metro_bpm.setValue(100)
        self.metro_bpm.setSuffix(" BPM")
        self.b_mic = big_button(tx("🎚 בדיקת מיקרופון"), "link")
        self.b_mic.setStyleSheet("font-size:20px;")
        self.b_mic.setToolTip(tx("לפני שמקליטים שיר שלם: האם העוצמה מתאימה, והאם יש רעש רקע (Ctrl+M)"))
        self.b_mic.clicked.connect(self.mic_check)
        m.addStretch(); m.addWidget(self.metro_on); m.addWidget(self.metro_bpm); m.addWidget(self.b_mic); m.addStretch()
        v.addLayout(m)
        v.addStretch()
        h2 = QHBoxLayout()
        for text, sig in ((tx("📂  פתח פרויקט שמור"), self.open_project), (tx("📚  כמה שירים ברצף"), self.batch),
                          (tx("🎼  מחרוזת"), self.medley), (tx("🎚  הפרדת קול\nופלייבק"), self.separate)):
            b = big_button(text, "light")
            b.setStyleSheet("font-size:21px; padding:12px 10px;")
            if sig is self.separate:
                b.setToolTip(tx("הפרדת שירה מנגינה, גרסה ווקאלית, הפרדה לכלים, פלייבק בסולם ובקצב שלך, ושירה על פלייבק"))
            b.clicked.connect(sig)
            h2.addWidget(b)
        v.addLayout(h2)
        lf = QHBoxLayout()
        self.lic_label = label("", "tiny")
        self.b_license = big_button(tx("יש לי קוד רישיון"), "link")
        self.b_license.clicked.connect(self.license)
        self.b_lang = big_button(tx("שפה / שפּראַך / Language"), "link")
        self.b_lang.clicked.connect(self.language)
        lf.addStretch(); lf.addWidget(self.lic_label); lf.addWidget(self.b_license); lf.addWidget(self.b_lang); lf.addStretch()
        v.addLayout(lf)
        f = QHBoxLayout()
        self.version = label(tx("גרסה ⁦{0}⁩").format(APP_VERSION), "tiny")
        self.b_update = big_button(tx("בדוק אם יש גרסה חדשה (דרך האינטרנט)"), "link")
        self.b_update.clicked.connect(self.check_update)
        self.b_keys = big_button(tx("קיצורי מקלדת (F1)"), "link")
        self.b_keys.clicked.connect(self.shortcuts)
        f.addStretch(); f.addWidget(self.version); f.addWidget(self.b_update); f.addWidget(self.b_keys); f.addStretch()
        v.addLayout(f)

    def show_license(self, st):
        """st: מה ש-license.status() מחזיר."""
        if st["licensed"]:
            self.lic_label.setText(tx("גרסה מלאה · רשום על שם: {0}").format(st["name"]))
            self.b_license.hide()
        else:
            if st["left"] > 0:
                self.lic_label.setText(tx("גרסת ניסיון · נשארו {0} שירים לשמירה").format(st["left"]))
            else:
                self.lic_label.setText(tx("גרסת הניסיון הסתיימה · כדי לשמור שירים צריך קוד רישיון"))
            self.b_license.show()
