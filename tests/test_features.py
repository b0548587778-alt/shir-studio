"""בדיקות לתכונות: תיקון ידני של צלילים, עליית טון, אדוני מלך, 6/8, עריכת משפטים, דף אקורדים, עדכון."""
import os
import numpy as np
import pytest
from synth_voice import sing
from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles
from shir_studio.music import analysis, arrange, theory
from shir_studio.audio import edit
from shir_studio.audio.fileio import SR
from shir_studio.audio.pitch import yin, hz_to_midi, FRAME_SEC
from shir_studio.project import settings_to_dict, settings_from_dict

quiet = lambda p, m=None: None


def style(sid):
    return [s for s in load_styles() if s["id"] == sid][0]


@pytest.fixture(scope="module")
def song():
    x, _ = sing(bpm=120, repeats=3)
    s = Song(x)
    s.prepare(quiet)
    return s


def sung_pitch(x, start, end):
    """הגובה הממוצע (midi) של קטע בקול."""
    f0, _ = yin(x)
    seg = f0[int((start + 0.08) / FRAME_SEC):int((end - 0.05) / FRAME_SEC)]
    return float(np.median(hz_to_midi(seg[seg > 0])))


def long_note(s, k=5):
    return [nt for nt in s.analysis.notes if nt.end - nt.start > 0.7][k]


# ---------- תיקון ידני ----------
def test_manual_note_fix_moves_only_that_note(song):
    st0 = Settings(tune=100)
    song.make(style("02_piano"), quiet, st0)
    nt = long_note(song)
    other = long_note(song, 1)
    auto = sung_pitch(song.tuned, nt.start, nt.end)
    other_before = sung_pitch(song.tuned, other.start, other.end)
    target = int(round(auto)) + 2
    st = Settings(tune=100, note_fixes=[[(nt.start + nt.end) / 2, target]])
    song.make(style("02_piano"), quiet, st)
    assert abs(sung_pitch(song.tuned, nt.start, nt.end) - target) < 0.3      # הצליל הגיע לאן שגררו אותו
    assert abs(sung_pitch(song.tuned, other.start, other.end) - other_before) < 0.15   # האחרים לא זזו
    notes = song.pitch_curves(st)[3]
    assert sum(1 for n in notes if n[4]) == 1
    # גם בלי לשמור: הגרף מחשב תיקון לבדיקה, וחוזר לאוטומטי כשמנקים
    assert not any(n[4] for n in song.pitch_curves(st, fixes=[])[3])
    clip = song.hear_fix(st.note_fixes, nt.start, nt.end)
    assert 0.5 * SR < len(clip) < 4 * SR and np.isfinite(clip).all()
    song.make(style("02_piano"), quiet, st0)
    assert abs(sung_pitch(song.tuned, nt.start, nt.end) - auto) < 0.15


def test_note_fixes_survive_project_and_advanced_dialog():
    st = Settings(note_fixes=[[1.25, 64]], lift=1, meter=6)
    back = settings_from_dict(settings_to_dict(st))
    assert back.note_fixes == [[1.25, 64]] and back.lift == 1 and back.meter == 6


# ---------- עליית טון ----------
def test_lift_raises_voice_and_accompaniment_in_last_phrase(song):
    stl = style("02_piano")
    song.make(stl, quiet, Settings(tune=100))
    base_events = [e for _, _, ev in song.last_tracks for e in ev]
    late = [nt for nt in song.analysis.notes if nt.end - nt.start > 0.7][-2]
    early = long_note(song, 0)
    p_late, p_early = sung_pitch(song.tuned, late.start, late.end), sung_pitch(song.tuned, early.start, early.end)
    song.make(stl, quiet, Settings(tune=100, lift=2))
    a = song.analysis
    assert a.lift_t is not None and early.end < a.lift_t < late.start
    assert abs(sung_pitch(song.tuned, late.start, late.end) - p_late - 2) < 0.25
    assert abs(sung_pitch(song.tuned, early.start, early.end) - p_early) < 0.15
    ev = [e for _, _, ev in song.last_tracks for e in ev]
    lead = song.last_lead
    pcs = lambda evs, lo, hi: sorted({int(m) % 12 for t, m, d, v in evs
                                      if not isinstance(m, str) and lo <= t - lead < hi})
    before = pcs(base_events, a.lift_t + 0.5, a.lift_t + 6)
    after = pcs(ev, a.lift_t + 0.5, a.lift_t + 6)
    assert after == sorted({(p + 2) % 12 for p in before})
    assert pcs(ev, 2, a.lift_t - 1) == pcs(base_events, 2, a.lift_t - 1)


