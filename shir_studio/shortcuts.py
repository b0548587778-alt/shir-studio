"""קיצורי מקלדת. כל קיצור פעיל רק במסך שבו הוא רלוונטי - כך הוא לא 'בולע' מקשים במסכים אחרים."""
from PySide6.QtGui import QKeySequence, QShortcut

SEEK = 5.0                 # שניות קדימה / אחורה בחצים


def table(win):
    """(מקש, המסכים שבהם הוא פעיל, הפעולה, התיאור למשתמש). None = בכל המסכים."""
    home, done, styles = win.home, win.done, win.style_page
    return [
        ("Space", (done,), lambda: toggle_play(win), "האזנה לשיר המוכן / עצירה"),
        ("Right", (done,), lambda: skip(win, -SEEK), "חמש שניות אחורה"),
        ("Left", (done,), lambda: skip(win, SEEK), "חמש שניות קדימה"),
        ("B", (done,), win.compare, "לפני / אחרי"),
        ("Escape", (done, styles), win.stop_playing, "עצירת ההשמעה"),
        ("Ctrl+Z", (done,), win.undo, "ביטול שינוי"),
        ("Ctrl+Y", (done,), win.redo, "החזרת שינוי"),
        ("Ctrl+S", (done,), win.save_result, "שמירת השיר"),
        ("Ctrl+Shift+S", (done,), win.save_project, "שמירת פרויקט"),
        ("Ctrl+T", (done,), win.practice, "מצב תרגול"),
        ("Ctrl+L", (done,), win.edit_lyrics, "מילות השיר"),
        ("Ctrl+G", (done,), win.show_pitch, "גרף ותיקון ידני"),
        ("Ctrl+R", (home,), win.start_recording, "הקלטת שיר"),
        ("Ctrl+O", (home,), win.choose_file, "בחירת קובץ מהמחשב"),
        ("Ctrl+M", (home,), win.mic_check, "בדיקת מיקרופון"),
        ("Ctrl+N", (done,), win.new_song, "שיר חדש"),
        ("F1", None, lambda: show_help(win), "רשימת הקיצורים"),
    ]


def install(win):
    """יוצר את הקיצורים ומפעיל אותם לפי המסך המוצג."""
    win.shortcuts = []
    for key, screens, fn, text in table(win):
        sc = QShortcut(QKeySequence(key), win)
        sc.activated.connect(fn)
        win.shortcuts.append((sc, screens, key, text))
    win.stack.currentChanged.connect(lambda _: refresh(win))
    refresh(win)


def refresh(win):
    cur = win.stack.currentWidget()
    for sc, screens, _, _ in win.shortcuts:
        sc.setEnabled(screens is None or cur in screens)


def toggle_play(win):
    if win.player.position() is not None:
        win.stop_playing()
    else:
        win.play_result()


def skip(win, seconds):
    pos = win.player.position()
    if pos is None or win.player.data is None:
        return
    win._play(win.player.data, min(max(0.0, pos + seconds), max(win.player.length() - 0.5, 0.0)), win.playing)


NAMES = {"Space": "רווח", "Right": "חץ ימינה", "Left": "חץ שמאלה", "Escape": "Esc"}


def help_text(win):
    rows = []
    for _, _, key, text in win.shortcuts:
        rows.append(f"⁦{NAMES.get(key, key)}⁩  -  {text}")
    return "\n".join(rows)


def show_help(win):
    win._info("קיצורי מקלדת", help_text(win))
