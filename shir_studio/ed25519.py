"""חתימה דיגיטלית Ed25519 - מימוש עצמי לפי התקן הפתוח RFC 8032 (האלגוריתם נחלת הכלל, בלי פטנטים).
משמש לקוד הרישיון: התוכנה מכילה רק את המפתח הציבורי ויכולה רק *לבדוק* קוד; כדי *ליצור* קוד צריך את
המפתח הסודי, שנמצא רק אצל בעל התוכנה. לכן אי אפשר לזייף קוד גם למי שקורא את כל הקוד של התוכנה."""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A = (y1 - x1) * (y2 - x2) % P
    B = (y1 + x1) * (y2 + x2) % P
    C = 2 * t1 * t2 * D % P
    Dd = 2 * z1 * z2 % P
    E, F, G, H = B - A, Dd - C, Dd + C, B + A
    return E * F % P, G * H % P, F * G % P, E * H % P


def _mul(s, a):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, a)
        a = _add(a, a)
        s >>= 1
    return q


def _xrecover(y):
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P:
        x = x * I % P
    if (x * x - xx) % P:
        raise ValueError("bad point")
    return x


_By = 4 * pow(5, P - 2, P) % P
_Bx = _xrecover(_By)
if _Bx & 1:
    _Bx = P - _Bx
BASE = (_Bx, _By, 1, _Bx * _By % P)


def _enc(pt):
    x, y, z, _t = pt
    zi = pow(z, P - 2, P)
    x, y = x * zi % P, y * zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _dec(b):
    if len(b) != 32:
        raise ValueError("bad length")
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= P:
        raise ValueError("bad point")
    x = _xrecover(y)
    if (x & 1) != sign:
        x = P - x
    return x, y, 1, x * y % P


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _expand(secret):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    a, _prefix = _expand(secret)
    return _enc(_mul(a, BASE))


def sign(secret: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(secret)
    A = _enc(_mul(a, BASE))
    r = _h(prefix + msg) % L
    R = _enc(_mul(r, BASE))
    h = _h(R + A + msg) % L
    return R + ((r + h * a) % L).to_bytes(32, "little")


def verify(public: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        if len(sig) != 64 or len(public) != 32:
            return False
        A, R = _dec(public), _dec(sig[:32])
        s = int.from_bytes(sig[32:], "little")
        if s >= L:
            return False
        h = _h(sig[:32] + public + msg) % L
        return _enc(_mul(s, BASE)) == _enc(_add(R, _mul(h, A)))
    except (ValueError, TypeError):
        return False
