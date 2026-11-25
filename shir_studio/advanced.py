"""חלון 'אפשרויות מתקדמות' - לאנשים טכנולוגיים ולמוזיקאים. המסך הרגיל נשאר פשוט."""
from .i18n import tx
from .i18n import direction
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QSlider, QLabel, QComboBox,
    QSpinBox, QRadioButton, QButtonGroup, QPlainTextEdit, QPushButton, QCheckBox, QScrollArea,
    QLineEdit,
    QWidget,
)

from .pipeline import Settings
from .music.theory import NOTE_NAMES, MODES

CSS = """
QWidget { font-size: 17px; }
QGroupBox { font-weight: bold; font-size: 19px; border: 2px solid #c9d2dc; border-radius: 12px;
            margin-top: 16px; padding: 14px 10px 10px 10px; background: #fbfaf6; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; padding: 0 8px; }
QPushButton { font-size: 19px; min-height: 44px; padding: 6px 18px; border-radius: 12px; }
QPlainTextEdit { background: white; border: 2px solid #c9d2dc; border-radius: 8px; font-size: 18px;
                 font-family: Consolas, 'DejaVu Sans Mono', monospace; }
QComboBox, QSpinBox { background: white; min-height: 34px; padding: 2px 8px; }
QLabel#small { color: #5a6571; font-size: 15px; }
"""


def _slider(lo, hi, val, fmt):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(int(val))
    lab = QLabel(fmt(val))
    lab.setMinimumWidth(80)
    s.valueChanged.connect(lambda v: lab.setText(fmt(v)))
    h.addWidget(s, 1)
    h.addWidget(lab)
    w.slider = s
    return w


def _db(v):
    return f"{v:+d} dB" if v else tx("רגיל")


