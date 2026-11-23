"""מסך 'השיר מוכן': האזנה והשוואה, שיפורים, ושמירה."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSlider

from .common import big_button, small_button, label, fmt_time


class DoneScreen(QWidget):
    play_result = Signal()
    play_original = Signal()
    compare = Signal()
    stop = Signal()
    seek = Signal(float)            # 0..1
    other_style = Signal()
    other_key = Signal()
    undo = Signal()
    redo = Signal()
    graph = Signal()
    punch = Signal()
    overdub = Signal()
    trim = Signal()
    save_project = Signal()
    share = Signal()
    chords = Signal()
    save = Signal()
    new_song = Signal()
    advanced = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 20, 40, 20)
        v.setSpacing(12)
        v.addWidget(label("השיר מוכן! ✔", "title"))
        self.hint = label("לחץ כדי להאזין ולהשוות", "hint")
        v.addWidget(self.hint)
        b_res = big_button("▶  האזן לשיר המוכן", "green")
        b_res.setMinimumHeight(80)
        b_res.clicked.connect(self.play_result)
        v.addWidget(b_res)
        pr = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderReleased.connect(lambda: self.seek.emit(self.slider.value() / 1000))
        self.pos_label = QLabel("0:00")
        self.pos_label.setMinimumWidth(110)
        pr.addWidget(self.pos_label); pr.addWidget(self.slider, 1)
        v.addLayout(pr)
        h2 = QHBoxLayout()
        b_org = big_button("▶  ההקלטה המקורית", "light")
        b_org.clicked.connect(self.play_original)
        self.b_compare = big_button("⇄  לפני / אחרי", "light")
        self.b_compare.setToolTip("מחליף בין ההקלטה המקורית לשיר המוכן - באותו מקום בשיר")
        self.b_compare.clicked.connect(self.compare)
        b_stop = big_button("⏹  עצור", "light")
        b_stop.clicked.connect(self.stop)
        for b in (b_org, self.b_compare, b_stop):
            b.setStyleSheet("font-size:22px; min-height:44px; padding:10px;")
            h2.addWidget(b)
        v.addLayout(h2)
        h3 = QHBoxLayout()
        b_other = big_button("🎵  נסה סגנון ליווי אחר", "light")
        b_other.clicked.connect(self.other_style)
        b_key = big_button("🔄  הליווי לא מתאים?\nנסה התאמה אחרת", "light")
        b_key.clicked.connect(self.other_key)
        for b in (b_other, b_key):
            b.setStyleSheet("font-size:22px; min-height:50px; padding:10px;")
            h3.addWidget(b)
        v.addLayout(h3)
        g = QGridLayout()
        g.setSpacing(10)
        self.b_undo = small_button("↶  ביטול שינוי")
        self.b_redo = small_button("↷  החזר שינוי")
        self.b_punch = small_button("🎤  הקלט משפט מחדש", "טעית במשפט אחד? שרים רק אותו שוב, בלי להתחיל מההתחלה")
        self.b_overdub = small_button("🎧  שיר שוב עם הליווי", "שרים שוב עם אוזניות על הליווי המוכן - יוצא מדויק ונקי יותר")
        rows = [
            [(self.b_undo, self.undo), (self.b_redo, self.redo),
             (small_button("📈  גרף ותיקון ידני", "מה שרת, מה תוקן - ואפשר לגרור צליל למקומו"), self.graph),
             (small_button("✂  חיתוך"), self.trim)],
            [(self.b_punch, self.punch), (self.b_overdub, self.overdub),
             (small_button("🎼  דף אקורדים", "דף להדפסה למי שמלווה בגיטרה או בפסנתר"), self.chords),
             (small_button("📤  קובץ לשליחה"), self.share)],
        ]
        for r, row in enumerate(rows):
            for c, (b, sig) in enumerate(row):
                b.clicked.connect(sig)
                g.addWidget(b, r, c)
        v.addLayout(g)
        v.addStretch()
        h = QHBoxLayout()
        b_save = big_button("💾  שמור", None)
        b_save.setMinimumHeight(80)
        b_save.clicked.connect(self.save)
        b_proj = big_button("📁  שמור\nפרויקט", "light")
        b_proj.clicked.connect(self.save_project)
        b_new = big_button("שיר חדש", "light")
        b_new.clicked.connect(self.new_song)
        b_adv = big_button("⚙  מתקדם", "light")
        b_adv.clicked.connect(self.advanced)
        for b in (b_proj, b_new, b_adv):
            b.setStyleSheet("font-size:21px; padding:10px;")
        h.addWidget(b_save, 3); h.addWidget(b_proj, 1); h.addWidget(b_new, 1); h.addWidget(b_adv, 1)
        v.addLayout(h)

    def show_position(self, pos, total, what=""):
        """pos=None כשלא מנגן."""
        if self.slider.isSliderDown():
            return
        txt = f"{fmt_time(pos or 0)} / {fmt_time(total)}"
        self.pos_label.setText(f"{txt}   {what}" if what and pos is not None else txt)
        if pos is not None:
            self.slider.setValue(int(1000 * pos / max(total, 1e-6)))
