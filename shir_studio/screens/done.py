"""מסך 'השיר מוכן': האזנה והשוואה, שיפורים, ושמירה."""
from ..i18n import tx
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
    tempo = Signal(float)           # 2 = ליווי מהיר פי שניים, 0.5 = איטי פי שניים
    practice = Signal()
    lyrics = Signal()
    best_take = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 10, 40, 12)
        v.setSpacing(10)
        v.addWidget(label(tx("השיר מוכן! ✔"), "title"))
        self.hint = label(tx("לחץ כדי להאזין ולהשוות"), "hint")
        v.addWidget(self.hint)
        b_res = big_button(tx("▶  האזן לשיר המוכן"), "green")
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
        b_org = big_button(tx("▶  ההקלטה המקורית"), "light")
        b_org.clicked.connect(self.play_original)
        self.b_compare = big_button(tx("⇄  לפני / אחרי"), "light")
        self.b_compare.setToolTip(tx("מחליף בין ההקלטה המקורית לשיר המוכן - באותו מקום בשיר"))
        self.b_compare.clicked.connect(self.compare)
        b_stop = big_button(tx("⏹  עצור"), "light")
        b_stop.clicked.connect(self.stop)
        for b in (b_org, self.b_compare, b_stop):
            b.setStyleSheet("font-size:22px; min-height:44px; padding:10px;")
            h2.addWidget(b)
        v.addLayout(h2)
        h3 = QHBoxLayout()
        b_other = big_button(tx("🎵  נסה סגנון ליווי אחר"), "light")
        b_other.clicked.connect(self.other_style)
        b_key = big_button(tx("🔄  הליווי לא מתאים?\nנסה התאמה אחרת"), "light")
        b_key.clicked.connect(self.other_key)
        for b in (b_other, b_key):
            b.setStyleSheet("font-size:22px; min-height:50px; padding:10px;")
            h3.addWidget(b)
        v.addLayout(h3)
        self.b_more = big_button(tx("🛠  עוד אפשרויות לשיפור השיר  ▾"), "light")
        self.b_more.setCheckable(True)
        self.b_more.setStyleSheet("font-size:19px; min-height:36px; padding:8px;")
        v.addWidget(self.b_more)
        self.more = QWidget()
        g = QGridLayout(self.more)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(8)
        self.b_undo = small_button(tx("↶  ביטול שינוי"))
        self.b_redo = small_button(tx("↷  החזר שינוי"))
        self.b_punch = small_button(tx("🎤  הקלט משפט מחדש"), tx("טעית במשפט אחד? שרים רק אותו שוב, בלי להתחיל מההתחלה"))
        self.b_overdub = small_button(tx("🎧  שיר שוב עם הליווי"), tx("שרים שוב עם אוזניות על הליווי המוכן - יוצא מדויק ונקי יותר"))
        rows = [
            [(self.b_undo, self.undo), (self.b_redo, self.redo),
             (small_button(tx("📈  גרף ותיקון ידני"), tx("מה שרת, מה תוקן - ואפשר לגרור צליל למקומו")), self.graph),
             (small_button(tx("✂  חיתוך")), self.trim)],
            [(self.b_punch, self.punch), (self.b_overdub, self.overdub),
             (small_button(tx("🎼  דף אקורדים"), tx("דף להדפסה למי שמלווה בגיטרה או בפסנתר")), self.chords),
             (small_button(tx("📤  קובץ לשליחה")), self.share)],
        ]
        for r, row in enumerate(rows):
            for c, (b, sig) in enumerate(row):
                b.clicked.connect(sig)
                g.addWidget(b, r, c)
        self.b_faster = small_button(tx("⏩  ליווי מהיר פי 2"), tx("הליווי מנגן לאט מדי ביחס לשיר? כך הוא יכפיל את הקצב"))
        self.b_slower = small_button(tx("⏪  ליווי איטי פי 2"), tx("הליווי רץ מהר מדי ביחס לשיר? כך הוא יחצה את הקצב"))
        self.b_faster.clicked.connect(lambda: self.tempo.emit(2.0))
        self.b_slower.clicked.connect(lambda: self.tempo.emit(0.5))
        self.b_practice = small_button(tx("🎓  תרגול"), tx("ציון דיוק לכל משפט, האזנה בלולאה ובהאטה (Ctrl+T)"))
        self.b_lyrics = small_button(tx("📝  מילים"), tx("מילות השיר: נשמרות בקובץ, מודפסות בדף האקורדים (Ctrl+L)"))
        self.b_take = small_button(tx("🏆  שיר שוב - ובחר את המיטב"),
                                   tx("שרים את השיר שוב עם הליווי, והתוכנה בוחרת לכל משפט את הביצוע הנקי יותר"))
        self.b_practice.clicked.connect(self.practice)
        self.b_lyrics.clicked.connect(self.lyrics)
        self.b_take.clicked.connect(self.best_take)
        g.addWidget(self.b_faster, 2, 0)
        g.addWidget(self.b_slower, 2, 1)
        g.addWidget(self.b_practice, 2, 2)
        g.addWidget(self.b_lyrics, 2, 3)
        g.addWidget(self.b_take, 3, 0, 1, 4)
        v.addWidget(self.more)
        self.more.setVisible(False)                  # מי שרק רוצה שיר מוכן רואה מסך פשוט; הכלים - בלחיצה
        self.b_more.toggled.connect(self.more.setVisible)
        v.addStretch()
        h = QHBoxLayout()
        b_save = big_button(tx("💾  שמור"), None)
        b_save.setMinimumHeight(80)
        b_save.clicked.connect(self.save)
        b_proj = big_button(tx("📁  שמור\nפרויקט"), "light")
        b_proj.clicked.connect(self.save_project)
        b_new = big_button(tx("שיר חדש"), "light")
        b_new.clicked.connect(self.new_song)
        b_adv = big_button(tx("⚙  מתקדם"), "light")
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
