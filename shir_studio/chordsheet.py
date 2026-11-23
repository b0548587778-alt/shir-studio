"""דף אקורדים להדפסה (PDF): האקורדים של השיר תיבה אחרי תיבה - לנגן שמלווה את הזמר."""
from .music.analysis import chord_bars
from .music.theory import key_name

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
PER_LINE = 4
PHRASE = 8


def chord_name(c, shift=0):
    n = NAMES[(c["root"] + shift) % 12] + ("m" if c["quality"] == "min" else "")
    s = c.get("seventh")
    return n + ("maj7" if s == 11 else ("7" if s == 10 else ""))


def sheet(song, title=""):
    """הנתונים של הדף: כותרת, שורת מידע, ורשימת חלקים - כל חלק: (שם החלק, [תיבות]), תיבה = רשימת אקורדים."""
    a = song.analysis
    tp = a.transpose
    bars = chord_bars(a)
    lift_t = a.lift_t if (a.lift and a.lift_t is not None) else None
    cells = []
    for s, e in bars:
        up = a.lift if (lift_t is not None and s >= lift_t - 0.05) else 0
        inside = []
        for cs, ce, c in a.chords:
            if cs < e - 0.05 and ce > s + 0.05:
                name = chord_name(c, tp + up)
                if not inside or inside[-1] != name:
                    inside.append(name)
        cells.append(inside[:4])
    # תיבה שהאקורד בה לא השתנה מסומנת בסימן החזרה המקובל (חוץ מתחילת חלק - שם תמיד כותבים את האקורד)
    shown, prev = [], None
    for i, c in enumerate(cells):
        first = (a.steady and i % PHRASE == 0) or prev is None
        c = c or ([prev[-1]] if prev else ["%"])
        shown.append(["%"] if (c == prev and len(c) == 1 and not first) else c)
        prev = c
    parts = []
    if a.steady:
        phrases = song.phrases()
        over = getattr(a, "sections_override", None) or []
        lifted = False
        for p in range(0, len(shown), PHRASE):
            i = p // PHRASE
            lvl = int(over[i]) if i < len(over) else (phrases[i][2] if i < len(phrases) else 1)
            name = "פזמון" if lvl else "בית"
            if lift_t is not None and bars[p][0] >= lift_t - 0.05 and not lifted:
                name += f" (עלייה של {'חצי טון' if a.lift == 1 else 'טון'})"
                lifted = True
            part = shown[p:p + PHRASE]
            if parts and len(part) <= 2:                 # זנב של תיבה או שתיים - שייך לחלק הקודם
                parts[-1] = (parts[-1][0], parts[-1][1] + part)
            else:
                parts.append((name, part))
        meter = "6/8" if getattr(a, "compound", False) else f"{a.meter}/4"
        info = f"סולם: {key_name((a.tonic + tp) % 12, a.mode)}   ·   קצב: ⁦{int(round(a.tempo))} BPM⁩   ·   משקל: ⁦{meter}⁩"
    else:
        parts.append(("", shown))
        info = f"סולם: {key_name((a.tonic + tp) % 12, a.mode)}   ·   קצב חופשי"
    return {"title": title or "דף אקורדים", "info": info, "parts": parts}


def as_text(data):
    """הדף כטקסט פשוט (לבדיקות ולהעתקה)."""
    out = [data["title"], data["info"], ""]
    for name, bars in data["parts"]:
        if name:
            out.append(name + ":")
        for i in range(0, len(bars), PER_LINE):
            out.append("| " + " | ".join(" ".join(b) for b in bars[i:i + PER_LINE]) + " |")
        out.append("")
    return "\n".join(out)


def save_pdf(path, data):
    """מצייר את הדף לקובץ PDF בגודל A4."""
    from PySide6.QtCore import Qt, QRectF, QMarginsF
    from PySide6.QtGui import QPdfWriter, QPainter, QFont, QPen, QColor, QPageSize, QPageLayout

    w = QPdfWriter(path)
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
    w.setResolution(150)
    w.setTitle(data["title"])
    p = QPainter(w)
    try:
        W, H = w.width(), w.height()
        mm = 150 / 25.4
        heb = lambda size, bold=False: QFont("Arial", size, QFont.Bold if bold else QFont.Normal)
        y = 0.0

        def text(s, font, h, align=Qt.AlignHCenter, color="#1d2733"):
            nonlocal y
            p.setFont(font)
            p.setPen(QColor(color))
            p.drawText(QRectF(0, y, W, h), int(align | Qt.AlignVCenter | Qt.TextSingleLine), s)
            y += h

        def header():
            nonlocal y
            y = 0.0
            text(data["title"], heb(22, True), 14 * mm, color="#24466b")
            text(data["info"], heb(12), 8 * mm, color="#4a5664")
            y += 4 * mm

        header()
        row_h, name_h = 15 * mm, 9 * mm
        cell_w = W / PER_LINE
        for name, bars in data["parts"]:
            rows = [bars[i:i + PER_LINE] for i in range(0, len(bars), PER_LINE)]
            need = (name_h if name else 0) + row_h * min(2, len(rows))
            if y + need > H:
                w.newPage()
                header()
            if name:
                text(name, heb(13, True), name_h, align=Qt.AlignRight, color="#2c7a3f")
            for row in rows:
                if y + row_h > H:
                    w.newPage()
                    header()
                p.setPen(QPen(QColor("#24466b"), 2))
                # אקורדים נכתבים משמאל לימין, כמקובל בתווים
                for i, bar in enumerate(row):
                    r = QRectF(i * cell_w, y, cell_w, row_h - 3 * mm)
                    p.setPen(QPen(QColor("#24466b"), 2))
                    p.drawLine(r.topLeft(), r.bottomLeft())
                    if i == len(row) - 1:
                        p.drawLine(r.topRight(), r.bottomRight())
                    p.setPen(QColor("#1d2733"))
                    p.setFont(heb(17 if len(bar) <= 2 else 13, True))
                    sub = r.width() / max(1, len(bar))
                    for j, ch in enumerate(bar):
                        p.drawText(QRectF(r.left() + j * sub, r.top(), sub, r.height()),
                                   int(Qt.AlignCenter | Qt.TextSingleLine), "⁦" + ch + "⁩")
                y += row_h
            y += 3 * mm
        p.setFont(heb(9))
        p.setPen(QColor("#8a94a0"))
        p.drawText(QRectF(0, H - 6 * mm, W, 6 * mm), int(Qt.AlignCenter), "הוכן בתוכנת שיר סטודיו")
    finally:
        p.end()
    _repair(path)


def _repair(path):
    """בגרסת Qt שבשימוש, סוגר מילון הפרטים של הקובץ נכתב שגוי ('2' במקום '>>'). מתקנים באותו אורך בדיוק,
    כדי שהקובץ ייפתח בלי אזהרות בכל תוכנה."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        bad, good = b"/Trapped /False\n2\nendobj", b"/Trapped /False>>\nendobj"
        if data.count(bad) == 1:
            with open(path, "wb") as f:
                f.write(data.replace(bad, good))
    except OSError:
        pass
