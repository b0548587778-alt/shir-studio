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
    from .pipeline import Song
    from .music.styles import load_styles
    t = np.arange(SR * 12) / SR
    f = 220 * 2 ** (np.floor(t * 2) % 5 / 12)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = sum(np.sin(k * ph) / k for k in range(1, 12)) * ((t * 2) % 1 < 0.85)
    x = (0.3 * x + 0.01 * np.random.randn(len(t))).astype("float32")
    song = Song(x)
    styles = load_styles()
    assert len(styles) >= 5
    from .music import sampler
    assert sampler.available(), "sample pack missing"
    for st in styles:
        y = song.make(st, lambda p, m=None: None)
        assert np.isfinite(y).all() and y.ndim == 2
    p = os.path.join(tempfile.gettempdir(), "shir_selftest.mp3")
    save(p, y)
    assert len(load(p)) > SR * 10
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

    import os
    from PySide6.QtGui import QIcon
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    app.setWindowIcon(QIcon(os.path.join(base, "assets", "icon.png")))
    from .ui import MainWindow
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
