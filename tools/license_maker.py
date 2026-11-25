"""יוצר הרישיונות - כלי רק לבעל התוכנה (לא נכנס לקובץ ההתקנה של הלקוחות).

הפעלה:  python tools/license_maker.py
בפעם הראשונה לוחצים "צור מפתח סודי". המפתח הסודי נשמר בקובץ במחשב שלך בלבד (בתיקיית המשתמש,
"ShirStudio-secret-key.txt") - צריך לגבות אותו במקום בטוח ולא לתת לאף אחד. את "המפתח הציבורי"
שהכלי מציג מכניסים פעם אחת לקובץ shir_studio/license_key.py. אחר כך: כותבים שם לקוח ומקבלים קוד."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from shir_studio import ed25519, license as lic       # noqa: E402

KEY_FILE = os.path.join(os.path.expanduser("~"), "ShirStudio-secret-key.txt")
LOG_FILE = os.path.join(os.path.expanduser("~"), "ShirStudio-customers.txt")


def load_secret():
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            raw = bytes.fromhex(f.read().strip())
        return raw if len(raw) == 32 else None
    except (OSError, ValueError):
        return None


def create_secret():
    if os.path.exists(KEY_FILE):
        raise RuntimeError("כבר קיים מפתח סודי. לא יוצרים חדש, כדי שהקודים שכבר נמכרו ימשיכו לעבוד.")
    raw = os.urandom(32)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(raw.hex())
    return raw


def code_for(name):
    secret = load_secret()
    if secret is None:
        raise RuntimeError("עוד אין מפתח סודי. לחץ קודם על 'צור מפתח סודי'.")
    code = lic.make_code(secret, name)
    try:
        import datetime
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.date.today()}\t{name}\t{code}\n")
    except OSError:
        pass
    return code


def main():
    if len(sys.argv) > 1:                       # שימוש בלי חלון:  license_maker.py "שם הלקוח"
        print(code_for(" ".join(sys.argv[1:])))
        return
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
                                   QPlainTextEdit, QMessageBox)
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    w = QWidget()
    w.setWindowTitle("שיר סטודיו - יוצר הרישיונות (רק לבעל התוכנה)")
    w.setStyleSheet("QWidget{font-size:18px;} QPushButton{padding:12px;font-weight:bold;}")
    v = QVBoxLayout(w)
    state = QLabel()
    state.setWordWrap(True)
    pub = QLineEdit()
    pub.setReadOnly(True)
    b_key = QPushButton("צור מפתח סודי (פעם אחת בלבד)")
    name = QLineEdit()
    name.setPlaceholderText("שם הלקוח (יופיע אצלו בתוכנה)")
    b_make = QPushButton("צור קוד רישיון")
    out = QPlainTextEdit()
    out.setReadOnly(True)
    b_copy = QPushButton("העתק את הקוד")

    def refresh():
        s = load_secret()
        b_key.setVisible(s is None)
        b_make.setEnabled(s is not None)
        if s is None:
            state.setText("עוד אין מפתח סודי במחשב הזה.")
            pub.setText("")
        else:
            state.setText(f"המפתח הסודי שמור בקובץ:\n{KEY_FILE}\nגבה אותו במקום בטוח ואל תיתן אותו לאף אחד.\n\n"
                          "המפתח הציבורי (אותו מכניסים לתוכנה - הוא לא סוד):")
            pub.setText(ed25519.public_key(s).hex())

    def on_key():
        try:
            create_secret()
        except (RuntimeError, OSError) as e:
            QMessageBox.warning(w, "שים לב", str(e))
        refresh()

    def on_make():
        try:
            out.setPlainText(code_for(name.text()))
        except (RuntimeError, lic.LicenseError) as e:
            QMessageBox.warning(w, "שים לב", str(e))

    b_key.clicked.connect(on_key)
    b_make.clicked.connect(on_make)
    b_copy.clicked.connect(lambda: app.clipboard().setText(out.toPlainText()))
    for x in (state, pub, b_key, QLabel("קוד חדש ללקוח:"), name, b_make, out, b_copy):
        v.addWidget(x)
    refresh()
    w.resize(640, 560)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
