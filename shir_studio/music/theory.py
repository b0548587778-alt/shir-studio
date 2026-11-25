"""סולמות ואקורדים - כולל סולם 'אהבה רבה' (פריגיש) הנפוץ בניגונים חסידיים."""
from ..i18n import tx
import numpy as np

NOTE_NAMES = [tx("דו"), tx("דו#"), tx("רה"), tx("מי♭"), tx("מי"), tx("פה"), tx("פה#"), tx("סול"), tx("סול#"), tx("לה"), tx("סי♭"), tx("סי")]

# פרופילי קרומהנסל-קסלר
MAJOR_P = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_P = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
AHAVA_P = np.array([6.30, 4.20, 2.10, 2.40, 5.00, 3.80, 2.20, 4.60, 4.00, 2.30, 3.60, 2.20])

# 'מי שברך' (אוקראיני-דורי): דו רה מי♭ פה# סול לה סי♭
MISHEB_P = np.array([6.30, 2.10, 4.00, 4.60, 2.10, 2.30, 4.20, 5.00, 2.10, 3.70, 3.60, 2.20])

# 'אדוני מלך' (מיקסולידי): דו רה מי פה סול לה סי♭ - נפוץ בתפילות ובניגונים
ADONAI_P = np.array([6.35, 2.10, 3.50, 2.20, 4.50, 4.00, 2.20, 5.20, 2.20, 3.50, 4.20, 2.00])

# מצב: (שם, מדרגות הסולם, פרופיל, אקורדים: (שם-תצוגה, מרחק שורש מהטוניקה, איכות))
MODES = {
    "major": (tx("מז'ור"), [0, 2, 4, 5, 7, 9, 11], MAJOR_P,
              [("I", 0, "maj"), ("ii", 2, "min"), ("iii", 4, "min"), ("IV", 5, "maj"),
               ("V", 7, "maj"), ("vi", 9, "min")]),
    "minor": (tx("מינור"), [0, 2, 3, 5, 7, 8, 10, 11], MINOR_P,
              [("i", 0, "min"), ("iv", 5, "min"), ("V", 7, "maj"), ("VI", 8, "maj"),
               ("III", 3, "maj"), ("VII", 10, "maj")]),
    "ahava": (tx("אהבה רבה"), [0, 1, 4, 5, 7, 8, 10], AHAVA_P,
              [("I", 0, "maj"), ("II", 1, "maj"), ("iv", 5, "min"), ("vii", 10, "min")]),
    "misheberach": (tx("מי שברך"), [0, 2, 3, 6, 7, 9, 10], MISHEB_P,
                    [("i", 0, "min"), ("II", 2, "maj"), ("III", 3, "maj"), ("v", 7, "min")]),
    "adonai": (tx("אדוני מלך"), [0, 2, 4, 5, 7, 9, 10], ADONAI_P,
               [("I", 0, "maj"), ("IV", 5, "maj"), ("v", 7, "min"), ("VII", 10, "maj"), ("ii", 2, "min")]),
}

QUALITY = {"maj": [0, 4, 7], "min": [0, 3, 7]}


def detect_key(pc_weights: np.ndarray, final_pc=None):
    """pc_weights: משקל לכל אחד מ-12 הצלילים. מחזיר (טוניקה, מצב, ציון)."""
    return rank_keys(pc_weights, final_pc)[0]


def rank_keys(pc_weights, final_pc=None):
    """כל הסולמות האפשריים, מהמתאים ביותר לפחות מתאים."""
    res = []
    for mode, (_, _, prof, _) in MODES.items():
        for tonic in range(12):
            p = np.roll(prof, tonic)
            c = np.corrcoef(p, pc_weights)[0, 1]
            if mode == "ahava":
                c -= 0.05
            elif mode == "adonai":
                c -= 0.10          # אותם צלילים כמו מז'ור של הדרגה הרביעית - רק כשהוא באמת בולט
            elif mode == "misheberach":
                c -= 0.08          # סולם נדיר יותר - רק כשהוא באמת בולט          # מעדיפים מז'ור/מינור כשקרוב
            if final_pc is not None and tonic == final_pc:
                c += 0.2           # שירים מסתיימים בדרך כלל בטוניקה
            res.append((tonic, mode, c))
    res.sort(key=lambda r: -r[2])
    # מסירים כפילויות של אותה קבוצת צלילים כשהציון כמעט זהה? לא - שומרים, הן שונות בטוניקה
    return res


def scale_pcs(tonic, mode):
    return sorted({(tonic + d) % 12 for d in MODES[mode][1]})


def chords_for(tonic, mode):
    """רשימת אקורדים: dict עם root (pc), quality, pcs, name, degree."""
    out = []
    for i, (deg, off, q) in enumerate(MODES[mode][3]):
        root = (tonic + off) % 12
        out.append({"degree": deg, "index": i, "root": root, "quality": q,
                    "pcs": [(root + d) % 12 for d in QUALITY[q]]})
    return out


def key_name(tonic, mode):
    return f"{NOTE_NAMES[tonic]} {MODES[mode][0]}"