# ---------- סולם ומשקל ----------
def test_adonai_malach_mode():
    w = np.zeros(12)
    for step, d in zip(theory.MODES["adonai"][1], [6, 2, 4, 2.5, 5, 2, 4]):       # סול מיקסולידי
        w[(7 + step) % 12] = d
    t, m, _ = theory.rank_keys(w, final_pc=7)[0]
    assert (t, m) == (7, "adonai")
    assert 5 in theory.scale_pcs(7, "adonai") and 6 not in theory.scale_pcs(7, "adonai")   # פה ולא פה#
    names = {c["degree"] for c in theory.chords_for(7, "adonai")}
    assert {"I", "IV", "VII"} <= names


def test_adonai_key_and_six_eight_render(song):
    st = Settings(key=(9, "adonai"), meter=6, tempo_mode="manual", bpm=60)
    y = song.make(style("01_hasidi"), quiet, st)
    a = song.analysis
    assert a.mode == "adonai" and a.compound and a.meter == 2
    assert y.ndim == 2 and np.isfinite(y).all()
    # בתיבה של 6/8 הצלילים נופלים על שלישי הפעמה
    beat = 60 / 60
    frac = []
    for spec, _, ev in song.last_tracks:
        if spec["instrument"] == "drums" and not spec.get("solo"):
            frac += [((t - song.last_lead - a.beats[0]) / beat) % 1 for t, *_ in ev]
    frac = np.array(frac)
    near = lambda f: np.minimum(np.abs(frac - f), 1 - np.abs(frac - f)) < 0.06
    assert len(frac) > 20 and np.mean(near(0) | near(1 / 3) | near(2 / 3)) > 0.9
    assert np.mean(near(0.5)) < 0.05


def test_to_compound_mapping():
    bar = [{"t": 0, "n": "a"}, {"t": 0.5, "n": "x"}, {"t": 1, "n": "b"}, {"t": 1.5, "n": "c"},
           {"t": 2, "n": "d"}, {"t": 3, "n": "e"}, {"t": 3.5, "n": "f"}]
    out = {e["n"]: round(e["t"], 3) for e in arrange.to_compound(bar)}
    assert out == {"a": 0, "b": 0.333, "c": 0.667, "d": 1, "e": 1.333, "f": 1.667}


def test_style_sets_its_meter_and_new_styles_exist(song):
    ids = {s["id"] for s in load_styles()}
    assert {"14_waltz", "15_hora", "16_dveikut", "17_six8"} <= ids
    song.make(style("14_waltz"), quiet, Settings())
    assert song.analysis.meter == 3
    song.make(style("17_six8"), quiet, Settings())
    assert song.analysis.compound
    song.make(style("14_waltz"), quiet, Settings(meter=6))     # בחירה ידנית של המשתמש גוברת
    assert song.analysis.compound
    song.make(style("15_hora"), quiet, Settings())
    assert song.analysis.meter == 4 and not song.analysis.compound


# ---------- מנעד ----------
def test_vocal_range_and_transpose_suggestion(song):
    song.make(style("02_piano"), quiet, Settings())
    lo, hi, mid = analysis.vocal_range(song.analysis)
    assert 67 <= lo <= 70 and 75 <= hi <= 78 and lo < mid < hi
    assert -4 <= analysis.suggest_transpose(song.analysis) < 0      # שירה גבוהה מאוד - מומלץ להוריד
    v = song.info()["voice"]
    assert v["suggest"] < 0 and v["low"] and v["high"]
    low, _ = sing(bpm=120, repeats=1)
    from scipy.signal import resample_poly
    s2 = Song(resample_poly(low, 3, 2).astype(np.float32))          # אותה מנגינה חמישית נמוך יותר
    s2.prepare(quiet)
    assert abs(analysis.suggest_transpose(s2.analysis)) < abs(analysis.suggest_transpose(song.analysis))


# ---------- עריכת משפטים ----------
@pytest.fixture(scope="module")
def two_phrases():
    a, _ = sing(bpm=120, repeats=1, seed=1)
    b, _ = sing(bpm=120, repeats=1, seed=2)
    x = np.concatenate([a, np.zeros(SR, np.float32), b])
    s = Song(x)
    s.prepare(quiet)
    return x, s


def test_phrase_regions(two_phrases):
    x, s = two_phrases
    rg = edit.regions(s.analysis, len(x))
    assert 2 <= len(rg) <= 6
    assert rg[0]["a"] == 0 and abs(rg[-1]["b"] - len(x) / SR) < 1e-6
    for r in rg:
        assert r["a"] <= r["start"] < r["end"] <= r["b"]
    for r1, r2 in zip(rg, rg[1:]):
        assert r1["b"] == r2["a"]                                 # המשפטים מכסים את כל ההקלטה ברצף
        assert r1["end"] <= r1["b"] <= r2["start"]                # החיתוך בתוך ההפסקה
    half = len(x) / SR / 2                                        # השקט הארוך באמצע הוא גבול בין משפטים
    assert any(abs(r["b"] - half) < 1.2 for r in rg[:-1])


