import os
import numpy as np
from synth_voice import sing
from shir_studio.pipeline import Song, Settings
from shir_studio.music.styles import load_styles
from shir_studio.music.analysis import parse_chords


def test_manual_settings_and_exports(tmp_path):
    x, _ = sing(bpm=110, repeats=1)
    s = Song(x)
    style = load_styles()[0]
    s.make(style, lambda p, m=None: None)
    st = Settings(key=(2, "minor"), tempo_mode="manual", bpm=100, meter=3, transpose=2,
                  chords_text="Dm | Gm A | Dm", accomp_db=3, reverb=50, tune=100)
    out = s.make(style, lambda p, m=None: None, st)
    info = s.info()
    assert info["tonic"] == 2 and info["meter"] == 3 and info["tempo"] == 100
    assert info["chords"].startswith("Dm | Gm A | Dm")
    assert np.isfinite(out).all()
    paths = s.export_extras(str(tmp_path), "song")
    assert len(paths) == 3 and all(os.path.getsize(p) > 100 for p in paths)
    with open(paths[-1], "rb") as f:
        assert f.read(4) == b"MThd"
    s.make(style, lambda p, m=None: None, Settings(tempo_mode="free"))
    assert not s.info()["steady"]


def test_parse_chords():
    ch = parse_chords("Am | F# Bbm | -", [(0, 2), (2, 4), (4, 6)])
    assert [(c["root"], c["quality"]) for _, _, c in ch] == [(9, "min"), (6, "maj"), (10, "min")]
    assert ch[-1][1] == 6
