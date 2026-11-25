"""החלון הראשי: מחבר בין המסכים (בתיקייה screens) לבין העבודה עצמה. הכול בעברית, מימין לשמאל."""
from .i18n import tx
from .i18n import direction
import dataclasses
import os
import time
import traceback

import numpy as np
from PySide6.QtCore import Qt, QTimer, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QFileDialog, QWidget, QVBoxLayout

from . import APP_NAME, APP_VERSION, prefs as prefs_mod, recovery, update, shortcuts
from .audio import edit
from .audio.fileio import load, save, AudioError, SR
from .audio.devices import Recorder, Player, Metronome, Overdub, clipped_share
from .pipeline import Song, Settings
from .advanced import AdvancedDialog
from .music.styles import load_styles
from .log import log_error, log_dir
from .project import save_project, load_project, settings_to_dict, settings_from_dict, History, batch, EXT
from .pitchview import PitchDialog
from .trimview import TrimDialog, PunchDialog
from .medleyview import MedleyDialog
from .screens import common
from .screens.common import STYLE, Worker, fmt_time, StepBar
from . import license as lic
from .screens.home import HomeScreen
from .screens.record import RecordScreen, TITLE as REC_TITLE, TOO_LOUD, NOT_HEARD
from .screens.styles import StyleScreen
from .screens.work import WorkScreen
from .screens.done import DoneScreen

