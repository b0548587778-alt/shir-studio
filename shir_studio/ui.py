"""החלון הראשי: מחבר בין המסכים (בתיקייה screens) לבין העבודה עצמה. הכול בעברית, מימין לשמאל."""
import dataclasses
import os
import time
import traceback

import numpy as np
from PySide6.QtCore import Qt, QTimer, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QFileDialog

from . import APP_NAME, APP_VERSION, prefs as prefs_mod, recovery, update
from .audio import edit
from .audio.fileio import load, save, AudioError, SR
from .audio.devices import Recorder, Player, Metronome, Overdub
from .pipeline import Song, Settings
from .advanced import AdvancedDialog
from .music.styles import load_styles
from .log import log_error
from .project import save_project, load_project, settings_to_dict, settings_from_dict, History, batch, EXT
from .pitchview import PitchDialog
from .trimview import TrimDialog, PunchDialog
from .medleyview import MedleyDialog
from .screens import common
from .screens.common import STYLE, Worker, fmt_time
from .screens.home import HomeScreen
from .screens.record import RecordScreen, TITLE as REC_TITLE
from .screens.styles import StyleScreen
from .screens.work import WorkScreen
from .screens.done import DoneScreen

AUDIO_EXT = (".mp3", ".wav", ".flac", ".ogg", ".m4a")
AUDIO_FILTER = "קבצי שיר (*.mp3 *.wav *.flac *.ogg *.m4a)"
PRE_ROLL = 3.0            # שניות של ספירה לאחור / השמעה מקדימה לפני הקלטה
KEEP_RAWS = 6             # כמה גרסאות של ההקלטה נשמרות לביטול/חזרה


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setLayoutDirection(Qt.RightToLeft)
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
        self.styles = load_styles()
        self.prefs = prefs_mod.load()
        self.settings = prefs_mod.personal_settings(self.prefs)
        self.save_extras = bool(self.prefs.get("extras", False))
        self.save_fmt = self.prefs.get("fmt") if self.prefs.get("fmt") in ("mp3", "wav") else "mp3"
        self.metronome = Metronome()
        self.history = History()

        self.home = HomeScreen()
        self.rec = RecordScreen()
        self.style_page = StyleScreen(self.styles)
        self.work = WorkScreen()
        self.done = DoneScreen()
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        for w in (self.home, self.rec, self.style_page, self.work, self.done):
            self.stack.addWidget(w)
        self._connect()
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

    def _connect(self):
        h, r, s, d = self.home, self.rec, self.style_page, self.done
        h.record.connect(self.start_recording)
        h.choose.connect(self.choose_file)
        h.open_project.connect(self.open_project)
        h.batch.connect(self.batch_process)
        h.medley.connect(self.medley)
        h.check_update.connect(self.check_update)
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

    # ---------- הודעות (פונקציות נפרדות - כדי שהבדיקות יוכלו להחליף אותן) ----------
    def error(self, text):
        common.warn(self, text)

    def _info(self, title, text, button="אישור"):
        common.info(self, title, text, button)

    def _ask(self, title, text, yes="כן", no="לא"):
        return common.ask(self, title, text, yes, no)

    def style(self):
        return self.styles[self.style_page.current()]

    @staticmethod
    def _docs(*parts):
        return os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), "שיר סטודיו", *parts)

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
        self._begin_recording("new", REC_TITLE, "מתכוננים...", PRE_ROLL, 15 * 60)

    def _begin_recording(self, mode, title, wait_title, countdown, limit, pre=0.0):
        """ספירה לאחור (3-2-1, כדי שתחילת השיר לא תיחתך) ואז מסך ההקלטה."""
        self.rec_mode, self.rec_title, self.rec_limit, self.rec_pre = mode, title, limit, pre
        self.countdown_end = time.time() + countdown
        self.rec_start = None
        self._last_flush = 0.0
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
        if self.backup and now - self._last_flush > 1.0:      # גיבוי שוטף - שהקלטה לא תאבד אם משהו נסגר
            self._last_flush = now
            self.backup.write(self.recorder.drain())
        if s >= self.rec_limit:
            self.stop_recording()

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
        if self.rec_mode == "new":
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
        if mode == "overdub":
            data = data[int(self.rec_pre * SR):]
        if len(data) < SR * 2:
            self._end_backup()
            self.error("ההקלטה קצרה מדי.\nלחץ 'הקלט שיר' ושיר לפחות כמה שניות.")
            self.cancel_recording()
            return
        if np.max(np.abs(data)) < 0.003:
            self._end_backup()
            self.error("לא שמעתי קול בהקלטה.\nבדוק שהמיקרופון מחובר ודבר קרוב אליו.")
            self.cancel_recording()
            return
        self._keep_recording(data)
        self._end_backup()
        if mode == "overdub":
            self._finish_overdub(data)
            return
        self.process(data)
        if self.home.metro_on.isChecked():                 # שרו עם מטרונום - הקצב ידוע
            self.settings.tempo_mode, self.settings.bpm = "manual", float(self.home.metro_bpm.value())

    def _keep_recording(self, data):
        """שומר עותק של ההקלטה המקורית בתיקייה 'מסמכים\\שיר סטודיו\\הקלטות'."""
        try:
            d = self._docs("הקלטות")
            os.makedirs(d, exist_ok=True)
            save(os.path.join(d, time.strftime("הקלטה %Y-%m-%d %H-%M-%S.mp3")), data)
        except Exception:
            log_error(traceback.format_exc())

    # ---------- פתיחת קבצים (כפתור או גרירה) ----------
    def choose_file(self):
        start = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
        path, _ = QFileDialog.getOpenFileName(self, "בחר שיר", start, AUDIO_FILTER + ";;כל הקבצים (*.*)")
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
            self.error("זה לא קובץ שיר.\nאפשר לגרור קובץ שנגמר ב-mp3 או wav, או פרויקט של שיר סטודיו.")

    # ---------- ההקלטה שעובדים עליה ----------
    def _set_raw(self, data, grid=None):
        self.raws.append((data, grid))
        for i in range(len(self.raws) - KEEP_RAWS):        # גרסאות ישנות מאוד משוחררות מהזיכרון
            self.raws[i] = None
        self.raw_id = len(self.raws) - 1
        self.original = data
        self.song = Song(data, grid=grid)
        self._orig_play = None

    def process(self, data):
        """שיר חדש."""
        self.raws = []
        self._set_raw(data)
        self.result = None
        st = self.settings
        st.key, st.chords_text, st.sections, st.note_edits = None, "", None, None
        if st.tempo_mode == "manual" and not self.home.metro_on.isChecked():
            st.tempo_mode = "auto"
        self.history = History()
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
        self._begin_recording("punch", "שיר עכשיו את המשפט", "הקשב... ואז שיר", PRE_ROLL, hi - lo + 1.5, pre)

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
    def overdub(self):
        if self.song is None or self.result is None:
            return
        if not self._ask("שיר שוב עם הליווי",
                         "תשמע את הליווי המוכן ותשיר איתו את כל השיר מחדש.\n"
                         "השירה יוצאת מדויקת יותר בקצב, והשיר נשמע נקי יותר.\n\n"
                         "חשוב: שים אוזניות, כדי שהליווי לא ייכנס למיקרופון.",
                         "יש לי אוזניות - מתחילים", "ביטול"):
            return
        self.stop_playing()
        self.work.begin("מכין את הליווי...")
        self.stack.setCurrentWidget(self.work)
        song = self.song
        self._run(lambda p: song.stems(p), self._start_overdub, back=self._back_to_song)

    def _start_overdub(self, stems):
        acc = stems.get("ליווי")
        self.song.last_stems = None                       # מפנים זיכרון
        if acc is None:
            self.error("לא הצלחתי להכין את הליווי.")
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
        self._begin_recording("overdub", "שיר עם הליווי", "מתכוננים...", PRE_ROLL, len(acc) / SR, PRE_ROLL)

    def _finish_overdub(self, rec):
        """rec מתחיל בתחילת הליווי. הקול בשיר מתחיל 'lead' שניות אחר כך - כמו בהקלטה המקורית."""
        voice = rec[int(self.overdub_lead * SR):]
        if len(voice) < 2 * SR or np.max(np.abs(voice)) < 0.003:
            self.error("לא שמעתי שירה בהקלטה.\nנסה שוב.")
            self._back_to_song()
            return
        grid = self._grid()
        self._pin_key()
        self._set_raw(np.ascontiguousarray(voice, dtype=np.float32), grid)
        self.settings = dataclasses.replace(self.settings, chords_text="", sections=None, note_edits=None)
        self.make_song()

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
        dlg = AdvancedDialog(self, self.settings, info, self.save_extras, self.save_fmt, style=self.style())
        r = dlg.exec()
        if r in (1, 3):
            self.settings = dlg.settings()
            self.save_extras = dlg.extras.isChecked()
            self.save_fmt = dlg.fmt.currentData()
            if r == 3:                                   # 'שמור כטעם שלי' - ברירת המחדל לכל שיר חדש
                self.prefs = prefs_mod.store_personal(self.prefs, self.settings, self.style()["id"],
                                                      self.save_fmt, self.save_extras)
                self._info("נשמר", "ההגדרות נשמרו כטעם שלך.\nמעכשיו כל שיר חדש יתחיל איתן.")
        elif r == 2:
            self.settings, self.save_extras, self.save_fmt = Settings(), False, "mp3"
        else:
            return
        self.style_page.set_harmony(self.settings.harmony != "off")
        if remake and self.song:
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

        def job(p):
            if pending is not None:
                song.prepare(p, settings)
                from .music.analysis import apply_settings, set_key
                apply_settings(song.analysis, settings)
                set_key(song.analysis, pending)
            if change_key:
                p(5, "מחפש התאמה אחרת...")
                song.next_key()
            out = song.make(st, p, settings)
            # גיבוי אוטומטי של העבודה - אם המחשב נכבה לפני ששמרו, אפשר לשחזר
            recovery.save_session(song.raw, {"settings": settings_to_dict(settings), "style": st["id"],
                                             "key_index": song.analysis.key_index}, raw_changed)
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
        hint = f"סגנון: {st['name']}"
        info = self.song.info()
        if not info["steady"]:
            hint += "\nהשיר מושר בקצב חופשי, לכן הליווי רך ובלי תופים."
        elif self.settings.modulate and self.song.analysis.modulate_at is None:
            hint += "\nהשיר קצר מדי לעליית סולם."
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
                self.error("אי אפשר לחזור כל כך הרבה צעדים אחורה.")
                return
            data, grid = self.raws[rid]
            self.raw_id, self.original, self._orig_play = rid, data, None
            self.song = Song(data, grid=grid)
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
        what = {"result": "השיר המוכן", "original": "ההקלטה המקורית"}.get(self.playing, "")
        self.done.show_position(p, total, what)

    def _seek(self, frac):
        data = self.player.data if self.player.data is not None else self.result
        if data is None:
            return
        self._play(data, frac * len(data) / SR, self.playing or "result")

    # ---------- שמירה ----------
    def share_file(self):
        """קובץ קטן לשליחה בוואטסאפ או במייל (MP3 128, בערך 1MB לדקה)."""
        if self.result is None:
            return
        d = self._docs("לשליחה")
        try:
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, time.strftime("השיר שלי %Y-%m-%d %H-%M.mp3"))
            save(path, self.result, bitrate=128)
        except Exception:
            log_error(traceback.format_exc())
            self.error("לא הצלחתי ליצור את הקובץ לשליחה.")
            return
        mb = os.path.getsize(path) / 1024 / 1024
        self._reveal(path)
        self._info("קובץ לשליחה", f"נוצר קובץ קטן ({mb:.1f}MB) שמתאים לוואטסאפ ולמייל:\n\n{path}\n\n"
                   "בוואטסאפ: לחצו על 📎 ← מסמך, ובחרו את הקובץ.")

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
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), "השיר שלי - אקורדים.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "שמור דף אקורדים", start, "קובץ PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        from . import chordsheet
        try:
            title = os.path.splitext(os.path.basename(path))[0]
            chordsheet.write_pdf(path, chordsheet.sheet_data(self.song, title))
        except Exception:
            log_error(traceback.format_exc())
            self.error("לא הצלחתי לשמור את דף האקורדים.\nבחר מקום אחר ונסה שוב.")
            return
        self._reveal(path)
        self._info("נשמר", f"דף האקורדים נשמר:\n{path}\n\nאפשר לפתוח אותו ולהדפיס.")

    def save_project(self):
        if self.original is None:
            return
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), f"השיר שלי{EXT}")
        path, _ = QFileDialog.getSaveFileName(self, "שמור פרויקט", start, f"פרויקט שיר סטודיו (*{EXT})")
        if not path:
            return
        if not path.lower().endswith(EXT):
            path += EXT
        try:
            save_project(path, self.original, self.settings, self.style()["id"],
                         {"key_index": self.song.analysis.key_index if self.song.analysis else 0})
        except Exception:
            log_error(traceback.format_exc())
            self.error("לא הצלחתי לשמור את הפרויקט.\nבדוק שיש מקום בדיסק ונסה שוב.")
            return
        self.dirty = False
        self._info("נשמר", f"הפרויקט נשמר:\n{path}\n\nאפשר לפתוח אותו בהמשך ממסך הפתיחה.")

    def open_project(self, path=None):
        if not path:
            start = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            path, _ = QFileDialog.getOpenFileName(self, "פתח פרויקט", start, f"פרויקט שיר סטודיו (*{EXT})")
        if not path:
            return
        try:
            raw, settings, style_id, meta = load_project(path)
        except Exception:
            log_error(traceback.format_exc())
            self.error("לא הצלחתי לפתוח את הפרויקט.\nייתכן שהקובץ פגום.")
            return
        self._open_loaded(raw, settings, style_id, meta)

    def _open_loaded(self, raw, settings, style_id, meta):
        self.raws = []
        self._set_raw(raw)
        self.result = None
        self.history = History()
        self.settings = settings
        for i, st in enumerate(self.styles):
            if st["id"] == style_id:
                self.style_page.set_current(i)
        self.style_page.set_harmony(settings.harmony != "off")
        self._pending_key = meta.get("key_index", 0)
        self.make_song()

    def save_result(self):
        ext = self.save_fmt
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.MusicLocation), f"השיר שלי.{ext}")
        flt = "קובץ MP3 (*.mp3)" if ext == "mp3" else "קובץ WAV (*.wav)"
        path, _ = QFileDialog.getSaveFileName(self, "שמור את השיר", start, flt)
        if not path:
            return
        if not path.lower().endswith("." + ext):
            path += "." + ext
        extra = []
        try:
            save(path, self.result)
            if self.save_extras:
                folder = os.path.dirname(path)
                base = os.path.splitext(os.path.basename(path))[0]
                extra = self.song.export_extras(folder, base)
        except AudioError as e:
            self.error(str(e))
            return
        self.dirty = False
        msg = f"השיר נשמר בהצלחה!\n\n{path}"
        if extra:
            msg += "\n\nנשמרו גם:\n" + "\n".join(os.path.basename(p) for p in extra)
        self._info("נשמר", msg, "מעולה")

    # ---------- כמה שירים ברצף, ומחרוזת ----------
    def batch_process(self, paths=None):
        if not paths:
            start = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
            paths, _ = QFileDialog.getOpenFileNames(self, "בחר כמה שירים", start, AUDIO_FILTER)
        if not paths:
            return
        folder = QFileDialog.getExistingDirectory(self, "לאן לשמור את השירים המוכנים?", os.path.dirname(paths[0]))
        if not folder:
            return
        st = self.style()
        settings, fmt = self.settings, self.save_fmt
        self.work.begin("מעבד את השירים...")
        self.stack.setCurrentWidget(self.work)
        self._run(lambda p: batch(paths, st, settings, folder, fmt, progress=p), self._batch_done)

    def _batch_done(self, results):
        ok = [r for r in results if r[1]]
        bad = [r for r in results if not r[1]]
        msg = f"הוכנו {len(ok)} שירים (סגנון: {self.style()['name']})."
        if ok:
            msg += f"\nנשמרו בתיקייה:\n{os.path.dirname(ok[0][1])}"
        if bad:
            msg += "\n\nלא הצלחתי להכין:\n" + "\n".join(os.path.basename(r[0]) for r in bad)
        self.go_home()
        self._info("סיום", msg)

    def medley(self):
        st = self.style()
        dlg = MedleyDialog(self, st["name"])
        if not dlg.exec() or len(dlg.paths()) < 2:
            return
        ext = self.save_fmt
        start = os.path.join(QStandardPaths.writableLocation(QStandardPaths.MusicLocation), f"מחרוזת.{ext}")
        path, _ = QFileDialog.getSaveFileName(self, "שמור את המחרוזת", start,
                                              "קובץ MP3 (*.mp3)" if ext == "mp3" else "קובץ WAV (*.wav)")
        if not path:
            return
        if not path.lower().endswith("." + ext):
            path += "." + ext
        self.make_medley(dlg.paths(), path, dlg.process.isChecked(), dlg.cross.value())

    def make_medley(self, paths, path, process, crossfade):
        from .medley import make_medley
        st, settings = self.style(), self.settings
        self.work.begin("מכין את המחרוזת...")
        self.stack.setCurrentWidget(self.work)

        def done(res):
            seconds, bad = res
            msg = f"המחרוזת מוכנה ({fmt_time(seconds)} דקות):\n\n{path}"
            if bad:
                msg += "\n\nלא הצלחתי לפתוח:\n" + "\n".join(os.path.basename(p) for p in bad)
            self.go_home()
            self._reveal(path)
            self._info("מחרוזת", msg, "מעולה")
        self._run(lambda p: make_medley(paths, path, st, settings, process, crossfade, p), done,
                  fail_text="לא הצלחתי להכין את המחרוזת.\nנסה שוב.")

    # ---------- גרסה חדשה ----------
    def check_update(self):
        self.home.b_update.setEnabled(False)
        self.home.b_update.setText("בודק...")
        self.upd_worker = self._keep(Worker(lambda p: update.latest_version()))
        self.upd_worker.finished_ok.connect(self._update_result)
        self.upd_worker.failed.connect(lambda m: self._update_result(None))
        self.upd_worker.start()

    def _update_result(self, latest):
        self.home.b_update.setEnabled(True)
        self.home.b_update.setText("בדוק אם יש גרסה חדשה (דרך האינטרנט)")
        if latest is None:
            self._info("בדיקת גרסה", "לא הצלחתי לבדוק.\nייתכן שאין חיבור לאינטרנט במחשב הזה.")
        elif update.newer(latest, APP_VERSION):
            if self._ask("יש גרסה חדשה", f"יש גרסה חדשה: {latest}\n(אצלך מותקנת גרסה {APP_VERSION})\n\n"
                         "לפתוח את דף ההורדה?", "פתח את דף ההורדה", "לא עכשיו"):
                QDesktopServices.openUrl(QUrl(update.PAGE))
        else:
            self._info("בדיקת גרסה", f"הגרסה שלך ({APP_VERSION}) היא העדכנית ביותר.")

    # ---------- שחזור אחרי סגירה לא צפויה ----------
    def offer_recovery(self):
        found = recovery.pending()
        if not found:
            recovery.clear()
            return
        if found[0] == "recording":
            data = found[1]
            if self._ask("נמצאה הקלטה", f"נמצאה הקלטה ({fmt_time(len(data) / SR)} דקות) שהתוכנה נסגרה באמצע שלה.\n"
                         "לשחזר אותה ולהמשיך?", "שחזר", "לא צריך"):
                self._keep_recording(data)
                recovery.clear()
                self.process(data)
                return
        else:
            _, raw, meta = found
            if self._ask("נמצא שיר שלא נשמר", "בפעם הקודמת התוכנה נסגרה לפני שהשיר נשמר.\nלפתוח אותו שוב?",
                         "פתח את השיר", "לא צריך"):
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