class AdvancedDialog(QDialog):
    def __init__(self, parent, settings: Settings, info=None, extras=False, fmt="mp3", style=None, artist=""):
        super().__init__(parent)
        self.setWindowTitle(tx("אפשרויות מתקדמות"))
        self.setLayoutDirection(direction())
        self.setStyleSheet(CSS)
        self.resize(720, 760)
        self.info = info
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        v = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        if info:
            t = tx("זוהה אוטומטית: סולם {0}").format(info['key'])
            t += tx(" · קצב ⁦{0} BPM⁩").format(info['tempo']) if info["steady"] else tx(" · קצב חופשי")
            lab = QLabel(t)
            lab.setObjectName("small")
            v.addWidget(lab)

        # ---- קול
        g = QGroupBox(tx("קול"))
        f = QFormLayout(g)
        self.denoise = _slider(0, 100, settings.denoise, lambda x: f"{x}%")
        self.tune = _slider(0, 100, settings.tune, lambda x: tx("כבוי") if x == 0 else f"{x}%")
        self.voice_db = _slider(-9, 9, settings.voice_db, _db)
        self.transpose = QSpinBox()
        self.transpose.setRange(-7, 7)
        self.transpose.setValue(settings.transpose)
        self.transpose.setSuffix(tx(" חצאי טונים"))
        f.addRow(tx("ניקוי רעשים:"), self.denoise)
        f.addRow(tx("תיקון זיופים:"), self.tune)
        f.addRow(tx("עוצמת הקול:"), self.voice_db)
        f.addRow(tx("העברת סולם (טרנספוזיציה):"), self.transpose)
        voice = (info or {}).get("voice")
        if voice:
            sug = voice["suggest"]
            vw = QWidget()
            vh = QHBoxLayout(vw)
            vh.setContentsMargins(0, 0, 0, 0)
            txt = tx("המנעד שלך בשיר: מ{0} עד {1}. ").format(voice['low'], voice['high'])
            if sug:
                way = tx("העלאה") if sug > 0 else tx("הורדה")
                txt += tx("מומלץ: {0} של ⁦{1}⁩ חצאי טונים, לגובה נוח יותר.").format(way, abs(sug))
            else:
                txt += tx("השיר בגובה נוח.")
            lab = QLabel(txt)
            lab.setObjectName("small")
            lab.setWordWrap(True)
            vh.addWidget(lab, 1)
            if sug:
                b = QPushButton(tx("החל המלצה"))
                b.clicked.connect(lambda: self.transpose.setValue(sug))
                vh.addWidget(b)
            f.addRow("", vw)
        self.harmony = QComboBox()
        for label, val in ((tx("בלי"), "off"), (tx("אוטומטי"), "auto"), (tx("מעל המנגינה"), "above"),
                           (tx("מתחת למנגינה"), "below"), (tx("שלושה קולות (מעל ומתחת)"), "three")):
            self.harmony.addItem(label, val)
        self.harmony.setCurrentIndex(max(0, self.harmony.findData(settings.harmony)))
        f.addRow(tx("קול שני (הרמוניה):"), self.harmony)
        self.choir = QCheckBox(tx("מקהלה - הקול נשמע כמו כמה זמרים"))
        self.choir.setChecked(bool(settings.choir))
        f.addRow("", self.choir)
        from .audio.polish import TONES
        self.voice_tone = QComboBox()
        for val, name in TONES.items():
            self.voice_tone.addItem(name, val)
        self.voice_tone.setCurrentIndex(max(0, self.voice_tone.findData(settings.voice_tone)))
        f.addRow(tx("אופי הקול:"), self.voice_tone)
        v.addWidget(g)

        # ---- מוזיקה
        g = QGroupBox(tx("מוזיקה"))
        f = QFormLayout(g)
        self.key = QComboBox()
        self.key.addItem(tx("אוטומטי"), None)
        for mode in MODES:
            for t in range(12):
                self.key.addItem(f"{NOTE_NAMES[t]} {MODES[mode][0]}", f"{t}:{mode}")
        if settings.key:
            i = self.key.findData(f"{settings.key[0]}:{settings.key[1]}")
            self.key.setCurrentIndex(max(0, i))
        f.addRow(tx("סולם:"), self.key)

        tw = QWidget()
        th = QHBoxLayout(tw)
        th.setContentsMargins(0, 0, 0, 0)
        self.t_auto = QRadioButton(tx("אוטומטי"))
        self.t_manual = QRadioButton(tx("קבוע"))
        self.t_free = QRadioButton(tx("חופשי (בלי תופים)"))
        self.tgroup = QButtonGroup(self)
        for b in (self.t_auto, self.t_manual, self.t_free):
            self.tgroup.addButton(b)
        self.bpm = QSpinBox()
        self.bpm.setRange(40, 220)
        self.bpm.setSuffix(" BPM")
        self.bpm.setValue(int(round(settings.bpm or (info["tempo"] if info else 110))))
        {"auto": self.t_auto, "manual": self.t_manual, "free": self.t_free}[settings.tempo_mode].setChecked(True)
        th.addWidget(self.t_auto); th.addWidget(self.t_manual); th.addWidget(self.bpm); th.addWidget(self.t_free)
        th.addStretch()
        f.addRow(tx("קצב:"), tw)

        self.meter = QComboBox()
        self.meter.addItem(tx("אוטומטי (4/4, או ואלס כשהוא מזוהה)"), 0)
        self.meter.addItem(tx("4/4 (רגיל)"), 4)
        self.meter.addItem(tx("3/4 (ואלס)"), 3)
        self.meter.addItem(tx("6/8 (מתנדנד)"), 6)
        cur = 0 if (settings.meter == 4 and settings.auto_meter) else settings.meter
        self.meter.setCurrentIndex(max(0, self.meter.findData(cur)))
        f.addRow(tx("משקל:"), self.meter)
        self.cpb = QComboBox()
        self.cpb.addItem(tx("שניים בתיבה"), 2)
        self.cpb.addItem(tx("אחד בתיבה"), 1)
        self.cpb.setCurrentIndex(0 if settings.chords_per_bar == 2 else 1)
        f.addRow(tx("החלפת אקורדים:"), self.cpb)
        self.accomp_db = _slider(-12, 9, settings.accomp_db, _db)
        self.reverb = _slider(0, 200, settings.reverb, lambda x: f"{x}%")
        f.addRow(tx("עוצמת הליווי:"), self.accomp_db)
        f.addRow(tx("הדהוד (ריוורב):"), self.reverb)
        from .audio.mix import SPACE_NAMES
        self.space = QComboBox()
        for val, name in SPACE_NAMES.items():
            self.space.addItem(name, val)
        self.space.setCurrentIndex(max(0, self.space.findData(settings.space)))
        f.addRow(tx("גודל האולם:"), self.space)
        from .music.arrange import INTROS, ENDINGS
        self.intro, self.ending = QComboBox(), QComboBox()
        for box, names, cur in ((self.intro, INTROS, settings.intro), (self.ending, ENDINGS, settings.ending)):
            box.addItem(tx("לפי הסגנון (רגיל)"), "auto")
            for val, name in names.items():
                box.addItem(name, val)
            box.setCurrentIndex(max(0, box.findData(cur)))
        self.intro.setToolTip(tx("מה הכלי המוביל מנגן לפני שהזמר נכנס"))
        self.ending.setToolTip(tx("איך השיר נגמר אחרי שהשירה מסתיימת"))
        f.addRow(tx("הפתיח:"), self.intro)
        f.addRow(tx("הסיום:"), self.ending)
        self.modulate = QCheckBox(tx("עליית סולם (חצי טון) בפזמון האחרון - הקול והליווי עולים יחד"))
        self.modulate.setChecked(bool(settings.modulate))
        f.addRow("", self.modulate)
        v.addWidget(g)

        # ---- כלים
        self.swaps = {}
        if style:
            from .music.styles import instruments_of, SWAPPABLE
            insts = instruments_of(style)
            if insts:
                g = QGroupBox(tx("כלי הנגינה בסגנון '{0}'").format(style.get('name', '')))
                f = QFormLayout(g)
                cur = settings.swaps or {}
                for inst in insts:
                    cb = QComboBox()
                    for k, name in SWAPPABLE.items():
                        cb.addItem(name, k)
                    cb.setCurrentIndex(max(0, cb.findData(cur.get(inst, inst))))
                    f.addRow(f"{SWAPPABLE[inst]} ←", cb)
                    self.swaps[inst] = cb
                v.addWidget(g)

        # ---- חלקי השיר (בית / פזמון)
        self.sec_boxes = []
        self.sec_auto = []
        phrases = (info or {}).get("phrases") or []
        if phrases:
            g = QGroupBox(tx("חלקי השיר - בית או פזמון"))
            f = QFormLayout(g)
            h = QLabel(tx("בבית הליווי רגוע, ובפזמון מלא וחזק. התוכנה מנחשת לבד - אפשר לשנות."))
            h.setObjectName("small")
            h.setWordWrap(True)
            f.addRow(h)
            cur = settings.sections or []
            for i, (s, e, lvl) in enumerate(phrases):
                cb = QComboBox()
                cb.addItem(tx("בית (רגוע)"), 0)
                cb.addItem(tx("פזמון (מלא)"), 1)
                cb.setCurrentIndex(int(cur[i]) if i < len(cur) else int(lvl))
                f.addRow(tx("משפט {0}  (⁦{1}:{2:02d}⁩):").format(i + 1, int(s) // 60, int(s) % 60), cb)
                self.sec_boxes.append(cb)
                self.sec_auto.append(int(lvl))
            v.addWidget(g)

        # ---- אקורדים
        g = QGroupBox(tx("אקורדים - למוזיקאים"))
        gv = QVBoxLayout(g)
        hint = QLabel(tx("כתוב תיבה אחרי תיבה, מופרדות בקו ישר. כמה אקורדים באותה תיבה - עם רווח ביניהם. "
                      "מקף = כמו האקורד הקודם. השאר ריק כדי שהתוכנה תבחר לבד. דוגמה:"))
        hint.setObjectName("small")
        hint.setWordWrap(True)
        gv.addWidget(hint)
        ex = QLabel("Am | Dm E | Am | -")
        ex.setObjectName("small")
        ex.setLayoutDirection(Qt.LeftToRight)
        ex.setAlignment(Qt.AlignLeft)
        gv.addWidget(ex)
        self.chords = QPlainTextEdit()
        self.chords.setLayoutDirection(Qt.LeftToRight)
        self.chords.setPlainText(settings.chords_text)
        if info:
            self.chords.setPlaceholderText(info["chords"])
        self.chords.setMinimumHeight(110)
        gv.addWidget(self.chords)
        row = QHBoxLayout()
        b_fill = QPushButton(tx("הכנס את האקורדים שזוהו לעריכה"))
        b_fill.setEnabled(bool(info))
        b_fill.clicked.connect(lambda: self.chords.setPlainText(info["chords"]))
        b_clear = QPushButton(tx("נקה (אוטומטי)"))
        b_clear.clicked.connect(self.chords.clear)
        row.addWidget(b_fill); row.addWidget(b_clear); row.addStretch()
        gv.addLayout(row)
        v.addWidget(g)

        # ---- שמירה
        g = QGroupBox(tx("שמירה"))
        f = QFormLayout(g)
        self.fmt = QComboBox()
        self.fmt.addItem("MP3", "mp3")
        self.fmt.addItem(tx("WAV (איכות מלאה)"), "wav")
        self.fmt.addItem(tx("FLAC (איכות מלאה, קובץ קטן יותר)"), "flac")
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(fmt)))
        self.extras = QCheckBox(tx("שמור גם קול וליווי בקבצים נפרדים + קובץ MIDI"))
        self.extras.setChecked(extras)
        from .audio.loudness import NAMES as LOUD_NAMES
        self.loudness = QComboBox()
        for val, name in LOUD_NAMES.items():
            self.loudness.addItem(name, val)
        self.loudness.setCurrentIndex(max(0, self.loudness.findData(settings.loudness)))
        f.addRow(tx("עוצמת השיר:"), self.loudness)
        self.artist = QLineEdit(artist or "")
        self.artist.setPlaceholderText(tx("נכתב בתוך קובץ ה-MP3 ומופיע בנגן"))
        f.addRow(tx("שם הזמר:"), self.artist)
        f.addRow(tx("סוג קובץ:"), self.fmt)
        f.addRow("", self.extras)
        v.addWidget(g)

        # ---- כפתורים
        row = QHBoxLayout()
        ok = QPushButton(tx("אישור"))
        ok.setStyleSheet("background:#2c7a3f; color:white; font-weight:bold;")
        ok.clicked.connect(self.accept)
        reset = QPushButton(tx("החזר הכול לרגיל"))
        reset.clicked.connect(self.reset)
        mine = QPushButton(tx("⭐  שמור כטעם שלי"))
        mine.setToolTip(tx("העוצמות, הניקוי, ההדהוד, הקול השני, הכלים וסוג הקובץ יהיו ברירת המחדל בכל שיר חדש"))
        mine.clicked.connect(lambda: self.done(3))
        cancel = QPushButton(tx("ביטול"))
        cancel.clicked.connect(self.reject)
        row.addWidget(ok, 2); row.addWidget(mine, 2); row.addWidget(reset, 1); row.addWidget(cancel, 1)
        self._orig = settings
        outer.addLayout(row)

    def reset(self):
        self.result_settings = Settings()
        self.result_extras, self.result_fmt = False, "mp3"
        self.done(2)

    def _key(self):
        d = self.key.currentData()
        if not d:
            return None
        t, m = d.split(":")
        return (int(t), m)

    def _sections(self):
        vals = [cb.currentData() for cb in self.sec_boxes]
        return vals if vals and vals != self.sec_auto else None

    def settings(self) -> Settings:
        mode = "auto" if self.t_auto.isChecked() else ("manual" if self.t_manual.isChecked() else "free")
        o = self._orig
        # קצב שנקבע במדויק (למשל 117.4) לא מתעגל סתם כשלא נגעו בו
        bpm = o.bpm if (o.bpm and self.bpm.value() == int(round(o.bpm))) else self.bpm.value()
        return Settings(
            denoise=self.denoise.slider.value(), tune=self.tune.slider.value(),
            key=self._key(), tempo_mode=mode, bpm=bpm,
            modulate=self.modulate.isChecked(), note_edits=o.note_edits, tempo_scale=o.tempo_scale,
            meter=self.meter.currentData() or 4, auto_meter=self.meter.currentData() == 0, chords_per_bar=self.cpb.currentData(),
            chords_text=self.chords.toPlainText().strip(), transpose=self.transpose.value(),
            voice_db=self.voice_db.slider.value(), accomp_db=self.accomp_db.slider.value(),
            reverb=self.reverb.slider.value(), harmony=self.harmony.currentData(),
            choir=self.choir.isChecked(), sections=self._sections(),
            voice_tone=self.voice_tone.currentData(), space=self.space.currentData(),
            loudness=self.loudness.currentData(),
            intro=self.intro.currentData(), ending=self.ending.currentData(),
            swaps={k: cb.currentData() for k, cb in self.swaps.items() if cb.currentData() != k} or None)
