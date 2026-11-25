"""חלון הרישיון: יצירת בקשת רישיון, וטעינת הרישיון שהתקבל."""
from .i18n import tx
from .i18n import direction
import os

from PySide6.QtCore import Qt, QStandardPaths
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QFileDialog, QLineEdit, QApplication

from . import license as lic
from .screens.common import big_button, label, STYLE, info, warn


class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tx("רישיון"))
        self.setLayoutDirection(direction())
        self.setStyleSheet(STYLE)
        self.resize(760, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(30, 20, 30, 20)
        v.setSpacing(10)
        v.addWidget(label(tx("רישיון לשיר סטודיו"), "title"))
        v.addWidget(label(tx("צעד 1: צור בקשת רישיון ושלח אותה למי שמכר לך את התוכנה."), "hint"))
        self.name = QLineEdit()
        self.name.setPlaceholderText(tx("השם שלך (יופיע ברישיון)"))
        v.addWidget(self.name)
        h1 = QHBoxLayout()
        b_file = big_button(tx("שמור בקשה לקובץ"), "light")
        b_file.clicked.connect(self.save_request)
        b_copy = big_button(tx("העתק בקשה"), "light")
        b_copy.setToolTip(tx("להדבקה במייל או בהודעה"))
        b_copy.clicked.connect(self.copy_request)
        h1.addWidget(b_file); h1.addWidget(b_copy)
        v.addLayout(h1)
        v.addWidget(label(tx("צעד 2: קיבלת קובץ רישיון? פתח אותו כאן, או הדבק את הקוד בתיבה.\n"
                             "הרישיון נבדק במחשב עצמו - אין צורך באינטרנט."), "hint"))
        self.edit = QPlainTextEdit()
        self.edit.setLayoutDirection(Qt.LeftToRight)
        v.addWidget(self.edit, 1)
        h = QHBoxLayout()
        from_file = big_button(tx("פתח קובץ רישיון"), "green")
        from_file.clicked.connect(self.load_file)
        ok = big_button(tx("אישור"), "light")
        ok.clicked.connect(self.apply)
        cancel = big_button(tx("סגור"), "light")
        cancel.clicked.connect(self.reject)
        h.addWidget(from_file, 2); h.addWidget(ok, 1); h.addWidget(cancel, 1)
        v.addLayout(h)

    def _request(self):
        try:
            return lic.request(self.name.text())
        except lic.LicenseError as e:
            warn(self, str(e))
            return None

    def save_request(self):
        text = self._request()
        if text is None:
            return
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation),
                             tx("בקשת רישיון - שיר סטודיו") + ".json")
        path, _filter = QFileDialog.getSaveFileName(self, tx("שמור את בקשת הרישיון"), start, tx("קובץ בקשה (*.json)"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            warn(self, tx("לא הצלחתי לשמור את הקובץ.\nנסה לשמור במקום אחר."))
            return
        info(self, tx("הבקשה נשמרה"), tx("שלח את הקובץ הזה למי שמכר לך את התוכנה:\n\n{0}").format(path), tx("הבנתי"))

    def copy_request(self):
        text = self._request()
        if text is None:
            return
        QApplication.clipboard().setText(text)
        info(self, tx("הבקשה הועתקה"), tx("עכשיו הדבק אותה במייל או בהודעה למי שמכר לך את התוכנה."), tx("הבנתי"))

    def load_file(self):
        path, _filter = QFileDialog.getOpenFileName(self, tx("בחר את קובץ הרישיון"), "",
                                                    tx("קובץ רישיון (*.json *.txt);;כל הקבצים (*)"))
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
                self.edit.setPlainText(f.read().strip())
        except OSError:
            warn(self, tx("לא הצלחתי לפתוח את הקובץ."))
            return
        self.apply()

    def apply(self):
        try:
            p = lic.activate(self.edit.toPlainText().strip())
        except lic.LicenseError as e:
            warn(self, str(e))
            return
        info(self, tx("תודה!"), tx("הרישיון הופעל.\nרשום על שם: {0}\nבתוקף עד: {1}").format(
            p.get("name", ""), lic_date(p["expiresAt"])), tx("מעולה"))
        self.accept()


def lic_date(ms):
    import datetime
    return datetime.date.fromtimestamp(ms / 1000).strftime("%d/%m/%Y")
