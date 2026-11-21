import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from .log import log_error


def selftest():
    """בדיקה עצמית שרצה בבניית קובץ ההתקנה, בלי מסך."""
    import os, tempfile
    import numpy as np
    from .audio.fileio import SR, save, load
    from .audio.denoise import denoise
    t = np.arange(SR * 4) / SR
    x = (0.3 * np.sin(2 * np.pi * 220 * t) + 0.02 * np.random.randn(len(t))).astype("float32")
    y = denoise(x)
    p = os.path.join(tempfile.gettempdir(), "shir_selftest.mp3")
    save(p, y)
    assert len(load(p)) > SR * 3
    import sounddevice  # noqa: F401  בודק שכרטיס הקול נטען
    print("SELFTEST OK")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)

    def hook(t, v, tb):
        log_error("".join(traceback.format_exception(t, v, tb)))
        QMessageBox.warning(None, "שים לב", "משהו השתבש.\nנסה שוב. אם זה חוזר, סגור את התוכנה ופתח אותה מחדש.")
    sys.excepthook = hook

    from .ui import MainWindow
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
