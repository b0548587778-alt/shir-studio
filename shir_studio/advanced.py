"""חלון 'אפשרויות מתקדמות' - לאנשים טכנולוגיים ולמוזיקאים. המסך הרגיל נשאר פשוט."""
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
    return f"{v:+d} dB" if v else "רגיל"


class AdvancedDialog(QDialog):
    def __init__(self, parent, settings: Settings, info=None, extras=False, fmt="mp3", style=None, artist=""):
        super().__init__(parent)
        self.setWindowTitle("אפשרויות מתקדמות")
        self.setLayoutDirection(Qt.RightToLeft)
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
            t = f"זוהה אוטומטית: סולם {info['key']}"
            t += f" · קצב \u2066{info['tempo']} BPM\u2069" if info["steady"] else " · קצב חופשי"
            lab = QLabel(t)
            lab.setObjectName("small")
            v.addWidget(lab)

        # ---- קול
        g = QGroupBox("קול")
        f = QFormLayout(g)
        self.denoise = _slider(0, 100, settings.denoise, lambda x: f"{x}%")
        self.tune = _slider(0, 100, settings.tune, lambda x: "כבוי" if x == 0 else f"{x}%")
        self.voice_db = _slider(-9, 9, settings.voice_db, _db)
        self.transpose = QSpinBox()
        self.transpose.setRange(-7, 7)
        self.transpose.setValue(settings.transpose)
        self.transpose.setSuffix(" חצאי טונים")
        f.addRow("ניקוי רעשים:", self.denoise)
        f.addRow("תיקון זיופים:", self.tune)
        f.addRow("עוצמת הקול:", self.voice_db)
        f.addRow("העברת סולם (טרנספוזיציה):", self.transpose)
        voice = (info or {}).get("voice")
        if voice:
            sug = voice["suggest"]
            vw = QWidget()
            vh = QHBoxLayout(vw)
            vh.setContentsMargins(0, 0, 0, 0)
            txt = f"המנעד שלך בשיר: מ{voice['low']} עד {voice['high']}. "
            if sug:
                way = "העלאה" if sug > 0 else "הורדה"
                txt += f"מומלץ: {way} של \u2066{abs(sug)}\u2069 חצאי טונים, לגובה נוח יותר."
            else:
                txt += "השיר בגובה נוח."
            lab = QLabel(txt)
            lab.setObjectName("small")
            lab.setWordWrap(True)
            vh.addWidget(lab, 1)
            if sug:
                b = QPushButton("החל המלצה")
                b.clicked.connect(lambda: self.transpose.setValue(sug))
                vh.addWidget(b)
            f.addRow("", vw)
        self.harmony = QComboBox()
        for label, val in (("בלי", "off"), ("אוטומטי", "auto"), ("מעל המנגינה", "above"),
                           ("מתחת למנגינה", "below"), ("שלושה קולות (מעל ומתחת)", "three")):
            self.harmony.addItem(label, val)
        self.harmony.setCurrentIndex(max(0, self.harmony.findData(settings.harmony)))
        f.addRow("קול שני (הרמוניה):", self.harmony)
        self.choir = QCheckBox("מקהלה - הקול נשמע כמו כמה זמרים")
        self.choir.setChecked(bool(settings.choir))
        f.addRow("", self.choir)
        from .audio.polish import TONES
        self.voice_tone = QComboBox()
        for val, name in TONES.items():
            self.voice_tone.addItem(name, val)
        self.voice_tone.setCurrentIndex(max(0, self.voice_tone.findData(settings.voice_tone)))
        f.addRow("אופי הקול:", self.voice_tone)
        v.addWidget(g)

        # ---- מוזיקה
        g = QGroupBox("מוזיקה")
        f = QFormLayout(g)
        self.key = QComboBox()
        self.key.addItem("אוטומטי", None)
        for mode in MODES:
            for t in range(12):
                self.key.addItem(f"{NOTE_NAMES[t]} {MODES[mode][0]}", f"{t}:{mode}")
        if settings.key:
            i = self.key.findData(f"{settings.key[0]}:{settings.key[1]}")
            self.key.setCurrentIndex(max(0, i))
        f.addRow("סולם:", self.key)

        tw = QWidget()
        th = QHBoxLayout(tw)
        th.setContentsMargins(0, 0, 0, 0)
        self.t_auto = QRadioButton("אוטומטי")
        self.t_manual = QRadioButton("קבוע")
        self.t_free = QRadioButton("חופשי (בלי תופים)")
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
        f.addRow("קצב:", tw)

        self.meter = QComboBox()
        self.meter.addItem("אוטומטי (4/4, או ואלס כשהוא מזוהה)", 0)
        self.meter.addItem("4/4 (רגיל)", 4)
        self.meter.addItem("3/4 (ואלס)", 3)
        self.meter.addItem("6/8 (מתנדנד)", 6)
        cur = 0 if (settings.meter == 4 and settings.auto_meter) else settings.meter
        self.meter.setCurrentIndex(max(0, self.meter.findData(cur)))
        f.addRow("משקל:", self.meter)
        self.cpb = QComboBox()
        self.cpb.addItem("שניים בתיבה", 2)
        self.cpb.addItem("אחד בתיבה", 1)
        self.cpb.setCurrentIndex(0 if settings.chords_per_bar == 2 else 1)
        f.addRow("החלפת אקורדים:", self.cpb)
        self.accomp_db = _slider(-12, 9, settings.accomp_db, _db)
        self.reverb = _slider(0, 200, settings.reverb, lambda x: f"{x}%")
        f.addRow("עוצמת הליווי:", self.accomp_db)
        f.addRow("הדהוד (ריוורב):", self.reverb)
        from .audio.mix import SPACE_NAMES
        self.space = QComboBox()
        for val, name in SPACE_NAMES.items():
            self.space.addItem(name, val)
        self.space.setCurrentIndex(max(0, self.space.findData(settings.space)))
        f.addRow("גודל האולם:", self.space)
        self.modulate = QCheckBox("עליית סולם (חצי טון) בפזמון האחרון - הקול והליווי עולים יחד")
        self.modulate.setChecked(bool(settings.modulate))
        f.addRow("", self.modulate)
        v.addWidget(g)

        # ---- כלים
        self.swaps = {}
        if style:
            from .music.styles import instruments_of, SWAPPABLE
            insts = instruments_of(style)
            if insts:
                g = QGroupBox(f"כלי הנגינה בסגנון '{style.get('name', '')}'")
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
            g = QGroupBox("חלקי השיר - בית או פזמון")
            f = QFormLayout(g)
            h = QLabel("בבית הליווי רגוע, ובפזמון מלא וחזק. התוכנה מנחשת לבד - אפשר לשנות.")
            h.setObjectName("small")
            h.setWordWrap(True)
            f.addRow(h)
            cur = settings.sections or []
            for i, (s, e, lvl) in enumerate(phrases):
                cb = QComboBox()
                cb.addItem("בית (רגוע)", 0)
                cb.addItem("פזמון (מלא)", 1)
                cb.setCurrentIndex(int(cur[i]) if i < len(cur) else int(lvl))
                f.addRow(f"משפט {i + 1}  (\u2066{int(s) // 60}:{int(s) % 60:02d}\u2069):", cb)
                self.sec_boxes.append(cb)
                self.sec_auto.append(int(lvl))
            v.addWidget(g)

        # ---- אקורדים
        g = QGroupBox("אקורדים - למוזיקאים")
        gv = QVBoxLayout(g)
        hint = QLabel("כתוב תיבה אחרי תיבה, מופרדות בקו ישר. כמה אקורדים באותה תיבה - עם רווח ביניהם. "
                      "מקף = כמו האקורד הקודם. השאר ריק כדי שהתוכנה תבחר לבד. דוגמה:")
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
        b_fill = QPushButton("הכנס את האקורדים שזוהו לעריכה")
        b_fill.setEnabled(bool(info))
        b_fill.clicked.connect(lambda: self.chords.setPlainText(info["chords"]))
        b_clear = QPushButton("נקה (אוטומטי)")
        b_clear.clicked.connect(self.chords.clear)
        row.addWidget(b_fill); row.addWidget(b_clear); row.addStretch()
        gv.addLayout(row)
        v.addWidget(g)

        # ---- שמירה
        g = QGroupBox("שמירה")
        f = QFormLayout(g)
        self.fmt = QComboBox()
        self.fmt.addItem("MP3", "mp3")
        self.fmt.addItem("WAV (איכות מלאה)", "wav")
        self.fmt.addItem("FLAC (איכות מלאה, קובץ קטן יותר)", "flac")
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(fmt)))
        self.extras = QCheckBox("שמור גם קול וליווי בקבצים נפרדים + קובץ MIDI")
        self.extras.setChecked(extras)
        from .audio.loudness import NAMES as LOUD_NAMES
        self.loudness = QComboBox()
        for val, name in LOUD_NAMES.items():
            self.loudness.addItem(name, val)
        self.loudness.setCurrentIndex(max(0, self.loudness.findData(settings.loudness)))
        f.addRow("עוצמת השיר:", self.loudness)
        self.artist = QLineEdit(artist or "")
        self.artist.setPlaceholderText("נכתב בתוך קובץ ה-MP3 ומופיע בנגן")
        f.addRow("שם הזמר:", self.artist)
        f.addRow("סוג קובץ:", self.fmt)
        f.addRow("", self.extras)
        v.addWidget(g)

        # ---- כפתורים
        row = QHBoxLayout()
        ok = QPushButton("אישור")
        ok.setStyleSheet("background:#2c7a3f; color:white; font-weight:bold;")
        ok.clicked.connect(self.accept)
        reset = QPushButton("החזר הכול לרגיל")
        reset.clicked.connect(self.reset)
        mine = QPushButton("⭐  שמור כטעם שלי")
        mine.setToolTip("העוצמות, הניקוי, ההדהוד, הקול השני, הכלים וסוג הקובץ יהיו ברירת המחדל בכל שיר חדש")
        mine.clicked.connect(lambda: self.done(3))
        cancel = QPushButton("ביטול")
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
            modulate=self.modulate.isChecked(), note_edits=o.note_edits,
            meter=self.meter.currentData() or 4, auto_meter=self.meter.currentData() == 0, chords_per_bar=self.cpb.currentData(),
            chords_text=self.chords.toPlainText().strip(), transpose=self.transpose.value(),
            voice_db=self.voice_db.slider.value(), accomp_db=self.accomp_db.slider.value(),
            reverb=self.reverb.slider.value(), harmony=self.harmony.currentData(),
            choir=self.choir.isChecked(), sections=self._sections(),
            voice_tone=self.voice_tone.currentData(), space=self.space.currentData(),
            loudness=self.loudness.currentData(),
            swaps={k: cb.currentData() for k, cb in self.swaps.items() if cb.currentData() != k} or None)