def test_replace_duplicate_delete_phrase(two_phrases):
    x, s = two_phrases
    rg = edit.regions(s.analysis, len(x))
    take = np.concatenate([np.zeros(SR // 2, np.float32), 0.1 * sing(bpm=120, repeats=1, seed=5)[0][:8 * SR],
                           np.zeros(SR, np.float32)])
    r = max(rg[1:], key=lambda q: q["end"] - q["start"])          # משפט ארוך שאינו הראשון
    y = edit.replace_phrase(x, r, take)
    assert len(y) == len(x)                                       # האורך נשמר - הקצב לא זז
    i0, i1 = int(r["a"] * SR), int(r["b"] * SR)
    assert np.array_equal(y[:i0], x[:i0]) and np.array_equal(y[i1:], x[i1:])   # שאר המשפטים לא נגעו
    assert not np.allclose(y[i0:i1], x[i0:i1])
    k = min(6 * SR, int((r["end"] - r["start"]) * SR))
    seg = lambda z: z[int(r["start"] * SR):int(r["start"] * SR) + k]
    assert 0.5 < np.sqrt(np.mean(seg(y) ** 2)) / np.sqrt(np.mean(seg(x) ** 2)) < 2   # עוצמה דומה
    d = edit.duplicate_phrase(x, rg[0])
    n0 = int(rg[0]["b"] * SR)
    assert len(d) == len(x) + n0
    assert np.allclose(d[1000:n0 - 1000], d[n0 + 1000:2 * n0 - 1000])
    k = edit.delete_phrase(x, rg[0])
    assert len(k) == len(x) - n0
    t = edit.trim(take)
    assert abs(len(t) / SR - 8) < 0.5


# ---------- דף אקורדים ----------
def test_chord_sheet_data_and_pdf(song, tmp_path):
    from shir_studio import chordsheet
    song.make(style("02_piano"), quiet, Settings(lift=1, transpose=2))
    data = chordsheet.sheet(song, "ניגון שמחה")
    bars = [b for _, part in data["parts"] for b in part]
    assert len(bars) >= 16 and all(1 <= len(b) <= 4 for b in bars)
    assert data["parts"][-1][0].startswith("פזמון") and "חצי טון" in data["parts"][-1][0]
    names = {c for b in bars for c in b if c != "%"}
    assert names and all(c[0] in "ABCDEFG" for c in names)
    assert theory.key_name((song.analysis.tonic + 2) % 12, song.analysis.mode) in data["info"]
    txt = chordsheet.as_text(data)
    assert "ניגון שמחה" in txt and txt.count("|") > 20
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])      # אותו סוג כמו בבדיקות המסכים
    p = str(tmp_path / "sheet.pdf")
    chordsheet.save_pdf(p, data)
    with open(p, "rb") as f:
        head = f.read(5)
    assert head == b"%PDF-" and os.path.getsize(p) > 2000
    with open(p, "rb") as f:
        body = f.read()
    i = body.index(b"/Trapped /False")
    assert body[i:i + 40].split(b"endobj")[0].strip().endswith(b">>")      # מילון הפרטים נסגר כמו שצריך


def test_chord_names():
    from shir_studio.chordsheet import chord_name
    c = analysis.parse_chord("Am7")
    assert chord_name(c) == "Am7" and chord_name(c, 2) == "Bm7"
    assert chord_name(analysis.parse_chord("Fmaj7"), 1) == "F#maj7"


# ---------- עדכון וזמן שנשאר ----------
def test_update_check():
    from shir_studio import update
    assert update.parse_version("גרסה 1.0.42") == (1, 0, 42)
    ok = lambda url, timeout: '{"name": "גרסה 1.0.42", "tag_name": "latest"}'
    assert update.check("1.0.7", fetch=ok)[:2] == ("newer", "1.0.42")
    assert update.check("1.0.42", fetch=ok)[0] == "latest"
    assert update.check("1.0.100", fetch=ok)[0] == "latest"          # השוואת מספרים, לא טקסט

    def offline(url, timeout):
        raise OSError("no network")
    assert update.check("1.0.7", fetch=offline)[0] == "error"
    assert update.check("1.0.7", fetch=lambda u, t: "{}")[0] == "error"
    assert update.check("1.0.7", fetch=ok)[2].startswith("https://github.com/")


def test_long_phrase_is_split_at_a_breath():
    from shir_studio.music.analysis import Note, voice_phrases

    class A:
        notes = ([Note(i * 0.5, i * 0.5 + 0.46, 60) for i in range(20)]            # 10 שניות רצופות
                 + [Note(10.2 + i * 0.5, 10.66 + i * 0.5, 62) for i in range(20)])  # נשימה קצרה, ועוד 10 שניות
    ph = voice_phrases(A)
    assert len(ph) == 2 and abs(ph[0][1] - 9.96) < 1e-6 and abs(ph[1][0] - 10.2) < 1e-6
    A.notes = A.notes[:20]
    assert len(voice_phrases(A)) == 1
