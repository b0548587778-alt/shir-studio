"""פרטי השיר בתוך קובץ ה-MP3 (תגיות ID3): שם השיר ושם הזמר - כך הם מופיעים בנגן, ברכב ובטלפון."""
import struct

FRAMES = {"title": "TIT2", "artist": "TPE1", "album": "TALB", "year": "TYER", "genre": "TCON",
          "software": "TSSE"}


def _syncsafe(n):
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def id3(tags):
    """כותרת ID3v2.3 לקובץ MP3. הטקסט ב-UTF-16 - עברית מוצגת נכון בכל נגן."""
    body = b""
    for key, fid in FRAMES.items():
        val = str((tags or {}).get(key) or "").strip()
        if not val:
            continue
        data = b"\x01" + val.encode("utf-16")               # 01 = UTF-16 עם סימן סדר בתים
        body += fid.encode("ascii") + struct.pack(">I", len(data)) + b"\x00\x00" + data
    if not body:
        return b""
    return b"ID3\x03\x00\x00" + _syncsafe(len(body)) + body


def read(path):
    """קורא את התגיות שנכתבו (לבדיקות, ולהצגת שם השיר)."""
    out = {}
    with open(path, "rb") as f:
        head = f.read(10)
        if len(head) < 10 or head[:3] != b"ID3":
            return out
        size = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
        body = f.read(size)
    names = {v: k for k, v in FRAMES.items()}
    i = 0
    while i + 10 <= len(body):
        fid = body[i:i + 4].decode("ascii", "replace")
        n = struct.unpack(">I", body[i + 4:i + 8])[0]
        data = body[i + 10:i + 10 + n]
        i += 10 + n
        if fid in names and data:
            enc = "utf-16" if data[0] == 1 else "latin-1"
            out[names[fid]] = data[1:].decode(enc, "replace").rstrip("\x00")
        if n == 0:
            break
    return out
