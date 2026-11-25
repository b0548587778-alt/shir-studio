"""חלון הזנת קוד הרישיון."""
from .i18n import tx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QFileDialog

from . import license as lic
from .screens.common import big_button, label, STYLE, info, warn


class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tx("קוד רישיון"))
        self.setStyleSheet(STYLE)
        self.resize(720, 460)
        v = QVBoxLayout(self)
        v.setContentsMargins(30, 24, 30, 24)
        v.setSpacing(14)
        v.addWidget(label(tx("הזנת קוד רישיון"), "title"))
        v.addWidget(label(tx("הדבק כאן את הקוד שקיבלת (אפשר גם להקליד), ולחץ על \"אישור\".\n"
                          "הקוד נבדק במחשב עצמו - אין צורך באינטרנט."), "hint"))
        self.edit = QPlainTextEdit()
        self.edit.setLayoutDirection(Qt.LeftToRight)
        self.edit.setPlaceholderText("SHIR-XXXXX-XXXXX-...")
        v.addWidget(self.edit, 1)
        h = QHBoxLayout()
        ok = big_button(tx("אישור"), "green")
        ok.clicked.connect(self.apply)
        from_file = big_button(tx("פתח קובץ רישיון"), "light")
        from_file.setToolTip(tx("אם קיבלת את הקוד כקובץ טקסט"))
        from_file.clicked.connect(self.load_file)
        cancel = big_button(tx("סגור"), "light")
        cancel.clicked.connect(self.reject)
        h.addWidget(ok, 2); h.addWidget(from_file, 1); h.addWidget(cancel, 1)
        v.addLayout(h)

    def load_file(self):
        path, _filter = QFileDialog.getOpenFileName(self, tx("בחר את קובץ הרישיון"), "", tx("קובץ טקסט (*.txt);;כל הקבצים (*)"))
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                self.edit.setPlainText(f.read().strip())
        except OSError:
            warn(self, tx("לא הצלחתי לפתוח את הקובץ."))

    def apply(self):
        try:
            name = lic.activate(self.edit.toPlainText())
        except lic.LicenseError as e:
            warn(self, str(e))
            return
        info(self, tx("תודה!"), tx("הרישיון הופעל.\nהתוכנה רשומה על שם: {0}").format(name), tx("מעולה"))
        self.accept()
