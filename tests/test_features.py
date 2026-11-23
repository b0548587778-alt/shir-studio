"""בדיקות לשדרוגים: חיתוך, הקלטה מחדש של משפט, תיקון ידני, עליית סולם, מחרוזת,
דף אקורדים, טעם אישי, גיבוי אוטומטי ובדיקת גרסה."""
import os
import numpy as np
import pytest

import synth_voice
from synth_voice import sing
from shir_studio.audio import edit, devices
from shir_studio.audio.fileio import SR, AudioError, save, load_stereo
from shir_studio.audio.pitch import yin, hz_to_midi
from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles

NOP = lambda p, m=None: None


def _phrased(repeats=1, rest=3, bpm=120):
    """שירה עם הפסקות (נשימה) בין המשפטים."""
    old = synth_voice.MELODY
    mel = []
    for i in range(0, len(old), 6):
        mel += old[i:i + 6] + [(None, rest)]
    synth_voice.MELODY = mel
    try:
        return sing(bpm=bpm, repeats=repeats)[0]
    finally:
        synth_voice.MELODY = old


@pytest.fixture(scope="module")
def long_song():
    x, _ = sing(bpm=120, repeats=4)
    s = Song(x)
    s.make(load_styles()[1], NOP, Settings())
    return s


def test_trim_removes_silence_only():
    x, _ = sing(bpm=120, repeats=1)
    padded = np.concatenate([0.002 * np.random.default_rng(1).standard_normal(3 * SR).astype(np.float32), x,
                             np.zeros(4 * SR, np.float32)])
    s, e = edit.auto_trim_range(padded)
    assert 2.9 < s < 3.6 and e < len(padded) / SR - 3.0
    y = edit.cut(padded, s, e)
    assert abs(len(y) / SR - (e - s)) < 0.01 and abs(y[0]) < 1e-6 and abs(y[-1]) < 1e-6
    with pytest.raises(AudioError):
        edit.cut(padded, 1.0, 2.0)                       # קטע קצר מדי


def test_phrases_and_replacing_one_phrase():
    x = _phrased()
    slots = edit.phrase_slots(x)
    assert len(slots) == 4
    s, e, lo, hi = slots[1]
    # 'הקלטה חדשה' של המשפט השני: אותה מנגינה חצי טון גבוה יותר, חלשה יותר, עם שקט בהתחלה
    seg = x[int(s * SR):int(e * SR)]
    f, _ = yin(seg)
    from shir_studio.audio.psola import shift
    take = np.concatenate([np.zeros(SR, np.float32), 0.4 * shift(seg, f, np.ones(len(f)))])
    y = edit.splice_take(x, lo, hi, take)
    assert len(y) == len(x)
    a, b = int(lo * SR), int(hi * SR)
    assert np.array_equal(y[:a], x[:a]) and np.array_equal(y[b:], x[b:])      # שאר השיר לא נגע
    f_old, _ = yin(x[int(s * SR):int(e * SR)])
    f_new, _ = yin(y[int(s * SR):int(e * SR)])
    ok = (f_old > 0) & (f_new > 0)
    assert ok.mean() > 0.6                                                   # המשפט החדש יושב באותו מקום
    assert abs(np.median(hz_to_midi(f_new[ok]) - hz_to_midi(f_old[ok])) - 1.0) < 0.2
    r = lambda z: np.sqrt(np.mean(z ** 2))
    assert 0.7 < r(y[a:b]) / r(x[a:b]) < 1.4                                 # אותה עוצמה
    with pytest.raises(AudioError):
        edit.splice_take(x, lo, hi, np.zeros(2 * SR, np.float32))            # הקלטה שקטה


def test_modulation_raises_voice_and_accompaniment(long_song):
    s = long_song
    st = load_styles()[1]
    y = s.make(st, NOP, Settings(modulate=True))
    a = s.analysis
    assert a.modulate_at is not None and a.modulate_voice <= a.modulate_at + 0.5
    assert a.modulate_at > 0.5 * a.duration                    # רק בסוף השיר
    assert np.isfinite(y).all()
    up, mod_at, mod_voice = s.tuned, a.modulate_at, a.modulate_voice
    s.make(st, NOP, Settings())
    assert s.analysis.modulate_at is None
    f1, _ = yin(up)
    f0, _ = yin(s.tuned)
    k = int(mod_voice / 0.01)
    ok = (f1 > 0) & (f0 > 0)
    d = hz_to_midi(np.where(ok, f1, 1)) - hz_to_midi(np.where(ok, f0, 1))
    assert abs(np.median(d[:k][ok[:k]])) < 0.05                 # לפני העלייה - בלי שינוי
    assert abs(np.median(d[k:][ok[k:]]) - 1.0) < 0.1            # אחריה - חצי טון למעלה
    # הליווי: התווים שאחרי רגע העלייה גבוהים בחצי טון
    s.make(st, NOP, Settings(modulate=True))
    hi = [(t, m) for spec, _, ev in s.last_tracks if spec["instrument"] != "drums" for t, m, _, _ in ev]
    s.make(st, NOP, Settings())
    lo = [(t, m) for spec, _, ev in s.last_tracks if spec["instrument"] != "drums" for t, m, _, _ in ev]
    assert len(hi) == len(lo)
    t_mod = mod_at + s.last_lead
    diffs_before = {mh - ml for (t, mh), (_, ml) in zip(hi, lo) if t < t_mod - 0.2}
    diffs_after = {mh - ml for (t, mh), (_, ml) in zip(hi, lo) if t > t_mod + 0.2}
    assert diffs_before == {0} and diffs_after == {1}


