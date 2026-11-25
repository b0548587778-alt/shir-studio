"""מסך ההמתנה בזמן שהשיר מוכן."""
from ..i18n import tx
import time

from PySide6.QtWidgets import QWidget, QVBoxLayout, QProgressBar

from .common import label

TITLE = tx("מכין את השיר...")


def eta_text(elapsed, percent):
    """הערכת הזמן שנשאר, לפי הקצב עד עכשיו."""
    if percent < 8 or percent >= 100 or elapsed < 3:
        return ""
    left = elapsed * (100 - percent) / percent
    if left < 8:
        return tx("עוד רגע...")
    if left < 50:
        return tx("נשארו בערך {0} שניות").format(int(round(left / 5) * 5))
    m = int(round(left / 60))
    return tx("נשארה בערך דקה") if m <= 1 else tx("נשארו בערך {0} דקות").format(m)


class WorkScreen(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 26, 40, 26)
        v.setSpacing(18)
        v.addStretch()
        self.title = label(TITLE, "title")
        v.addWidget(self.title)
        v.addWidget(label(tx("זה ייקח רגע. אין צורך ללחוץ על כלום."), "hint"))
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setFormat("%p%")
        v.addWidget(self.bar)
        self.eta = label("", "hint")
        v.addWidget(self.eta)
        v.addStretch()
        self._t0 = time.time()

    def begin(self, title=TITLE):
        self._t0 = time.time()
        self.bar.setValue(0)
        self.eta.setText("")
        self.title.setText(title)

    def set_progress(self, p):
        """מעדכן את פס ההתקדמות ומעריך כמה זמן נשאר."""
        self.bar.setValue(p)
        self.eta.setText(eta_text(time.time() - self._t0, p))
