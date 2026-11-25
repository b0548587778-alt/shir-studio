"""גרסת הניסיון והרישיון (רישיונות SuperSuite)."""
import json
import os

import pytest

from shir_studio import ed25519, license as lic

ROOT_SEED = bytes(range(32))                      # מפתח שורש לבדיקות בלבד
ROOT_X = lic.b64u(ed25519.public_key(ROOT_SEED))
DAY = lic.DAY_MS
NOW = 1_800_000_000_000


@pytest.fixture
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(lic, "_paths", lambda: [str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    monkeypatch.setattr(lic, "ROOT_KEYS", [ROOT_X])
    monkeypatch.setattr(lic.time, "time", lambda: NOW / 1000)
    return tmp_path


def issue(request_text, features=("shir-studio",), days=365, issued=NOW, root=ROOT_SEED, name=None):
    """מה שמסך הרישוי של SuperSuite עושה: פותח בקשה ומנפיק רישיון חתום במפתח השורש."""
    req = json.loads(request_text)
    payload = {"v": 1, "id": req["keyId"], "parentId": None, "depth": 1, "slot": 1, "name": name or req["name"],
               "publicKey": req["publicKey"], "features": sorted(features),
               "limits": {"maxChildren": 0, "maxUsers": 1, "maxStorageMb": 0, "maxDepth": 1},
               "issuedAt": issued, "expiresAt": issued + days * DAY, "graceDays": 7}
    return json.dumps({"type": "supersuite-license", "v": 1, "notices": [],
                       "chain": [{"payload": payload, "sig": lic.sign_object(payload, root)}]}, ensure_ascii=False)


def test_signature_matches_the_standard():
    sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert ed25519.public_key(sk).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert ed25519.sign(sk, b"").hex().startswith("e5564300c360ac729086e2cc806e828a")


def test_license_made_by_supersuite_code_is_accepted():
    """רישיון שנוצר בקוד של SuperSuite עצמו (shell/licensing/license.js) - אותה חתימה, אותו קידוד."""
    fx = json.load(open(os.path.join(os.path.dirname(__file__), "supersuite_license_fixture.json"), encoding="utf-8"))
    pub = ed25519.public_key(bytes.fromhex(fx["nodeSeedHex"]))
    assert lic.key_id(pub) == fx["nodeKeyId"]
    p = lic.read_license(json.dumps(fx["package"], ensure_ascii=False), pub, [fx["rootX"]])
    assert p["name"] == 'משה "כהן" 1' and "shir-studio" in p["features"]
    fx["package"]["chain"][0]["payload"]["expiresAt"] += 1          # שינוי קטן בתוכן = החתימה נפסלת
    with pytest.raises(lic.LicenseError):
        lic.read_license(fx["package"], pub, [fx["rootX"]])


def test_request_and_activation(clean):
    req = json.loads(lic.request("  משה כהן "))
    assert req["type"] == "supersuite-license-request" and req["name"] == "משה כהן"
    assert req["keyId"] == lic.key_id(lic.b64u_decode(req["publicKey"]["x"]))
    assert json.loads(lic.request("שם אחר"))["publicKey"] == req["publicKey"]       # אותו מחשב - אותו מפתח
    with pytest.raises(lic.LicenseError):
        lic.request("   ")
    p = lic.activate(issue(json.dumps(req)))
    assert p["name"] == "משה כהן"
    s = lic.status()
    assert s["licensed"] and s["state"] == "active" and s["until"] == NOW + 365 * DAY and lic.can_save()


def test_wrong_licenses_are_refused(clean):
    req = lic.request("לקוח")
    for bad in ("", "{}", "not json", issue(req, features=("econ",)),                 # בלי התחום של שיר סטודיו
                issue(req, root=bytes(range(1, 33))),                                 # נחתם במפתח אחר = זיוף
                issue(req, issued=NOW - 800 * DAY)):                                  # כבר פג
        with pytest.raises(lic.LicenseError):
            lic.activate(bad)
    other = json.loads(req)
    pub = ed25519.public_key(bytes(range(5, 37)))
    other["publicKey"]["x"], other["keyId"] = lic.b64u(pub), lic.key_id(pub)
    with pytest.raises(lic.LicenseError) as e:
        lic.activate(issue(json.dumps(other)))                                        # הונפק למחשב אחר
    assert "מחשב אחר" in str(e.value)
    assert not lic.status()["licensed"]


def test_no_root_key_means_trial_only(clean, monkeypatch):
    req = lic.request("א")
    monkeypatch.setattr(lic, "ROOT_KEYS", [])
    with pytest.raises(lic.LicenseError):
        lic.activate(issue(req))


def test_subscription_expires_with_grace_and_clock_guard(clean, monkeypatch):
    lic.activate(issue(lic.request("מנוי"), days=365))
    at = lambda ms: monkeypatch.setattr(lic.time, "time", lambda: ms / 1000)
    at(NOW + 366 * DAY)
    assert lic.status()["state"] == "grace" and lic.can_save()                        # שבוע של חסד
    at(NOW + 380 * DAY)
    s = lic.status()
    assert s["state"] == "expired" and not s["licensed"]
    at(NOW + 10 * DAY)                                                                # מחזירים את השעון אחורה
    assert lic.status()["state"] == "expired"                                         # ...וזה לא עוזר


def test_trial_counts_down_and_license_opens(clean):
    s = lic.status()
    assert (s["licensed"], s["state"], s["used"], s["left"]) == (False, "trial", 0, lic.TRIAL_SONGS)
    for _ in range(lic.TRIAL_SONGS):
        assert lic.can_save()
        lic.count_song()
    assert not lic.can_save() and lic.status()["left"] == 0
    (clean / "a.json").unlink()                                   # מחיקת קובץ אחד לא מאפסת את הניסיון
    assert not lic.can_save()
    lic.activate(issue(lic.request("לקוח")))
    assert lic.can_save() and lic.status()["name"] == "לקוח"
    lic.count_song()
    assert lic.status()["used"] == lic.TRIAL_SONGS                # ברישיון בתוקף לא סופרים
