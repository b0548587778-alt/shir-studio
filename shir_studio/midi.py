"""ייצוא קובץ MIDI (פורמט 1) - כדי שמוזיקאים יוכלו להמשיך לערוך בתוכנת מוזיקה."""
import struct

GM_PROGRAM = {"piano": 0, "guitar": 24, "steel_guitar": 25, "bass": 33, "acoustic_bass": 32,
              "strings": 48, "slow_strings": 49, "choir": 52, "choir_oo": 53, "bass_voice": 53,
              "trumpet": 56, "brass": 61, "clarinet": 71, "accordion": 21, "timpani": 47,
              "organ": 16, "flute": 73, "violin": 40}
GM_DRUM = {"kick": 36, "snare": 38, "clap": 39, "hat": 42, "open_hat": 46, "crash": 49,
           "tom_low": 45, "tom_hi": 50,
           "tambourine": 54, "ride": 51}
PPQ = 480


def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def _track(events, name):
    """events: (tick, bytes)."""
    data = b"\x00\xff\x03" + _vlq(len(name.encode())) + name.encode()
    last = 0
    for tick, msg in sorted(events, key=lambda e: (e[0], e[1][0] & 0xF0 != 0x80)):
        data += _vlq(max(0, tick - last)) + msg
        last = max(last, tick)
    data += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + data


def write(path, bpm, melody, tracks, lead):
    """melody: [(start, end, midi)] בזמן השירה. tracks: [(spec, buf, events)] בזמן הליווי."""
    tps = PPQ * bpm / 60.0

    def tk(sec):
        return int(round(sec * tps))
    tempo = int(60_000_000 / bpm)
    head = _track([(0, b"\xff\x51\x03" + tempo.to_bytes(3, "big"))], "Tempo")
    out = [head]
    ev = [(0, bytes([0xC0, 85]))]   # קול השירה: Voice Lead
    for s, e, m in melody:
        m = int(round(m))
        ev += [(tk(s + lead), bytes([0x90, m, 100])), (tk(e + lead), bytes([0x80, m, 0]))]
    out.append(_track(ev, "Melody"))
    ch = 1
    for spec, _, events in tracks:
        inst = spec["instrument"]
        drums = inst == "drums"
        c = 9 if drums else ch
        evs = [] if drums else [(0, bytes([0xC0 | c, GM_PROGRAM.get(inst, 0)]))]
        for t, m, d, v in events:
            key = GM_DRUM.get(m, 38) if drums else int(m)
            vel = max(1, min(127, int(v * 110)))
            evs += [(tk(t), bytes([0x90 | c, key, vel])), (tk(t + d), bytes([0x80 | c, key, 0]))]
        out.append(_track(evs, inst))
        if not drums:
            ch = ch + 1 if ch + 1 != 9 else 10
            ch = min(ch, 15)
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, len(out), PPQ) + b"".join(out))
