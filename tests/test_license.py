"""גרסת הניסיון וקוד הרישיון."""
import datetime
import pytest

from shir_studio import ed25519, license as lic

SECRET = bytes(range(32))                         # מפתח לבדיקות בלבד
PUBLIC = ed25519.public_key(SECRET).hex()


@pytest.fixture
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(lic, "_paths", lambda: [str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    monkeypatch.setattr(lic, "PUBLIC_KEY_HEX", PUBLIC)
    return tmp_path


def test_signature_matches_the_standard():
    sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert ed25519.public_key(sk).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert ed25519.sign(sk, b"").hex().startswith("e5564300c360ac729086e2cc806e828a")


def test_code_round_trip_and_forgery(clean):
    code = lic.make_code(SECRET, "משה כהן", datetime.date(2026, 12, 1))
    assert code.startswith("SHIR-")
    info = lic.read_code(code)
    assert info == {"name": "משה כהן", "date": "2026-12-01"}
    assert lic.read_code(code.lower().replace("-", " "))["name"] == "משה כהן"     # הקלדה באותיות קטנות וברווחים
    for bad in (code[:-3], code[:20] + ("A" if code[20] != "A" else "B") + code[21:], "SHIR-AAAAA", ""):
        with pytest.raises(lic.LicenseError):
            lic.read_code(bad)
    other = lic.make_code(bytes(range(1, 33)), "משה כהן")                          # נחתם במפתח אחר = זיוף
    with pytest.raises(lic.LicenseError):
        lic.read_code(other)


def test_no_public_key_means_trial_only(clean, monkeypatch):
    monkeypatch.setattr(lic, "PUBLIC_KEY_HEX", "")
    with pytest.raises(lic.LicenseError):
        lic.read_code(lic.make_code(SECRET, "א"))


def test_trial_counts_down_and_license_opens(clean):
    assert lic.status() == {"licensed": False, "name": None, "used": 0, "left": lic.TRIAL_SONGS}
    for _ in range(lic.TRIAL_SONGS):
        assert lic.can_save()
        lic.count_song()
    assert not lic.can_save() and lic.status()["left"] == 0
    (clean / "a.json").unlink()                                   # מחיקת קובץ אחד לא מאפסת את הניסיון
    assert not lic.can_save()
    (clean / "b.json").write_text('{"d": {"used": 0, "code": null}, "s": "0000"}', encoding="utf-8")
    assert lic.status()["left"] == lic.TRIAL_SONGS                # שני הקבצים נמחקו/שונו - מתחילים מחדש (ידוע)
    lic.count_song(lic.TRIAL_SONGS)
    assert lic.activate(lic.make_code(SECRET, "לקוח")) == "לקוח"
    assert lic.can_save() and lic.status()["licensed"] and lic.status()["name"] == "לקוח"
    lic.count_song()
    assert lic.status()["used"] == lic.TRIAL_SONGS                # ברישיון מלא לא סופרים
