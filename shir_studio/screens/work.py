"""מסך ההמתנה בזמן שהשיר מוכן."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QProgressBar

from .common import label

TITLE = "מכין את השיר..."


class WorkScreen(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 26, 40, 26)
        v.setSpacing(18)
        v.addStretch()
        self.title = label(TITLE, "title")
        v.addWidget(self.title)
        v.addWidget(label("זה ייקח רגע. אין צורך ללחוץ על כלום.", "hint"))
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setFormat("%p%")
        v.addWidget(self.bar)
        v.addStretch()

    def begin(self, title=TITLE):
        self.bar.setValue(0)
        self.title.setText(title)
