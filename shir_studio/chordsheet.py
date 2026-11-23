"""דף אקורדים להדפסה (PDF) - למי שרוצה ללוות את השיר בעצמו בגיטרה, בפסנתר או באורגן."""
from . import APP_NAME
from .music.analysis import NAMES, chord_bars
from .music.theory import NOTE_NAMES, MODES

PER_ROW = 4


def _symbol(c, up):
    s = NAMES[(c["root"] + up) % 12] + ("m" if c["quality"] == "min" else "")
    if c.get("seventh") == 11:
        s += "maj7"
    elif c.get("seventh") == 10:
        s += "7"
    return s


def sheet_data(song, title="השיר שלי"):
    """מה שכתוב בדף: סולם, קצב, והאקורדים תיבה אחרי תיבה, מחולקים לבית ולפזמון.
    האקורדים כתובים כפי שהם נשמעים - כולל העברת הסולם ועליית הסולם בסוף."""
    from .music.arrange import MOD_UP
    a = song.analysis
    tp = a.transpose
    last = max([nt.end for nt in a.notes] + [0.0])
    bars = []
    for s, e in chord_bars(a):
        if s > last:
            break
        up = tp + (MOD_UP if a.modulate_at is not None and s >= a.modulate_at - 0.03 else 0)
        names = []
        for cs, ce, c in a.chords:
            if cs < e - 0.05 and ce > s + 0.05:
                n = _symbol(c, up)
                if not names or names[-1] != n:
                    names.append(n)
        bars.append(" ".join(names[:4]) or "-")
    sections = []
    if a.steady:
        phrases = song.phrases()
        lv = a.sections_override or []
        counts = {0: 0, 1: 0}
        for p in range(0, len(bars), 8):
            i = p // 8
            auto = phrases[i][2] if i < len(phrases) else 1
            kind = int(lv[i]) if i < len(lv) else int(auto)
            counts[kind] += 1
            label = ("פזמון" if kind else "בית") + (f" {counts[kind]}" if counts[kind] > 1 else "")
            if a.modulate_at is not None and i < len(phrases) and abs(phrases[i][0] - a.modulate_at) < 0.05:
                label += "  ·  עליית סולם (חצי טון)"
            sections.append((label, bars[p:p + 8]))
    else:
        sections.append(("", bars))
    info = [f"סולם: {NOTE_NAMES[(a.tonic + tp) % 12]} {MODES[a.mode][0]}"]
    if a.steady:
        info += [f"קצב: ⁦{int(round(a.tempo))} BPM⁩", f"משקל: ⁦{a.meter}/4⁩"]
    else:
        info.append("קצב חופשי - כל אקורד נמשך כשתי שניות")
    return {"title": title, "info": "   ·   ".join(info), "sections": sections}


def as_text(data):
    """אותו דף כטקסט פשוט."""
    lines = [data["title"], data["info"], ""]
    for label, bars in data["sections"]:
        if label:
            lines.append(f"[{label}]")
        for i in range(0, len(bars), PER_ROW):
            lines.append("| " + " | ".join(bars[i:i + PER_ROW]) + " |")
        lines.append("")
    return "\n".join(lines)


def write_pdf(path, data):
    """מצייר את הדף ל-PDF בגודל A4. האקורדים משמאל לימין (כמו בתווים), הכותרות בעברית."""
    from PySide6.QtCore import Qt, QRectF, QMarginsF
    from PySide6.QtGui import QPdfWriter, QPainter, QFont, QPen, QColor, QPageSize, QPageLayout

    w = QPdfWriter(path)
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
    w.setResolution(150)
    w.setTitle(data["title"])
    p = QPainter(w)
    if not p.isActive():
        raise OSError(path)
    W, H = w.width(), w.height()

    def font(size, bold=False):
        f = QFont("Arial", size)
        f.setBold(bold)
        return f

    def text(y, h, s, f, align=Qt.AlignHCenter, color="#1d2733"):
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(0, y, W, h), int(align | Qt.AlignVCenter), s)

    y = 0
    text(y, 80, data["title"], font(24, True))
    y += 90
    text(y, 40, data["info"], font(12), color="#4a5664")
    y += 70
    bw, bh = W / PER_ROW, 90
    for label, bars in data["sections"]:
        rows = (len(bars) + PER_ROW - 1) // PER_ROW
        if y + 50 + min(rows, 2) * bh > H - 40:
            w.newPage()
            y = 0
        if label:
            text(y, 44, label, font(13, True), Qt.AlignRight, "#24466b")
            y += 50
        for r in range(rows):
            if y + bh > H - 40:
                w.newPage()
                y = 0
            for c, bar in enumerate(bars[r * PER_ROW:(r + 1) * PER_ROW]):
                rect = QRectF(c * bw, y, bw, bh)
                p.setPen(QPen(QColor("#9aa5b1"), 2))
                p.drawRect(rect)
                p.setFont(font(15 if len(bar) > 9 else 18, True))
                p.setPen(QColor("#1d2733"))
                p.drawText(rect, int(Qt.AlignCenter), bar)
            y += bh
        y += 26
    text(H - 30, 30, f"הודפס מתוך {APP_NAME}", font(9), color="#8a94a0")
    p.end()