def test_short_song_does_not_modulate():
    x, _ = sing(bpm=120, repeats=1)
    s = Song(x)
    s.make(load_styles()[1], NOP, Settings(modulate=True))
    assert s.analysis.modulate_at is None


def test_manual_note_edits(long_song):
    s = long_song
    st = load_styles()[1]
    s.make(st, NOP, Settings())
    _, _, _, notes = s.pitch_curves(Settings())
    base = hz_to_midi(np.maximum(yin(s.tuned)[0], 1))
    long_notes = [n for n in notes if n[1] - n[0] > 0.4]
    n1, n2 = long_notes[3], long_notes[6]
    s.make(st, NOP, Settings(note_edits={n1[4]: 2, n2[4]: "off"}))
    m = hz_to_midi(np.maximum(yin(s.tuned)[0], 1))
    i0, i1 = int(n1[0] / 0.01) + 6, int(n1[1] / 0.01) - 6
    assert abs(np.median((m - base)[i0:i1]) - 2.0) < 0.15       # הצליל שנגרר עלה בשני חצאי טונים
    j0, j1 = int(n2[0] / 0.01) + 6, int(n2[1] / 0.01) - 6
    assert np.abs(s.analysis.correction[j0:j1]).max() < 0.05    # הצליל שבוטל - בלי תיקון
    tg = {n[4]: n for n in s.pitch_curves(Settings())[3]}
    assert tg[n1[4]][3] == n1[5] + 2 and tg[n2[4]][3] == n2[2]
    # ההגדרות נשמרות בפרויקט ונטענות
    from shir_studio.project import settings_to_dict, settings_from_dict
    import json
    st2 = settings_from_dict(json.loads(json.dumps(settings_to_dict(Settings(note_edits={n1[4]: 2}, modulate=True)))))
    assert st2.note_edits == {n1[4]: 2} and st2.modulate is True


def test_known_grid_is_kept(long_song):
    """שרו שוב על הליווי: הקצב של השיר הקודם נשאר בדיוק."""
    a = long_song.analysis
    grid = (a.auto["beats"], a.auto["tempo"], a.auto["steady"])
    x, _ = sing(bpm=120, repeats=1, seed=3)
    s = Song(x, grid=grid)
    s.make(load_styles()[1], NOP, Settings())
    assert s.analysis.steady and np.allclose(s.analysis.beats, grid[0]) and s.analysis.tempo == grid[1]


def test_medley(tmp_path):
    from shir_studio.medley import join, make_medley
    t = np.arange(4 * SR) / SR
    a = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    b = np.stack([0.05 * np.sin(2 * np.pi * 660 * t)] * 2, axis=1).astype(np.float32)
    out = join([a, b], crossfade=1.0)
    assert out.ndim == 2 and abs(len(out) / SR - 7.0) < 0.6
    r = lambda z: np.sqrt(np.mean(z ** 2))
    assert 0.6 < r(out[:SR]) / r(out[-2 * SR:-SR]) < 1.6          # עוצמה אחידה בין השירים
    assert np.abs(out).max() <= 0.9
    mid = out[int(3.2 * SR):int(3.6 * SR), 0]                      # באמצע המעבר שומעים את שני השירים
    spec = np.abs(np.fft.rfft(mid * np.hanning(len(mid))))
    fr = np.fft.rfftfreq(len(mid), 1 / SR)
    assert spec[np.argmin(abs(fr - 440))] > 0.1 * spec.max() and spec[np.argmin(abs(fr - 660))] > 0.1 * spec.max()
    p1, p2, dst = str(tmp_path / "a.wav"), str(tmp_path / "b.wav"), str(tmp_path / "m.mp3")
    save(p1, a)
    save(p2, b)
    seconds, bad = make_medley([p1, str(tmp_path / "missing.wav"), p2], dst)
    assert bad == [str(tmp_path / "missing.wav")] and abs(seconds - 7.0) < 2.1
    assert load_stereo(dst).shape[1] == 2
    with pytest.raises(AudioError):
        make_medley([str(tmp_path / "missing.wav")], dst)


def test_medley_from_raw_singing(tmp_path):
    from shir_studio.medley import make_medley
    x, _ = sing(bpm=120, repeats=1)
    p = str(tmp_path / "v.wav")
    save(p, x)
    seconds, bad = make_medley([p, p], str(tmp_path / "m.wav"), load_styles()[2], Settings(), process=True)
    assert not bad and seconds > 2 * len(x) / SR - 5


