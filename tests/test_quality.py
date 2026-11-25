"""בדיקות האיכות של השדרוג: שירה מזויפת בכוונה, התפתחות העיבוד, שפות, ורישיון במסכים."""
import json
import os
import re
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from singers import CASES, SONGS, sing
from shir_studio.music import analysis as A
from shir_studio.music.arrange import arc, render
from shir_studio.music.styles import load_styles


def test_badly_off_key_singer_is_understood():
    """זיוף חזק (עד 0.7 חצי טון לכל תו). לפני השדרוג: הסולם זוהה שגוי ו-74% מהתווים נשארו מזויפים."""
    import quality_report
    r = quality_report.measure("זיוף חזק")
    assert r["key_ok"], r["key"]
    assert r["bad"] <= 0.15 and r["mean"] <= 0.12
    assert r["chord_fit"] >= 0.6


def test_medium_off_key_singer_comes_out_clean():
    """זיוף בינוני. לפני השדרוג: 20% מהתווים נשארו מזויפים (התווים הכי מזויפים תוקנו רק בשליש)."""
    import quality_report
    r = quality_report.measure("זיוף בינוני")
    assert r["key_ok"] and r["bad"] <= 0.05


def test_melody_targets_use_intervals_and_scale():
    N = A.Note
    # הזמר שר את כל המשפט נמוך מדי בכמעט חצי טון, אבל המרווחים נכונים: דו רה מי פה סול
    notes = [N(i * 0.5, i * 0.5 + 0.45, p - 0.45) for i, p in enumerate([60, 62, 64, 65, 67])]
    assert A.melody_targets(notes, [0, 2, 4, 5, 7, 9, 11]) == [60, 62, 64, 65, 67]
    # תו בודד שנפל בין שני צלילים הולך לצליל שבסולם
    notes = [N(0, .45, 60.0), N(.5, .95, 63.5), N(1, 1.45, 67.0)]
    assert A.melody_targets(notes, [0, 2, 4, 5, 7, 9, 11])[1] == 64


def test_long_note_that_sags_is_straightened_but_vibrato_stays():
    n = 200
    t = np.arange(n) * 0.01
    vib = 0.3 * np.sin(2 * np.pi * 5.5 * t)
    mc = 60 + vib - 0.6 * t / t[-1]                      # תו של 2 שניות ש'נוזל' למטה ב-0.6 חצי טון
    nt = A.Note(0.0, 2.0, float(np.median(mc)), 60)
    corr = A._targets(mc, np.ones(n, bool), [nt], [0, 2, 4, 5, 7, 9, 11], 1.0)
    after = mc + corr
    mid = slice(30, 170)
    slope = np.polyfit(t[mid], after[mid], 1)[0]
    assert abs(slope) < 0.12                             # הנזילה (0.3 לשנייה) כמעט נעלמה
    assert np.std(after[mid] - np.polyval(np.polyfit(t[mid], after[mid], 1), t[mid])) > 0.15   # הוויברטו נשאר


def test_arrangement_develops_to_a_climax():
    assert arc([0, 1, 0, 1])[-1] == 1.0 and arc([0, 1, 0, 1])[0] < 0.4
    a4 = arc([0, 0, 1, 0, 1])
    assert a4[-2] < a4[-1] and a4[0] == min(a4)
    x, _truth, _beats = sing(SONGS["shabbat"][0], repeats=5, wobble=0.1)
    from shir_studio.pipeline import Song
    s = Song(x)
    s.prepare(lambda *q: None)
    an = s.analysis
    sym = [st for st in load_styles() if "symphonic" in st["id"]][0]
    tracks, lead = render(an, sym)
    by = {}
    for spec, buf, events in tracks:
        by.setdefault(spec["instrument"], []).append((spec, events))
    last_voice = max(nt.end for nt in an.notes) + lead
    first_voice = min(nt.start for nt in an.notes) + lead
    span = last_voice - first_voice
    brass = [e[0] for spec, ev in by["brass"] for e in ev if spec.get("from")]
    harp = [e[0] for spec, ev in by["harp"] for e in ev]
    assert brass and min(brass) > first_voice + 0.55 * span          # כלי המתכת נכנסים רק בשיא
    assert min(harp) < first_voice + 0.1 * span                       # הנבל שם מההתחלה
    dbl = [ev for spec, ev in by["strings"] if spec.get("double")]
    assert dbl and min(e[0] for e in dbl[0]) > first_voice + 0.5 * span   # הכינורות מצטרפים למנגינה בשיא
    # השיא חזק מההתחלה
    mix = sum(np.pad(b if b.ndim == 1 else b.mean(axis=1), (0, 0)) [: min(len(t[1]) for t in tracks)]
              for _, b, _ in tracks)
    sr = 44100
    q = lambda t0, t1: float(np.sqrt(np.mean(mix[int(t0 * sr): int(t1 * sr)] ** 2)))
    assert q(last_voice - 0.25 * span, last_voice) > 1.5 * q(first_voice, first_voice + 0.25 * span)


