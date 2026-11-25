"""חלון מילות השיר: מקלידים (או מדביקים) את המילים, והן נשמרות עם השיר."""
from .i18n import tx
from .i18n import direction
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit

from .trimview import CSS

MAX_CHARS = 20000


class LyricsDialog(QDialog):
    def __init__(self, parent, text=""):
        super().__init__(parent)
        self.setWindowTitle(tx("מילות השיר"))
        self.setLayoutDirection(direction())
        self.setStyleSheet(CSS + "QPlainTextEdit { background: white; font-size: 22px; border: 2px solid #c9d2dc; "
                                 "border-radius: 8px; padding: 8px; }")
        v = QVBoxLayout(self)
        lab = QLabel(tx("הקלד או הדבק כאן את מילות השיר. שורה ריקה מפרידה בין בית לבית.\n"
                     "המילים נשמרות בתוך קובץ השיר (ומופיעות בנגנים שמציגים מילים), מודפסות בדף האקורדים, "
                     "ומוצגות על המסך כששרים שוב עם הליווי."))
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.edit = QPlainTextEdit()
        opt = self.edit.document().defaultTextOption()
        opt.setTextDirection(direction())             # עברית: השורות מתחילות מימין
        self.edit.document().setDefaultTextOption(opt)
        self.edit.setPlainText(text or "")
        self.edit.setPlaceholderText(tx("מילות השיר..."))
        v.addWidget(self.edit, 1)
        h = QHBoxLayout()
        ok = QPushButton(tx("✔  שמור"))
        ok.setStyleSheet("background:#2c7a3f; color:white; font-weight:bold;")
        ok.clicked.connect(self.accept)
        clear = QPushButton(tx("נקה"))
        clear.clicked.connect(self.edit.clear)
        cancel = QPushButton(tx("ביטול"))
        cancel.clicked.connect(self.reject)
        h.addWidget(ok, 2); h.addWidget(clear); h.addWidget(cancel)
        v.addLayout(h)
        self.resize(640, 620)

    def text(self):
        lines = [l.rstrip() for l in self.edit.toPlainText().replace("\r", "").split("\n")]
        return "\n".join(lines).strip()[:MAX_CHARS]