AUDIO_EXT = (".mp3", ".wav", ".flac", ".ogg", ".m4a")
AUDIO_FILTER = tx("קבצי שיר (*.mp3 *.wav *.flac *.ogg *.m4a)")
PRE_ROLL = 3.0            # שניות של ספירה לאחור / השמעה מקדימה לפני הקלטה
KEEP_RAWS = 6             # כמה גרסאות של ההקלטה נשמרות לביטול/חזרה


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setLayoutDirection(direction())
        self.setStyleSheet(STYLE)
        self.resize(1000, 760)
        self.setAcceptDrops(True)
        self.recorder = None
        self.backup = None
        self.rec_mode = "new"
        self.player = Player()
        self.playing = None           # "result" / "original" / None
        self.original = None
        self.result = None
        self.worker = None
        self._workers = []            # עבודות רקע שעוד רצות - נשמרות עד שהן מסתיימות
        self.song = None
        self.raws, self.raw_id = [], 0
        self.dirty = False            # יש שיר מוכן שעוד לא נשמר
        self._saved_raw = None
        self._pending_key = None
        self._record = True
        self.backing = None           # פלייבק ששרים עליו (אז הוא הליווי של השיר)
        self.lyrics = ""              # מילות השיר
        self._best_take = False       # שרים שוב כדי לבחור את המיטב משתי ההקלטות
        self._playback = None
        self.styles = load_styles()
        self.prefs = prefs_mod.load()
        self.settings = prefs_mod.personal_settings(self.prefs)
        self.save_extras = bool(self.prefs.get("extras", False))
        self.save_fmt = self.prefs.get("fmt") if self.prefs.get("fmt") in ("mp3", "wav", "flac") else "mp3"
        self.metronome = Metronome()
        self.history = History()

        self.home = HomeScreen()
        self.rec = RecordScreen()
        self.style_page = StyleScreen(self.styles)
        self.work = WorkScreen()
        self.done = DoneScreen()
        self.stack = QStackedWidget()
        self.steps = StepBar()                        # שלושת הצעדים: הקלטה, סגנון, שיר מוכן
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.steps)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(box)
        for w in (self.home, self.rec, self.style_page, self.work, self.done):
            self.stack.addWidget(w)
        self.stack.currentChanged.connect(self._show_step)
        self._connect()
        shortcuts.install(self)
        for i, st in enumerate(self.styles):
            if st["id"] == self.prefs.get("style"):
                self.style_page.set_current(i)
        self.style_page.set_harmony(self.settings.harmony != "off")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._update_pos)
        self.play_timer.start(200)
        QTimer.singleShot(400, self.offer_recovery)
        self.home.license.connect(self.enter_license)
        self.home.language.connect(self.choose_language)
        self._refresh_license()

    def _show_step(self, _index=None):
        w = self.stack.currentWidget()
        if w is self.done:
            self.steps.set_step(2)
        elif w is self.style_page or (w is self.work and self.song is not None):
            self.steps.set_step(1)
        elif w is not self.work:
            self.steps.set_step(0)

    def _connect(self):
        h, r, s, d = self.home, self.rec, self.style_page, self.done
        h.record.connect(self.start_recording)
        h.choose.connect(self.choose_file)
        h.open_project.connect(self.open_project)
        h.batch.connect(self.batch_process)
        h.medley.connect(self.medley)
        h.separate.connect(self.open_tools)
        h.check_update.connect(self.check_update)
        h.mic_check.connect(self.mic_check)
        h.shortcuts.connect(lambda: shortcuts.show_help(self))
        r.stop.connect(self.stop_recording)
        r.cancel.connect(self.cancel_recording)
        s.make.connect(self.make_song)
        s.back.connect(self.go_home)
        s.advanced.connect(lambda: self.open_advanced(remake=False))
        s.preview.connect(self.preview_style)
        s.trim.connect(self.trim)
        s.harmony.connect(lambda on: setattr(self.settings, "harmony", "auto" if on else "off"))
        d.play_result.connect(lambda: self.play_result())
        d.play_original.connect(lambda: self.play_original())
        d.compare.connect(self.compare)
        d.stop.connect(self.stop_playing)
        d.seek.connect(self._seek)
        d.other_style.connect(self.choose_style)
        d.other_key.connect(self.other_key)
        d.undo.connect(self.undo)
        d.redo.connect(self.redo)
        d.graph.connect(self.show_pitch)
        d.punch.connect(self.punch)
        d.overdub.connect(self.overdub)
        d.trim.connect(self.trim)
        d.save_project.connect(self.save_project)
        d.share.connect(self.share_file)
        d.chords.connect(self.chord_sheet)
        d.save.connect(self.save_result)
        d.new_song.connect(self.new_song)
        d.advanced.connect(lambda: self.open_advanced(remake=True))
        d.tempo.connect(self.scale_tempo)
        d.practice.connect(self.practice)
        d.lyrics.connect(self.edit_lyrics)
        d.best_take.connect(lambda: self.overdub(best=True))

    # ---------- הודעות (פונקציות נפרדות - כדי שהבדיקות יוכלו להחליף אותן) ----------
    def error(self, text):
        common.warn(self, text)

    def _info(self, title, text, button=tx("אישור")):
        common.info(self, title, text, button)

    def _ask(self, title, text, yes=tx("כן"), no=tx("לא")):
        return common.ask(self, title, text, yes, no)

    def style(self):
        return self.styles[self.style_page.current()]

    @staticmethod
    def _docs(*parts):
        return os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), tx("שיר סטודיו"), *parts)

    # ---------- מעבר בין מסכים ----------
    def go_home(self):
        self.stop_playing()
        self.stack.setCurrentWidget(self.home)

    def new_song(self):
        self.dirty = False
        recovery.clear()
        self._saved_raw = None
        self.go_home()

    def choose_style(self):
        if self.backing is not None and self.result is not None:
            self._info(tx("סגנון ליווי"), tx("בשיר הזה הליווי הוא הפלייבק שבחרת, ולכן אין סגנון להחליף."))
            return
        self.stop_playing()
        self.stack.setCurrentWidget(self.style_page)

    def _back_to_song(self):
        """חוזרים למסך שממנו באנו: 'השיר מוכן' אם כבר יש שיר, אחרת בחירת הסגנון."""
        self.stack.setCurrentWidget(self.done if self.result is not None else self.style_page)

    # ---------- הקלטה ----------
    def start_recording(self):
        self.recorder = Recorder()
        try:
            self.recorder.start()
            if self.home.metro_on.isChecked():
                m = self.settings.meter
                self.metronome.start(self.home.metro_bpm.value(), 2 if m == 6 else m)
        except AudioError as e:
            self.recorder.stop()
            self.metronome.stop()
            self.error(str(e))
            return
        self.backup = recovery.RecordingBackup()
        self._begin_recording("new", REC_TITLE, tx("מתכוננים..."), PRE_ROLL, 15 * 60)

    def _begin_recording(self, mode, title, wait_title, countdown, limit, pre=0.0):
        """ספירה לאחור (3-2-1, כדי שתחילת השיר לא תיחתך) ואז מסך ההקלטה."""
        self.rec_mode, self.rec_title, self.rec_limit, self.rec_pre = mode, title, limit, pre
        self.countdown_end = time.time() + countdown
        self.rec_start = None
        self._last_flush = 0.0
        self._clips, self._loud_until, self._heard = 0, 0.0, 0.0
        self.rec.set_warning(None)
        self.rec.set_lyrics(self.lyrics if mode in ("overdub", "punch") else "")
        self.rec.title.setText(wait_title)
        self.rec.time.setText(str(int(np.ceil(countdown))))
        self.stack.setCurrentWidget(self.rec)
        self.timer.start(100)

    def _tick(self):
        now = time.time()
        self.rec.set_level(self.recorder.level)
        if self.rec_start is None:
            left = self.countdown_end - now
            if left > 0:
                self.rec.time.setText(str(int(left) + 1))
                return
            self.recorder.reset()               # מתחילים את ההקלטה רק עכשיו
            self.rec_start = now
            self.rec.title.setText(self.rec_title)
        s = now - self.rec_start
        self.rec.time.setText(fmt_time(s))
        self._mic_warning(now, s)
        if self.backup and now - self._last_flush > 1.0:      # גיבוי שוטף - שהקלטה לא תאבד אם משהו נסגר
            self._last_flush = now
            self.backup.write(self.recorder.drain())
        if s >= self.rec_limit:
            self.stop_recording()

    def _mic_warning(self, now, elapsed):
        """בזמן ההקלטה: מזהירים מיד כשהקול נחתך (חזק מדי), או כשהמיקרופון לא שומע כלום."""
        r = self.recorder
        clips = getattr(r, "clips", 0)
        if clips > self._clips:
            self._clips, self._loud_until = clips, now + 2.5
        self._heard = max(self._heard, r.level)
        if now < self._loud_until:
            self.rec.set_warning(TOO_LOUD)
        elif self.rec_mode == "new" and elapsed > 5 and self._heard < 0.004:   # (מול ליווי יש מבוא שבו שותקים)
            self.rec.set_warning(NOT_HEARD)
        else:
            self.rec.set_warning(None)

    def mic_check(self):
        from .micview import MicDialog
        self.stop_playing()
        MicDialog(self).exec()

    def _end_backup(self):
        if self.backup:
            self.backup.discard()
            self.backup = None

    def cancel_recording(self):
        self.timer.stop()
        self.metronome.stop()
        if self.recorder:
            self.recorder.stop()
        self._end_backup()
        if self.rec_mode in ("new", "playback"):
            self.go_home()
        else:
            self._back_to_song()

    def stop_recording(self):
        self.timer.stop()
        self.metronome.stop()
        mode = self.rec_mode
        if self.rec_start is None:          # לחצו 'סיום' עוד בזמן הספירה
            self.cancel_recording()
            return
        data = self.recorder.stop()
        if mode == "punch":
            self._finish_punch(data[int(self.rec_pre * SR):])
            return
        if mode in ("overdub", "playback"):
            data = data[int(self.rec_pre * SR):]
        if len(data) < SR * 2:
            self._end_backup()
            self.error(tx("ההקלטה קצרה מדי.\nלחץ 'הקלט שיר' ושיר לפחות כמה שניות."))
            self.cancel_recording()
            return
        if np.max(np.abs(data)) < 0.003:
            self._end_backup()
            self.error(tx("לא שמעתי קול בהקלטה.\nבדוק שהמיקרופון מחובר ודבר קרוב אליו."))
            self.cancel_recording()
            return
        self._keep_recording(data)
        self._end_backup()
        if mode == "new" and clipped_share(data) > 0.002 and not self._ask(
                tx("ההקלטה חזקה מדי"), tx("בחלק מההקלטה הקול היה חזק מדי ונחתך, ולכן הוא עלול להישמע צרוד.\n"
                "מומלץ להקליט שוב, קצת יותר רחוק מהמיקרופון.\n(ההקלטה הזו נשמרה בתיקיית 'הקלטות'.)"),
                tx("המשך עם ההקלטה הזו"), tx("הקלט שוב")):
            self.start_recording()
            return
        if mode == "overdub":
            self._finish_overdub(data)
            return
        if mode == "playback":
            self.process(np.ascontiguousarray(data, dtype=np.float32), backing=self._playback)
            self._playback = None
            return
        self.process(data)
        if self.home.metro_on.isChecked():                 # שרו עם מטרונום - הקצב ידוע
            self.settings.tempo_mode, self.settings.bpm = "manual", float(self.home.metro_bpm.value())

    def _keep_recording(self, data):
        """שומר עותק של ההקלטה המקורית בתיקייה 'מסמכים\\שיר סטודיו\\הקלטות'."""
        try:
            d = self._docs(tx("הקלטות"))
            os.makedirs(d, exist_ok=True)
            save(os.path.join(d, time.strftime(tx("הקלטה %Y-%m-%d %H-%M-%S.mp3"))), data)
        except Exception:
            log_error(traceback.format_exc())

    # ---------- פתיחת קבצים (כפתור או גרירה) ----------
    def choose_file(self):
        start = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
        path, _ = QFileDialog.getOpenFileName(self, tx("בחר שיר"), start, AUDIO_FILTER + tx(";;כל הקבצים (*.*)"))
        if path:
            self.open_audio(path)

    def open_audio(self, path):
        try:
            data = load(path)
        except AudioError as e:
            self.error(str(e))
            return
        self.process(data)

    def dragEnterEvent(self, ev):
        ok = self.stack.currentWidget() in (self.home, self.style_page, self.done)
        if ok and any(u.isLocalFile() for u in ev.mimeData().urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        self.open_paths([u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()])

    def open_paths(self, paths):
        """קבצים שנגררו לחלון: פרויקט נפתח, שיר אחד מעובד, כמה שירים - ברצף."""
        proj = [p for p in paths if p.lower().endswith(EXT)]
        audio = [p for p in paths if p.lower().endswith(AUDIO_EXT)]
        if proj:
            self.open_project(proj[0])
        elif len(audio) == 1:
            self.open_audio(audio[0])
        elif audio:
            self.batch_process(audio)
        elif paths:
            self.error(tx("זה לא קובץ שיר.\nאפשר לגרור קובץ שנגמר ב-mp3 או wav, או פרויקט של שיר סטודיו."))

    # ---------- ההקלטה שעובדים עליה ----------
    def _set_raw(self, data, grid=None):
        self.raws.append((data, grid))
        for i in range(len(self.raws) - KEEP_RAWS):        # גרסאות ישנות מאוד משוחררות מהזיכרון
            self.raws[i] = None
        self.raw_id = len(self.raws) - 1
        self.original = data
        self.song = Song(data, grid=grid)
        self.song.backing = self.backing
        self._orig_play = None

    def process(self, data, backing=None):
        """שיר חדש. backing: פלייבק ששרו עליו - הוא יהיה הליווי, בלי בחירת סגנון."""
        self.backing = backing
        self.raws = []
        self._set_raw(data)
        self.result = None
        st = self.settings
        st.key, st.chords_text, st.sections, st.note_edits = None, "", None, None
        self._load_lyrics("")
        if st.tempo_mode == "manual" and not self.home.metro_on.isChecked():
            st.tempo_mode = "auto"
        self.history = History()
        if backing is not None:
            self.make_song()
        else:
            self.choose_style()

    def _grid(self):
        a = self.song.analysis if self.song else None
        return (a.auto["beats"], a.auto["tempo"], a.auto["steady"]) if a is not None else None

    def _pin_key(self):
        """ההקלטה משתנה אבל השיר אותו שיר - הסולם שכבר נבחר נשאר."""
        a = self.song.analysis if self.song else None
        if a is not None and self.settings.key is None:
            self.settings = dataclasses.replace(self.settings, key=(int(a.tonic), str(a.mode)))

    # ---------- חיתוך ----------
    def trim(self):
        if self.original is None:
            return
        if self.backing is not None:
            self.error(tx("אי אפשר לחתוך שיר שהוקלט על פלייבק - השירה צריכה להישאר במקומה מול הנגינה."))
            return
        self.stop_playing()
        dlg = TrimDialog(self, self.original, play=self._play, stop=self.stop_playing)
        if not dlg.exec() or not dlg.selection():
            return
        try:
            new = edit.cut(self.original, *dlg.selection())
        except AudioError as e:
            self.error(str(e))
            return
        self.apply_trim(new)

    def apply_trim(self, new):
        had_song = self.result is not None and self.stack.currentWidget() is self.done
        self._set_raw(new)
        # הזמנים זזו - מה שנקבע לפי זמן (אקורדים, בית/פזמון, תיקונים ידניים) כבר לא מתאים
        self.settings = dataclasses.replace(self.settings, chords_text="", sections=None, note_edits=None)
        if had_song:
            self.make_song()

    # ---------- הקלטה מחדש של משפט אחד ----------
    def punch(self):
        if self.original is None:
            return
        self.stop_playing()
        dlg = PunchDialog(self, self.original, play=self._play, stop=self.stop_playing)
        if not dlg.exec() or not dlg.slot():
            return
        self.start_punch(dlg.slot())

    def start_punch(self, slot):
        _, _, lo, hi = slot
        self.punch_slot = (lo, hi)
        # לפני המשפט משמיעים את 3 השניות שקודמות לו - כדי להיכנס בקצב ובסולם
        a = int(lo * SR)
        seg = self.original[max(0, a - int(PRE_ROLL * SR)):a]
        backing = np.zeros(int(PRE_ROLL * SR), dtype=np.float32)
        if len(seg):
            backing[-len(seg):] = seg * (0.6 / max(float(np.max(np.abs(self.original))), 1e-6))
        pre = PRE_ROLL
        self.recorder = Overdub(backing)
        try:
            self.recorder.start()
        except AudioError:
            # אין אפשרות להשמיע ולהקליט יחד במחשב הזה - מקליטים בלי ההשמעה המקדימה
            self.recorder, pre = Recorder(), 0.0
            try:
                self.recorder.start()
            except AudioError as e:
                self.recorder.stop()
                self.error(str(e))
                return
        self._begin_recording("punch", tx("שיר עכשיו את המשפט"), tx("הקשב... ואז שיר"), PRE_ROLL, hi - lo + 1.5, pre)

    def _finish_punch(self, take):
        lo, hi = self.punch_slot
        try:
            new = edit.splice_take(self.original, lo, hi, take)
        except AudioError as e:
            self.error(str(e))
            self._back_to_song()
            return
        self.replace_phrase(new)

    def replace_phrase(self, new):
        grid = self._grid()
        self._pin_key()
        self._set_raw(new, grid)
        self.make_song()

    # ---------- שירה מחדש על הליווי המוכן ----------
    def overdub(self, best=False):
        """best: אחרי ההקלטה התוכנה בוחרת לכל משפט את הביצוע הנקי יותר - מההקלטה הקודמת או מהחדשה."""
        if self.song is None or self.result is None:
            return
        if best:
            ok = self._ask(tx("שיר שוב - ובחר את המיטב"),
                           tx("תשמע את הליווי המוכן ותשיר איתו את כל השיר שוב.\n"
                           "אחר כך התוכנה תשווה משפט אחרי משפט, ותיקח מכל הקלטה את המשפטים שיצאו נקיים יותר.\n"
                           "אפשר לחזור על זה כמה פעמים - בכל פעם נשמר הטוב ביותר.\n\n"
                           "חשוב: שים אוזניות, כדי שהליווי לא ייכנס למיקרופון."),
                           tx("יש לי אוזניות - מתחילים"), tx("ביטול"))
        else:
            ok = self._ask(tx("שיר שוב עם הליווי"),
                           tx("תשמע את הליווי המוכן ותשיר איתו את כל השיר מחדש.\n"
                           "השירה יוצאת מדויקת יותר בקצב, והשיר נשמע נקי יותר.\n\n"
                           "חשוב: שים אוזניות, כדי שהליווי לא ייכנס למיקרופון."),
                           tx("יש לי אוזניות - מתחילים"), tx("ביטול"))
        if not ok:
            return
        self._best_take = bool(best)
        self.stop_playing()
        self.work.begin(tx("מכין את הליווי..."))
        self.stack.setCurrentWidget(self.work)
        song = self.song
        self._run(lambda p: song.stems_in_sung_key(p), self._start_overdub, back=self._back_to_song)

    def _start_overdub(self, stems):
        acc = stems.get(tx("ליווי"))
        self.song.last_stems = None                       # מפנים זיכרון
        if acc is None:
            self.error(tx("לא הצלחתי להכין את הליווי."))
            self._back_to_song()
            return
        self.overdub_lead = float(self.song.last_lead)
        backing = np.concatenate([np.zeros((int(PRE_ROLL * SR), 2), dtype=np.float32), acc])
        self.recorder = Overdub(backing)
        try:
            self.recorder.start()
        except AudioError as e:
            self.error(str(e))
            self._back_to_song()
            return
        self._begin_recording("overdub", tx("שיר עם הליווי"), tx("מתכוננים..."), PRE_ROLL, len(acc) / SR, PRE_ROLL)

    def _finish_overdub(self, rec):
        """rec מתחיל בתחילת הליווי. הקול בשיר מתחיל 'lead' שניות אחר כך - כמו בהקלטה המקורית."""
        voice = rec[int(self.overdub_lead * SR):]
        if len(voice) < 2 * SR or np.max(np.abs(voice)) < 0.003:
            self.error(tx("לא שמעתי שירה בהקלטה.\nנסה שוב."))
            self._back_to_song()
            return
        if self._best_take:
            self._choose_best(np.ascontiguousarray(voice, dtype=np.float32))
            return
        grid = self._grid()
        self._pin_key()
        self._set_raw(np.ascontiguousarray(voice, dtype=np.float32), grid)
        self.settings = dataclasses.replace(self.settings, chords_text="", sections=None, note_edits=None)
        self.make_song()

    def _choose_best(self, take):
        """משווה את ההקלטה החדשה לקודמת, משפט אחרי משפט, ומשלב את הטובים משתיהן."""
        from .audio import takes
        from .music import theory
        old, a = self.original, self.song.analysis
        scale = theory.scale_pcs(a.tonic, a.mode) if a is not None else None
        f0 = a.f0 if a is not None else None
        self.work.begin(tx("משווה בין ההקלטות..."))
        self.stack.setCurrentWidget(self.work)
        self._run(lambda p: takes.best_of(old, take, scale, f0, p), self._best_chosen, back=self._back_to_song,
                  fail_text=tx("לא הצלחתי לשלב בין ההקלטות.\nהשיר נשאר כמו שהיה."))

    def _best_chosen(self, res):
        from .audio import takes
        mixed, picks = res
        new, kept = takes.summary(picks)
        if new == 0:
            self._back_to_song()
            self._info(tx("בחירת המיטב"), tx("בכל המשפטים ההקלטה הקודמת יצאה נקייה יותר (או שווה),\nולכן השיר נשאר כמו שהיה."))
            return
        self._info(tx("בחירת המיטב"), tx("מההקלטה החדשה נלקחו {0} משפטים, ומהקודמת נשארו {1}.\nלא מרוצה? 'ביטול שינוי' מחזיר את ההקלטה הקודמת.").format(new, kept))
        grid = self._grid()
        self._pin_key()
        self._set_raw(mixed, grid)
        self.settings = dataclasses.replace(self.settings, note_edits=None)   # המשפטים אותם משפטים - האקורדים נשארים
        self.make_song()

    # ---------- מצב תרגול ומילות השיר ----------
    def practice(self):
        if not (self.song and self.song.analysis is not None and self.original is not None):
            return
        from .practiceview import PracticeDialog
        self.stop_playing()
        tuned = self.song.tuned if self.song.tuned is not None and len(self.song.tuned) == len(self.original) else None
        dlg = PracticeDialog(self, self.original, self.song.analysis, tuned, play=self._play, stop=self.stop_playing)
        if dlg.exec() and dlg.punch:
            self.start_punch(dlg.punch)

    def edit_lyrics(self):
        from .lyricsview import LyricsDialog
        dlg = LyricsDialog(self, self.lyrics)
        if dlg.exec():
            self.set_lyrics(dlg.text())

    def _load_lyrics(self, text):
        """המילים של השיר שנפתח עכשיו (שיר חדש = בלי מילים)."""
        self.lyrics = text
        self.done.b_lyrics.setText(tx("📝  מילים ✔") if text else tx("📝  מילים"))

    def set_lyrics(self, text):
        if text == self.lyrics:
            return
        self._load_lyrics(text)
        self.dirty = self.dirty or self.result is not None
        if self.song is not None and self.result is not None:            # שהמילים לא יאבדו אם התוכנה נסגרת
            try:
                recovery.save_session(self.song.raw, self._session_meta(), False)
            except Exception:
                log_error(traceback.format_exc())

    def _session_meta(self):
        a = self.song.analysis if self.song else None
        return {"settings": settings_to_dict(self.settings), "style": self.style()["id"],
                "key_index": a.key_index if a is not None else 0, "lyrics": self.lyrics}

    # ---------- הכנת השיר ----------
    def _run(self, fn, done, back=None, fail_text=None):
        """מריץ עבודה ארוכה ברקע, עם מסך ההמתנה."""
        self.worker = self._keep(Worker(fn, fail_text) if fail_text else Worker(fn))
        self.worker.progress.connect(self.work.set_progress)
        self.worker.message.connect(self.work.title.setText)
        self.worker.finished_ok.connect(done)
        self.worker.failed.connect(lambda m: (self.error(m), (back or self.go_home)()))
        self.worker.start()

    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        return worker

    def open_advanced(self, remake):
        info = self.song.info() if (self.song and self.song.analysis) else None
        dlg = AdvancedDialog(self, self.settings, info, self.save_extras, self.save_fmt, style=self.style(),
                             artist=self.prefs.get("artist", ""))
        r = dlg.exec()
        if r in (1, 3):
            artist = dlg.artist.text().strip()
            if artist != self.prefs.get("artist", ""):
                self.prefs = dict(self.prefs, artist=artist)
                prefs_mod.save(self.prefs)
            self.settings = dlg.settings()
            self.save_extras = dlg.extras.isChecked()
            self.save_fmt = dlg.fmt.currentData()
            if r == 3:                                   # 'שמור כטעם שלי' - ברירת המחדל לכל שיר חדש
                self.prefs = prefs_mod.store_personal(self.prefs, self.settings, self.style()["id"],
                                                      self.save_fmt, self.save_extras)
                self._info(tx("נשמר"), tx("ההגדרות נשמרו כטעם שלך.\nמעכשיו כל שיר חדש יתחיל איתן."))
        elif r == 2:
            self.settings, self.save_extras, self.save_fmt = Settings(), False, "mp3"
        else:
            return
        self.style_page.set_harmony(self.settings.harmony != "off")
        if remake and self.song:
            self.make_song()

    def scale_tempo(self, factor):
        """ליווי מהיר או איטי פי שניים - כשהקצב זוהה בחצי או בכפול ממה שהזמר מרגיש."""
        a = self.song.analysis if self.song else None
        if a is None:
            return
        if not a.steady:
            self.error(tx("השיר מושר בקצב חופשי, ואין בו קצב קבוע לשנות."))
            return
        st = self.settings
        if not 50 <= a.tempo * factor <= 230:
            self.error(tx("הליווי כבר מהיר מאוד.") if factor > 1 else tx("הליווי כבר איטי מאוד."))
            return
        if st.tempo_mode == "manual" and st.bpm:
            self.settings = dataclasses.replace(st, bpm=st.bpm * factor)
        else:
            self.settings = dataclasses.replace(st, tempo_scale=st.tempo_scale * factor)
        self.make_song()

    def other_key(self):
        self.make_song(change_key=True)

    def make_song(self, change_key=False, record=True):
        self._record = record
        st = self.style()
        self.stop_playing()
        self.work.begin()
        self.stack.setCurrentWidget(self.work)
        song = self.song
        settings = self.settings
        if change_key:
            settings.key = None          # 'התאמה אחרת' עוקפת סולם שנקבע ידנית
            settings.chords_text = ""
        pending, self._pending_key = self._pending_key, None
        raw_changed = self._saved_raw is not song.raw
        lyrics = self.lyrics

        def job(p):
            if pending is not None:
                song.prepare(p, settings)
                from .music.analysis import apply_settings, set_key
                apply_settings(song.analysis, settings)
                set_key(song.analysis, pending)
            if change_key:
                p(5, tx("מחפש התאמה אחרת..."))
                song.next_key()
            out = song.make(st, p, settings)
            # גיבוי אוטומטי של העבודה - אם המחשב נכבה לפני ששמרו, אפשר לשחזר
            recovery.save_session(song.raw, {"settings": settings_to_dict(settings), "style": st["id"],
                                             "key_index": song.analysis.key_index, "lyrics": lyrics}, raw_changed)
            return out
        self._run(job, lambda r: self._processed(r, st, song))

    def _processed(self, result, st, song=None):
        self.result = result
        self.dirty = True
        self._saved_raw = (song or self.song).raw
        if self._record:
            self.history.push(self._state())
        self._update_undo()
        self.work.bar.setValue(100)
        hint = tx("סגנון: {0}").format(st['name'])
        info = self.song.info()
        if self.backing is not None:
            hint = tx("ליווי: הפלייבק שבחרת")
        elif not info["steady"]:
            hint += tx("\nהשיר מושר בקצב חופשי, לכן הליווי רך ובלי תופים.")
        elif getattr(self.song.analysis, "auto_waltz", False):
            hint += tx("\nהשיר זוהה כוואלס (3/4). לא מתאים? אפשר לשנות את המשקל ב'מתקדם'.")
        elif self.settings.modulate and self.song.analysis.modulate_at is None:
            hint += tx("\nהשיר קצר מדי לעליית סולם.")
        self.done.hint.setText(hint)
        self.stack.setCurrentWidget(self.done)

    def preview_style(self):
        if not self.song:
            return
        st = self.style()
        self.stop_playing()
        self.style_page.set_preview_busy(True)
        song, settings = self.song, self.settings
        self.prev_worker = self._keep(Worker(lambda p: song.preview(st, p, settings)))

        def done(res):
            self.style_page.set_preview_busy(False)
            self._play(res)

        def fail(m):
            self.style_page.set_preview_busy(False)
            self.error(m)
        self.prev_worker.finished_ok.connect(done)
        self.prev_worker.failed.connect(fail)
        self.prev_worker.start()

    # ---------- ביטול / חזרה ----------
    def _state(self):
        return {"settings": settings_to_dict(self.settings), "style": self.style_page.current(),
                "raw": self.raw_id,
                "key_index": self.song.analysis.key_index if self.song and self.song.analysis else 0}

    def _restore(self, state):
        if not state:
            return
        rid = state.get("raw", self.raw_id)
        if rid != self.raw_id:                           # השינוי היה בהקלטה עצמה (חיתוך, משפט חדש)
            if not (0 <= rid < len(self.raws)) or self.raws[rid] is None:
                self.error(tx("אי אפשר לחזור כל כך הרבה צעדים אחורה."))
                return
            data, grid = self.raws[rid]
            self.raw_id, self.original, self._orig_play = rid, data, None
            self.song = Song(data, grid=grid)
            self.song.backing = self.backing
            self._pending_key = state.get("key_index", 0)
        self.settings = settings_from_dict(state["settings"])
        self.style_page.set_current(state["style"])
        self.style_page.set_harmony(self.settings.harmony != "off")
        if self.song and self.song.analysis:
            from .music.analysis import set_key
            set_key(self.song.analysis, state.get("key_index", 0))
        self.make_song(record=False)

    def undo(self):
        self._restore(self.history.undo())

    def redo(self):
        self._restore(self.history.redo())

    def _update_undo(self):
        self.done.b_undo.setEnabled(self.history.can_undo())
        self.done.b_redo.setEnabled(self.history.can_redo())

    # ---------- גרף ותיקון ידני ----------
    def show_pitch(self):
        if not (self.song and self.song.analysis is not None):
            return
        dlg = PitchDialog(self, self.song.pitch_curves(self.settings), self.settings.note_edits)
        if dlg.exec() and dlg.changed():
            self.apply_note_edits(dlg.edits())

    def apply_note_edits(self, edits):
        self.settings = dataclasses.replace(self.settings, note_edits=dict(edits) or None)
        self.make_song()

    # ---------- השמעה והשוואה ----------
    def _play(self, data, start=0.0, what=None):
        try:
            self.player.play(data, start)
            self.playing = what
        except AudioError as e:
            self.playing = None
            self.error(str(e))

    def stop_playing(self):
        self.playing = None
        self.player.stop()

    def play_result(self, start=0.0):
        if self.result is not None:
            self._play(self.result, start, "result")

    def play_original(self, start=0.0):
        if self.original is None:
            return
        if self._orig_play is None:            # ההקלטה המקורית חלשה - מגבירים אותה להשמעה, כדי שההשוואה תהיה הוגנת
            self._orig_play = self.original * np.float32(0.7 / max(float(np.max(np.abs(self.original))), 1e-6))
        self._play(self._orig_play, start, "original")

    def compare(self):
        """לפני / אחרי: מחליף בין המקור לשיר המוכן, וממשיך מאותו מקום בשיר."""
        pos = self.player.position()
        lead = float(self.song.last_lead) if self.song else 0.0
        if pos is not None and self.playing == "result":
            start = pos - lead
            self.play_original(start if 0 <= start < len(self.original) / SR - 0.2 else 0.0)
        elif pos is not None and self.playing == "original":
            self.play_result(pos + lead)
        else:
            self.play_result()

    def _update_pos(self):
        if self.stack.currentWidget() is not self.done:
            return
        p = self.player.position()
        if p is None:
            self.playing = None
        total = self.player.length() or (len(self.result) / SR if self.result is not None else 0)
        what = {"result": tx("השיר המוכן"), "original": tx("ההקלטה המקורית")}.get(self.playing, "")
        self.done.show_position(p, total, what)

    def _seek(self, frac):
        data = self.player.data if self.player.data is not None else self.result
        if data is None:
            return
        self._play(data, frac * len(data) / SR, self.playing or "result")

    # ---------- שמירה ----------
    def share_file(self):
        """קובץ קטן לשליחה בוואטסאפ או במייל (MP3 128, בערך 1MB לדקה)."""
        if self.result is None or not self._may_save():
            return
        d = self._docs(tx("לשליחה"))
        try:
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, time.strftime(tx("השיר שלי %Y-%m-%d %H-%M.mp3")))
            save(path, self.result, bitrate=128, tags=self._tags(path))
        except Exception:
            log_error(traceback.format_exc())
            self.error(tx("לא הצלחתי ליצור את הקובץ לשליחה."))
            return
        mb = os.path.getsize(path) / 1024 / 1024
        if not getattr(self, "_counted", None) is self.song:
            self._counted = self.song
            self._count_saved()
        self._reveal(path)
        self._info(tx("קובץ לשליחה"), tx("נוצר קובץ קטן ({0:.1f}MB) שמתאים לוואטסאפ ולמייל:\n\n{1}\n\nבוואטסאפ: לחצו על 📎 ← מסמך, ובחרו את הקובץ.").format(mb, path))

    def _tags(self, path):
        """פרטי השיר שנכתבים בתוך הקובץ: שם השיר (שם הקובץ) ושם הזמר."""
        return {"title": os.path.splitext(os.path.basename(path))[0], "artist": self.prefs.get("artist", ""),
                "year": time.strftime("%Y"), "software": f"{APP_NAME} {APP_VERSION}", "lyrics": self.lyrics}

    @staticmethod
    def _reveal(path):
        """פותח את התיקייה עם הקובץ מסומן (בווינדוס)."""
        try:
            if os.name == "nt":
                import subprocess
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception:
            pass

    def chord_sheet(self):
        """דף אקורדים להדפסה (PDF)."""
        if not (self.song and self.song.analysis is not None):
            return
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), tx("השיר שלי - אקורדים.pdf"))
        path, _ = QFileDialog.getSaveFileName(self, tx("שמור דף אקורדים"), start, tx("קובץ PDF (*.pdf)"))
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        from . import chordsheet
        try:
            title = os.path.splitext(os.path.basename(path))[0]
            chordsheet.write_pdf(path, chordsheet.sheet_data(self.song, title, self.lyrics))
        except Exception:
            log_error(traceback.format_exc())
            self.error(tx("לא הצלחתי לשמור את דף האקורדים.\nבחר מקום אחר ונסה שוב."))
            return
        self._reveal(path)
        self._info(tx("נשמר"), tx("דף האקורדים נשמר:\n{0}\n\nאפשר לפתוח אותו ולהדפיס.").format(path))

    def save_project(self):
        if self.original is None:
            return
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), tx("השיר שלי{0}").format(EXT))
        path, _ = QFileDialog.getSaveFileName(self, tx("שמור פרויקט"), start, tx("פרויקט שיר סטודיו (*{0})").format(EXT))
        if not path:
            return
        if not path.lower().endswith(EXT):
            path += EXT
        try:
            save_project(path, self.original, self.settings, self.style()["id"],
                         {"key_index": self.song.analysis.key_index if self.song.analysis else 0, "lyrics": self.lyrics})
        except Exception:
            log_error(traceback.format_exc())
            self.error(tx("לא הצלחתי לשמור את הפרויקט.\nבדוק שיש מקום בדיסק ונסה שוב."))
            return
        self.dirty = False
        self._info(tx("נשמר"), tx("הפרויקט נשמר:\n{0}\n\nאפשר לפתוח אותו בהמשך ממסך הפתיחה.").format(path))

    def open_project(self, path=None):
        if not path:
            start = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            path, _ = QFileDialog.getOpenFileName(self, tx("פתח פרויקט"), start, tx("פרויקט שיר סטודיו (*{0})").format(EXT))
        if not path:
            return
        try:
            raw, settings, style_id, meta = load_project(path)
        except Exception:
            log_error(traceback.format_exc())
            self.error(tx("לא הצלחתי לפתוח את הפרויקט.\nייתכן שהקובץ פגום."))
            return
        self._open_loaded(raw, settings, style_id, meta)

    def _open_loaded(self, raw, settings, style_id, meta):
        self.backing = None
        self.raws = []
        self._set_raw(raw)
        self.result = None
        self.history = History()
        self.settings = settings
        self._load_lyrics(str(meta.get("lyrics") or ""))
        for i, st in enumerate(self.styles):
            if st["id"] == style_id:
                self.style_page.set_current(i)
        self.style_page.set_harmony(settings.harmony != "off")
        self._pending_key = meta.get("key_index", 0)
        self.make_song()

    # ---------- גרסת ניסיון ורישיון ----------
    def _refresh_license(self):
        self.home.show_license(lic.status())

    def _may_save(self):
        """מותר לשמור? בגרסת ניסיון שנגמרה - מסבירים ומציעים להזין קוד."""
        if lic.can_save():
            return True
        if self._ask(tx("גרסת הניסיון הסתיימה"),
                     tx("שמרת כבר {0} שירים בגרסת הניסיון.\nכדי להמשיך לשמור שירים צריך קוד רישיון.\n\nיש לך קוד?").format(lic.TRIAL_SONGS), tx("כן, להזין קוד"), tx("לא עכשיו")):
            self.enter_license()
        return lic.can_save()

    def _count_saved(self, n=1):
        lic.count_song(n)
        self._refresh_license()

    def choose_language(self):
        from .langview import LanguageDialog
        from . import i18n
        dlg = LanguageDialog(self, i18n.language())
        if dlg.exec() and dlg.code != i18n.language():
            i18n.save_language(dlg.code)
            self._info(tx("שפה"), tx("השפה תתחלף בפעם הבאה שתפתח את התוכנה.\nסגור את התוכנה ופתח אותה מחדש."))

    def enter_license(self):
        from .licenseview import LicenseDialog
        LicenseDialog(self).exec()
        self._refresh_license()

    def save_result(self):
        if not self._may_save():
            return
        ext = self.save_fmt
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.MusicLocation), tx("השיר שלי.{0}").format(ext))
        flt = {"mp3": tx("קובץ MP3 (*.mp3)"), "flac": tx("קובץ FLAC (*.flac)")}.get(ext, tx("קובץ WAV (*.wav)"))
        path, _ = QFileDialog.getSaveFileName(self, tx("שמור את השיר"), start, flt)
        if not path:
            return
        if not path.lower().endswith("." + ext):
            path += "." + ext
        extra = []
        try:
            save(path, self.result, tags=self._tags(path))
            if self.save_extras:
                folder = os.path.dirname(path)
                base = os.path.splitext(os.path.basename(path))[0]
                extra = self.song.export_extras(folder, base)
        except AudioError as e:
            self.error(str(e))
            return
        self.dirty = False
        if not getattr(self, "_counted", None) is self.song:      # כל שיר נספר פעם אחת, גם אם נשמר שוב
            self._counted = self.song
            self._count_saved()
        msg = tx("השיר נשמר בהצלחה!\n\n{0}").format(path)
        if extra:
            msg += tx("\n\nנשמרו גם:\n") + "\n".join(os.path.basename(p) for p in extra)
        self._info(tx("נשמר"), msg, tx("מעולה"))

    # ---------- כמה שירים ברצף, ומחרוזת ----------
    def batch_process(self, paths=None):
        if not self._may_save():
            return
        if not paths:
            start = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
            paths, _ = QFileDialog.getOpenFileNames(self, tx("בחר כמה שירים"), start, AUDIO_FILTER)
        if not paths:
            return
        folder = QFileDialog.getExistingDirectory(self, tx("לאן לשמור את השירים המוכנים?"), os.path.dirname(paths[0]))
        if not folder:
            return
        st = self.style()
        settings, fmt = self.settings, self.save_fmt
        self.work.begin(tx("מעבד את השירים..."))
        self.stack.setCurrentWidget(self.work)
        self._run(lambda p: batch(paths, st, settings, folder, fmt, progress=p,
                                          artist=self.prefs.get("artist", "")), self._batch_done)

    def _batch_done(self, results):
        ok = [r for r in results if r[1]]
        bad = [r for r in results if not r[1]]
        if ok:
            self._count_saved(len(ok))
        msg = tx("הוכנו {0} שירים (סגנון: {1}).").format(len(ok), self.style()['name'])
        if ok:
            msg += tx("\nנשמרו בתיקייה:\n{0}").format(os.path.dirname(ok[0][1]))
        if bad:
            msg += tx("\n\nלא הצלחתי להכין:\n") + "\n".join(os.path.basename(r[0]) for r in bad)
        self.go_home()
        self._info(tx("סיום"), msg)

    def medley(self):
        if not self._may_save():
            return
        st = self.style()
        dlg = MedleyDialog(self, st["name"])
        if not dlg.exec() or len(dlg.paths()) < 2:
            return
        ext = self.save_fmt
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.MusicLocation), tx("מחרוזת.{0}").format(ext))
        path, _ = QFileDialog.getSaveFileName(self, tx("שמור את המחרוזת"), start,
                                              {"mp3": tx("קובץ MP3 (*.mp3)"), "flac": tx("קובץ FLAC (*.flac)")}
                                              .get(ext, tx("קובץ WAV (*.wav)")))
        if not path:
            return
        if not path.lower().endswith("." + ext):
            path += "." + ext
        self.make_medley(dlg.paths(), path, dlg.process.isChecked(), dlg.cross.value())

    def make_medley(self, paths, path, process, crossfade):
        from .medley import make_medley
        st, settings = self.style(), self.settings
        self.work.begin(tx("מכין את המחרוזת..."))
        self.stack.setCurrentWidget(self.work)

        def done(res):
            seconds, bad = res
            msg = tx("המחרוזת מוכנה ({0} דקות):\n\n{1}").format(fmt_time(seconds), path)
            if bad:
                msg += tx("\n\nלא הצלחתי לפתוח:\n") + "\n".join(os.path.basename(p) for p in bad)
            self.go_home()
            self._count_saved()
            self._reveal(path)
            self._info(tx("מחרוזת"), msg, tx("מעולה"))
        self._run(lambda p: make_medley(paths, path, st, settings, process, crossfade, p), done,
                  fail_text=tx("לא הצלחתי להכין את המחרוזת.\nנסה שוב."))

    # ---------- גרסה חדשה ----------
    # ---------- הפרדת קול משיר מוכן ----------
    def open_tools(self):
        from .audio import separate as sep
        from .toolsview import ToolsDialog
        dlg = ToolsDialog(self, stems=sep.stems_available())
        if not dlg.exec() or not dlg.action:
            return
        kind = dlg.action[0]
        if kind == "separate":
            self.separate_voice(mode=dlg.action[1])
        elif kind == "shift":
            self.shift_playback(semitones=dlg.action[1], tempo=dlg.action[2])
        elif kind == "sing":
            self.sing_on_playback()

    def _pick_audio(self, title, many=False):
        start = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
        flt = AUDIO_FILTER + tx(";;כל הקבצים (*.*)")
        if many:
            return QFileDialog.getOpenFileNames(self, title, start, flt)[0]
        return QFileDialog.getOpenFileName(self, title, start, flt)[0]

    def separate_voice(self, path=None, mode="two"):
        """שיר מוכן (שירה + כלי נגינה) -> קבצים נפרדים. mode: two = שירה ונגינה, stems = גם תופים ובס,
        vocal = ממשיכים מיד לגרסה ווקאלית. path: קובץ אחד, או רשימת קבצים (ואז רק שומרים)."""
        from .audio import separate as sep
        from .audio.fileio import load_stereo
        ok = sep.stems_available() if mode == "stems" else sep.available()
        if not ok:
            self.error(tx("הפרדת הקול לא זמינה בהתקנה הזו.\nהתקן מחדש את התוכנה מקובץ ההתקנה העדכני."))
            return
        paths = [path] if isinstance(path, str) else list(path or [])
        if not paths:
            paths = self._pick_audio(tx("בחר שיר מוכן להפרדה (אפשר כמה)"), many=True)
        if not paths:
            return
        try:
            first = load_stereo(paths[0])                    # בודקים כבר עכשיו שהקובץ הראשון נפתח
        except AudioError as e:
            self.error(str(e))
            return
        self.work.begin(tx("מפריד את השירה מהנגינה...\n(כמה דקות לכל שיר - תלוי במחשב)"))
        self.stack.setCurrentWidget(self.work)
        folder, fmt, artist = self._docs(tx("הפרדת קול")), self.save_fmt, self.prefs.get("artist", "")
        limit = SR * 60 * 15

        def job(p):
            saved, failed, voice = [], [], None
            os.makedirs(folder, exist_ok=True)
            for i, src in enumerate(paths):
                name = os.path.basename(src)
                rep_ = lambda pct, m=None, i=i: p(2 + (i * 100 + pct) * 0.96 / len(paths), None)
                if len(paths) > 1:
                    p(2 + i * 96 / len(paths), tx("שיר {0} מתוך {1}: {2}").format(i + 1, len(paths), name))
                try:
                    mix = first if i == 0 else load_stereo(src)
                    if len(mix) > limit:
                        raise AudioError(tx("הקובץ ארוך מדי (עד 15 דקות)."))
                    if mode == "stems":
                        parts = sep.separate_stems(mix, progress=rep_)
                    else:
                        v, m = sep.separate(mix, progress=rep_)
                        parts = {tx("שירה"): v, tx("נגינה"): m}
                    base = os.path.splitext(name)[0]
                    for part, data in parts.items():
                        dst = os.path.join(folder, f"{base} - {part}.{fmt}")
                        save(dst, data, tags={"title": f"{base} - {part}", "artist": artist})
                        saved.append(dst)
                    if i == 0:
                        voice = parts[tx("שירה")]
                except AudioError as e:
                    failed.append((name, str(e).splitlines()[0]))
                except MemoryError:
                    raise
                except Exception:
                    log_error(traceback.format_exc())
                    failed.append((name, tx("ההפרדה לא הצליחה")))
            if not saved:
                raise AudioError(tx("ההפרדה לא הצליחה.\n") + "\n".join(f"{n}: {why}" for n, why in failed))
            p(100, None)
            return voice, saved, failed
        self._run(job, lambda res: self._separated(res, mode, len(paths)), back=self.go_home,
                  fail_text=tx("ההפרדה לא הצליחה.\nנסה קובץ אחר."))

    def _separated(self, res, mode="two", count=1):
        voice, paths, failed = res
        self.stack.setCurrentWidget(self.home)
        mono = voice.mean(axis=1).astype(np.float32) if voice is not None else None
        has_voice = mono is not None and np.max(np.abs(mono)) >= 1e-3
        if mode == "vocal" and count == 1:
            if not has_voice:
                self.error(tx("לא מצאתי שירה בשיר הזה."))
                return
            # גרסה ווקאלית: ממשיכים ישר עם השירה לסגנון 'ווקאלי - בלי כלים'
            self.process(mono)
            for i, st in enumerate(self.styles):
                if st.get("voices") or st["id"].endswith("vocal"):
                    self.style_page.set_current(i)
                    break
            self.make_song()
            return
        self._reveal(paths[0])
        text = tx("נשמרו {0} קבצים בתיקייה:\n{1}").format(len(paths), os.path.dirname(paths[0]))
        if count == 1:
            text = tx("נשמרו הקבצים:\n\n") + "\n".join(paths)
        if failed:
            text += tx("\n\nלא הצליחו:\n") + "\n".join(f"{n} - {why}" for n, why in failed)
        if count > 1 or not has_voice:
            self._info(tx("ההפרדה מוכנה"), text)
        elif self._ask(tx("ההפרדה מוכנה"), text + tx("\n\nלהמשיך עם השירה, ולהוסיף לה ליווי חדש?"),
                       tx("כן, ליווי חדש"), tx("לא, זה מספיק")):
            self.process(mono)

    # ---------- פלייבק: סולם וקצב, ושירה על פלייבק ----------
    def shift_playback(self, path=None, semitones=0, tempo=100):
        """שומר עותק של קובץ נגינה בסולם ובקצב אחרים."""
        from .audio import stretch
        from .audio.fileio import load_stereo
        if semitones == 0 and tempo == 100:
            self._info(tx("פלייבק"), tx("לא נבחר שינוי.\nבחר בכמה חצאי טונים להעלות או להוריד, או קצב אחר."))
            return
        path = path or self._pick_audio(tx("בחר קובץ נגינה (פלייבק)"))
        if not path:
            return
        try:
            audio = load_stereo(path)
        except AudioError as e:
            self.error(str(e))
            return
        self.work.begin(tx("משנה את הסולם והקצב של הפלייבק..."))
        self.stack.setCurrentWidget(self.work)
        base = os.path.splitext(os.path.basename(path))[0]
        note = []
        if semitones:
            note.append(tx("{0} חצאי טונים למעלה").format(abs(semitones)) if semitones > 0
                        else tx("{0} חצאי טונים למטה").format(abs(semitones)))
        if tempo != 100:
            note.append(tx("קצב {0}%").format(tempo))
        folder, fmt = self._docs(tx("פלייבק")), self.save_fmt
        dst = os.path.join(folder, f"{base} ({', '.join(note)}).{fmt}")

        def job(p):
            out = stretch.change(audio, semitones, tempo / 100.0, progress=lambda pct: p(2 + pct * 0.9, None))
            os.makedirs(folder, exist_ok=True)
            save(dst, out, tags={"title": os.path.splitext(os.path.basename(dst))[0]})
            p(100, None)
            return dst
        self._run(job, self._shifted, back=self.go_home, fail_text=tx("השינוי לא הצליח.\nנסה קובץ אחר."))

    def _shifted(self, dst):
        self.stack.setCurrentWidget(self.home)
        self._reveal(dst)
        self._info(tx("הפלייבק מוכן"), tx("הפלייבק נשמר בסולם ובקצב החדשים:\n\n{0}").format(dst))

    def sing_on_playback(self, path=None):
        """בוחרים קובץ נגינה, שרים עליו עם אוזניות, והתוכנה מעבדת את הקול ומערבבת אותו עם הפלייבק."""
        from .audio.fileio import load_stereo
        path = path or self._pick_audio(tx("בחר קובץ נגינה (פלייבק) לשיר עליו"))
        if not path:
            return
        try:
            backing = load_stereo(path)
        except AudioError as e:
            self.error(str(e))
            return
        if len(backing) > SR * 60 * 15:
            self.error(tx("הקובץ ארוך מדי.\nאפשר לשיר על פלייבק של עד 15 דקות."))
            return
        if not self._ask(tx("שירה על פלייבק"), tx("תשמע את הפלייבק ותשיר עליו.\n\n"
                         "חשוב: שים אוזניות, כדי שהנגינה לא תיכנס למיקרופון.\n"
                         "כשסיימת לשיר - לחץ 'סיום'."), tx("יש לי אוזניות - מתחילים"), tx("ביטול")):
            return
        self.stop_playing()
        self._playback = backing
        self.recorder = Overdub(np.concatenate([np.zeros((int(PRE_ROLL * SR), 2), dtype=np.float32), backing]))
        try:
            self.recorder.start()
        except AudioError as e:
            self.error(str(e))
            return
        self._begin_recording("playback", tx("שיר עם הפלייבק"), tx("מתכוננים..."), PRE_ROLL, len(backing) / SR, PRE_ROLL)

    def check_update(self):
        self.home.b_update.setEnabled(False)
        self.home.b_update.setText(tx("בודק..."))
        self.upd_worker = self._keep(Worker(lambda p: update.latest_version()))
        self.upd_worker.finished_ok.connect(self._update_result)
        self.upd_worker.failed.connect(lambda m: self._update_result(None))
        self.upd_worker.start()

    def _update_result(self, latest):
        self.home.b_update.setEnabled(True)
        self.home.b_update.setText(tx("בדוק אם יש גרסה חדשה (דרך האינטרנט)"))
        if latest is None:
            self._info(tx("בדיקת גרסה"), tx("לא הצלחתי לבדוק.\nייתכן שאין חיבור לאינטרנט במחשב הזה."))
        elif update.newer(latest, APP_VERSION):
            if not update.can_install():
                if self._ask(tx("יש גרסה חדשה"), tx("יש גרסה חדשה: {0}\n(אצלך מותקנת גרסה {1})\n\nלפתוח את דף ההורדה?").format(latest, APP_VERSION), tx("פתח את דף ההורדה"), tx("לא עכשיו")):
                    QDesktopServices.openUrl(QUrl(update.PAGE))
            elif self._ask(tx("יש גרסה חדשה"), tx("יש גרסה חדשה: {0}\n(אצלך מותקנת גרסה {1})\n\nלהוריד ולהתקין אותה עכשיו?\nהתוכנה תיסגר, תתעדכן ותיפתח מחדש.").format(latest, APP_VERSION),
                           tx("עדכן עכשיו"), tx("לא עכשיו")):
                self.install_update()
        else:
            self._info(tx("בדיקת גרסה"), tx("הגרסה שלך ({0}) היא העדכנית ביותר.").format(APP_VERSION))

    def install_update(self):
        """מוריד את הגרסה החדשה, בודק שהקובץ מקורי, מתקין וסוגר את התוכנה."""
        self.stop_playing()
        self.work.begin(tx("מוריד את הגרסה החדשה..."))
        self.stack.setCurrentWidget(self.work)
        folder = os.path.join(log_dir(), "update")

        def job(p):
            info = update.release_info()
            if info is None:
                raise update.UpdateError(tx("לא מצאתי קובץ התקנה לגרסה החדשה."))
            return update.download(info, folder, progress=lambda pct: p(pct, None))
        self.upd_worker = self._keep(Worker(job, tx("העדכון לא הצליח.\nאפשר להוריד את הגרסה החדשה מדף ההורדה.")))
        self.upd_worker.progress.connect(self.work.set_progress)
        self.upd_worker.finished_ok.connect(self._run_installer)
        self.upd_worker.failed.connect(self._update_failed)
        self.upd_worker.start()

    def _update_failed(self, message):
        self.go_home()
        if self._ask(tx("העדכון לא הצליח"), tx("{0}\n\nלפתוח את דף ההורדה?").format(message), tx("פתח את דף ההורדה"), tx("לא עכשיו")):
            QDesktopServices.openUrl(QUrl(update.PAGE))

    def _run_installer(self, path):
        try:
            update.install(path)
        except Exception:
            log_error(traceback.format_exc())
            self._update_failed(tx("לא הצלחתי להפעיל את קובץ ההתקנה."))
            return
        self.close()                       # שיר שלא נשמר נשאר בגיבוי האוטומטי ויוצע לשחזור אחרי העדכון

    # ---------- שחזור אחרי סגירה לא צפויה ----------
    def offer_recovery(self):
        found = recovery.pending()
        if not found:
            recovery.clear()
            return
        if found[0] == "recording":
            data = found[1]
            if self._ask(tx("נמצאה הקלטה"), tx("נמצאה הקלטה ({0} דקות) שהתוכנה נסגרה באמצע שלה.\nלשחזר אותה ולהמשיך?").format(fmt_time(len(data) / SR)), tx("שחזר"), tx("לא צריך")):
                self._keep_recording(data)
                recovery.clear()
                self.process(data)
                return
        else:
            _, raw, meta = found
            if self._ask(tx("נמצא שיר שלא נשמר"), tx("בפעם הקודמת התוכנה נסגרה לפני שהשיר נשמר.\nלפתוח אותו שוב?"),
                         tx("פתח את השיר"), tx("לא צריך")):
                self._open_loaded(raw, settings_from_dict(meta.get("settings")), meta.get("style"), meta)
                return
        recovery.clear()

    def closeEvent(self, ev):
        self.timer.stop()
        self.metronome.stop()
        if self.recorder:
            try:
                self.recorder.stop()
            except Exception:
                pass
        self.player.stop()
        if self._workers:                  # סגרו באמצע עבודה - מחכים שהיא תסתיים, כדי שהתוכנה תיסגר בצורה נקייה
            self.hide()
            for wk in list(self._workers):
                wk.wait(60000)
        if self.backup:
            self.backup.close()            # הקלטה שנקטעה נשארת בגיבוי - תוצע לשחזור בפעם הבאה
        elif not self.dirty:
            recovery.clear()               # הכול נשמר - אין מה לשחזר
        super().closeEvent(ev)