LANG_DIR = os.path.join(os.path.dirname(__file__), "..", "shir_studio", "lang")


@pytest.mark.parametrize("code", ["en", "yi"])
def test_every_text_is_translated(code):
    he = json.load(open(os.path.join(LANG_DIR, "he.json"), encoding="utf-8"))
    tr = json.load(open(os.path.join(LANG_DIR, code + ".json"), encoding="utf-8"))
    ph = lambda s: sorted(re.findall(r"\{[^{}]*\}", s))
    assert not [k for k in he if not tr.get(k)]                       # אין טקסט בלי תרגום
    assert not [k for k in he if ph(k) != ph(tr[k])]                  # המקומות למספרים ולשמות נשמרו


def test_language_files_match_the_code():
    import i18n_wrap
    keys, problems = [], []
    for base, _dirs, files in os.walk(i18n_wrap.ROOT):
        for fn in files:
            if fn.endswith(".py") and fn not in i18n_wrap.SKIP:
                src = open(os.path.join(base, fn), encoding="utf-8").read()
                k, pr = i18n_wrap.process(os.path.join(base, fn), write=False)
                assert open(os.path.join(base, fn), encoding="utf-8").read() == src
                keys += k
                problems += pr
    he = json.load(open(os.path.join(LANG_DIR, "he.json"), encoding="utf-8"))
    assert not problems
    assert not [k for k in set(keys) | set(i18n_wrap.style_keys()) if k not in he]   # טקסט חדש שלא נכנס לקובצי השפה


def test_switching_language_translates_and_flips_direction():
    from shir_studio import i18n
    from PySide6.QtCore import Qt
    try:
        assert i18n.set_language("en") == "en"
        assert i18n.tx("שיר סטודיו") == "Shir Studio" and i18n.direction() == Qt.LeftToRight
        assert i18n.set_language("yi") == "yi" and i18n.direction() == Qt.RightToLeft
        assert i18n.tx("משפט שאין לו תרגום") == "משפט שאין לו תרגום"
    finally:
        i18n.set_language("he")
    assert i18n.tx("שיר סטודיו") == "שיר סטודיו"


def test_trial_blocks_saving_when_used_up(qapp, appdata, fake_sd, tmp_path, monkeypatch):
    from shir_studio import license as lic
    from shir_studio.ui import MainWindow
    from PySide6.QtWidgets import QFileDialog
    w = MainWindow()
    try:
        assert "10" in w.home.lic_label.text()
        w.result = np.zeros((44100, 2), np.float32)
        w.song = object()
        target = str(tmp_path / "song.mp3")
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (target, ""))
        monkeypatch.setattr(w, "_info", lambda *a, **k: None)
        w.save_extras = False
        w.save_result()
        assert os.path.exists(target) and lic.status()["used"] == 1
        w.save_result()                                   # אותו שיר שוב - לא נספר פעמיים
        assert lic.status()["used"] == 1
        lic.count_song(lic.TRIAL_SONGS)
        os.remove(target)
        asked = []
        monkeypatch.setattr(w, "_ask", lambda *a, **k: asked.append(a) or False)
        w.save_result()
        assert asked and not os.path.exists(target)       # הניסיון נגמר: לא נשמר, והוצע להזין קוד
    finally:
        w.dirty = False
        w.close()
