"""דוח איכות: מריץ את הזמרים המזויפים דרך התוכנה ומודד מה יצא. הרצה:  python tools/quality_report.py
עם --save <תיקייה> נשמרים גם קבצי 'לפני' ו'אחרי' להאזנה."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from singers import CASES, SONGS, sing
from shir_studio.pipeline import Song, Settings
from shir_studio.audio.pitch import yin, hz_to_midi
from shir_studio.music.theory import key_name


def measure(name, style=None, save=None):
    song, kw = CASES[name]
    mel, tonic, mode = SONGS[song]
    x, truth, beats = sing(mel, **kw)
    s = Song(x)
    quiet = lambda *a: None
    s.prepare(quiet)
    st = Settings()
    s._apply(st)
    s._retune(st)
    a = s.analysis
    f0, _ = yin(s.tuned)
    m = np.where(f0 > 0, hz_to_midi(np.where(f0 > 0, f0, 1)), np.nan)
    errs = []
    for t0, mi, err, t1 in truth:
        seg = m[int((t0 + 0.08) * 100): int((t1 - 0.05) * 100)]
        if np.isfinite(seg).sum() > 4:
            errs.append(np.nanmedian(seg) - mi)
    errs = np.array(errs)
    ref = np.round(np.median(errs) * 2) / 2 if abs(np.median(errs)) > 0.75 else np.median(errs)
    e = errs - np.median(errs)                      # ביחס לכיוון שהתוכנה בחרה (הליווי מכוון אליו)
    # הקצב: כמה מתחילות התווים יושבות על הפעמות או על חצאי הפעמות של הליווי
    if a.steady and len(a.beats) > 3:
        grid = np.sort(np.concatenate([a.beats, (a.beats[:-1] + a.beats[1:]) / 2]))
        on = float(np.mean([np.min(np.abs(grid - t0)) < 0.07 for t0, *_ in truth]))
    else:
        on = float("nan")
    # האקורדים: כמה מזמן השירה הצליל הנכון שייך לאקורד (או צליל מעבר סמוך)
    best = None
    for shift in {int(np.floor(np.median(errs))), int(np.ceil(np.median(errs)))}:   # כיוון של 'חצי טון באמצע' - שתי האפשרויות
        fit = tot = 0.0
        for t0, mi, err, t1 in truth:
            for cs, ce, c in a.chords:
                ov = min(t1, ce) - max(t0, cs)
                if ov > 0:
                    tot += ov
                    fit += ov * (((mi + shift) % 12) in c["pcs"])
        ok = a.tonic == (tonic + shift) % 12 and a.mode == mode
        if best is None or (ok, fit) > best[:2]:
            best = (ok, fit, tot, shift)
    key_ok, fit, tot, shift = best
    e = errs - shift
    e = e - np.median(e)
    res = dict(name=name, key=key_name(a.tonic, a.mode), key_ok=key_ok,
               mean=float(np.mean(np.abs(e))), bad=float(np.mean(np.abs(e) > 0.2)), wrong=float(np.mean(np.abs(e) > 0.5)),
               steady=a.steady, tempo=a.tempo, on_grid=on, chord_fit=fit / max(tot, 1e-9))
    if save:
        from shir_studio.audio.fileio import save as wsave
        from shir_studio.music.styles import load_styles
        os.makedirs(save, exist_ok=True)
        stl = [z for z in load_styles() if (style or "symphonic") in z["id"]] or load_styles()
        out = s.make(stl[0], quiet)
        wsave(os.path.join(save, f"{name} - לפני.wav"), x)
        wsave(os.path.join(save, f"{name} - אחרי.wav"), out)
    return res


if __name__ == "__main__":
    save = sys.argv[sys.argv.index("--save") + 1] if "--save" in sys.argv else None
    print(f"{'זמר':<18}{'סולם':<16}{'נכון?':<7}{'סטייה':<8}{'מזויפים':<9}{'תו שגוי':<9}{'קצב':<12}{'על הפעמה':<10}{'אקורדים'}")
    for name in CASES:
        r = measure(name, save=save)
        print(f"{r['name']:<18}{r['key']:<16}{'כן' if r['key_ok'] else 'לא':<7}{r['mean']:<8.2f}{r['bad']*100:<9.0f}"
              f"{r['wrong']*100:<9.0f}{(str(int(r['tempo'])) if r['steady'] else 'חופשי'):<12}{r['on_grid']*100:<10.0f}{r['chord_fit']*100:.0f}")