def test_chord_sheet(long_song, tmp_path, qapp):
    from shir_studio import chordsheet
    s = long_song
    st = load_styles()[1]
    s.make(st, NOP, Settings())
    plain = chordsheet.sheet_data(s, "ניגון")
    bars = [b for _, bs in plain["sections"] for b in bs]
    assert len(plain["sections"]) == 4 and len(bars) == 32 and "Am" in bars[0]
    assert "לה מינור" in plain["info"] and "120" in plain["info"]
    s.make(st, NOP, Settings(modulate=True, transpose=2))
    d = chordsheet.sheet_data(s, "ניגון")
    assert "סי מינור" in d["info"]                                   # לה מינור + טון
    assert d["sections"][0][1][0].startswith("Bm")
    assert "עליית סולם" in d["sections"][-1][0] and d["sections"][-1][1][0].startswith("Cm")
    assert "| Bm" in chordsheet.as_text(d)
    path = str(tmp_path / "דף אקורדים.pdf")
    chordsheet.write_pdf(path, d)
    with open(path, "rb") as f:
        assert f.read(5) == b"%PDF-" and os.path.getsize(path) > 1500


def test_personal_defaults(appdata):
    from shir_studio import prefs
    assert prefs.personal_settings(prefs.load()) == Settings()
    mine = Settings(reverb=150, harmony="three", modulate=True, key=(2, "minor"), chords_text="Am", transpose=3)
    prefs.store_personal(prefs.load(), mine, "02_piano", "wav", True)
    p = prefs.load()
    st = prefs.personal_settings(p)
    assert (st.reverb, st.harmony, st.modulate) == (150, "three", True)
    assert st.key is None and st.chords_text == "" and st.transpose == 0     # מה ששייך לשיר אחד לא נשמר
    assert (p["style"], p["fmt"], p["extras"]) == ("02_piano", "wav", True)
    with open(os.path.join(str(appdata), "ShirStudio", "prefs.json"), "w") as f:
        f.write("{ broken")
    assert prefs.personal_settings(prefs.load()) == Settings()               # קובץ פגום לא מפיל את התוכנה


def test_recovery(appdata):
    from shir_studio import recovery
    assert recovery.pending() is None
    x, _ = sing(bpm=120, repeats=1)
    rec = devices.Recorder()
    bk = recovery.RecordingBackup()
    for i in range(0, len(x), 4410):
        rec._chunks.append(x[i:i + 4410])
        if i % 44100 == 0:
            bk.write(rec.drain())
    bk.write(rec.drain())
    assert rec.drain() == []
    bk.close()                                                   # התוכנה 'נסגרה' באמצע ההקלטה
    kind, data = recovery.pending()
    assert kind == "recording" and len(data) == len(x) and np.abs(data - x).max() < 1e-3
    bk.discard()
    assert recovery.pending() is None
    recovery.save_session(x, {"style": "02_piano", "key_index": 1, "settings": {"reverb": 120}})
    kind, raw, meta = recovery.pending()
    assert kind == "session" and np.array_equal(raw, x) and meta["key_index"] == 1
    recovery.save_session(None, {"style": "03_guitar"}, raw_changed=False)   # רק ההגדרות השתנו
    assert recovery.pending()[2]["style"] == "03_guitar" and len(recovery.pending()[1]) == len(x)
    recovery.clear()
    assert recovery.pending() is None


def test_update_check():
    from shir_studio import update
    assert update.parse("גרסה 1.0.57") == (1, 0, 57) and update.parse("latest") is None
    assert update.newer("1.0.57", "1.0.9") and not update.newer("1.0.9", "1.0.9") and not update.newer("x", "1.0.0")
    assert update.latest_version(lambda t: {"name": "גרסה 1.0.57", "tag_name": "latest"}) == "1.0.57"

    def offline(timeout):
        raise OSError("אין אינטרנט")
    assert update.latest_version(offline) is None


def test_overdub_is_aligned_to_playback(fake_sd):
    """משמיעים ומקליטים יחד: ההקלטה שחוזרת מתחילה בדיוק בתחילת ההשמעה (אחרי פיצוי האיחור)."""
    backing = np.zeros(SR, np.float32)
    backing[1000] = 1.0
    od = devices.Overdub(backing)
    od.start()
    stream = fake_sd.streams[-1]
    lat = int(round(sum(stream.latency) * SR))
    played = []
    mic = np.zeros(2 * SR, np.float32)
    mic[1000 + lat] = 1.0                       # הזמר 'עונה' בדיוק על הנקישה, והיא חוזרת באיחור של כרטיס הקול
    for i in range(0, 2 * SR, 512):
        out = np.zeros((512, 2), np.float32)
        stream.callback(mic[i:i + 512].reshape(-1, 1), out, 512, None, None)
        played.append(out.copy())
    rec = od.stop()
    played = np.concatenate(played)
    assert int(np.argmax(played[:, 0])) == 1000 and played[SR + 10:].max() == 0   # אחרי הליווי - שקט
    assert abs(int(np.argmax(rec)) - 1000) <= 1
    assert od.position() >= 2.0 - 0.02
