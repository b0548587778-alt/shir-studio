"""חלון בחירת השפה - מוצג בהפעלה הראשונה, ונפתח גם ממסך הפתיחה. כתוב בשלוש השפות יחד."""
from .i18n import tx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton

from .i18n import LANGS

LOOK = """
QDialog { background: #f7f5f0; }
QLabel { font-family: 'Segoe UI', 'Arial'; font-size: 24px; color: #1f3a5f; font-weight: bold; }
QPushButton { font-family: 'Segoe UI', 'Arial'; font-size: 30px; font-weight: bold; min-height: 84px; border-radius: 18px;
              background: white; color: #1f3a5f; border: 2px solid #ddd6c8; }
QPushButton:hover { background: #fbf6e9; border-color: #c8962e; }
QPushButton[current="true"] { border: 3px solid #2e7d4f; background: #e8f4ec; }
"""


class LanguageDialog(QDialog):
    def __init__(self, parent=None, current=None):
        super().__init__(parent)
        self.code = current
        self.setWindowTitle(tx("שפה · שפּראַך · Language"))
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(LOOK)
        self.resize(520, 440)
        v = QVBoxLayout(self)
        v.setContentsMargins(36, 28, 36, 28)
        v.setSpacing(16)
        head = QLabel(tx("בחר שפה  ·  קלייַב אויס אַ שפּראַך  ·  Choose a language"))
        head.setAlignment(Qt.AlignCenter)
        head.setWordWrap(True)
        v.addWidget(head)
        self.buttons = {}
        for code, name in LANGS.items():
            b = QPushButton(name)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("current", "true" if code == current else "false")
            b.clicked.connect(lambda _checked=False, c=code: self.pick(c))
            self.buttons[code] = b
            v.addWidget(b)

    def pick(self, code):
        self.code = code
        self.accept()
