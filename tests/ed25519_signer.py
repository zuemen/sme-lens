"""**僅供測試**的 Ed25519 簽章實作（RFC 8032 §5.1.6）。

為什麼放在 tests/ 而不是 smelens/
---------------------------------
生產程式碼刻意只做驗證、不做簽章、不持有私鑰（見
smelens/trust/ed25519.py 的界線說明）。但測試需要**真的簽過的**憑證才有
意義——用手寫的假 proofValue 測驗證器，只能測到「它會拒絕」，測不到
「它會接受正確的簽章」，而後者才是驗證器的主要職責。

所以簽章能力只存在於測試範圍內，且明確標示為測試工具。任何情況下都不要把
這支模組搬進 smelens/。
"""

from __future__ import annotations

import hashlib

from smelens.trust.ed25519 import _BASE, _L, _P, _point_add, _point_mul

_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def _encode_point(point: tuple[int, int, int, int]) -> bytes:
    x, y, z, _ = point
    inv_z = pow(z, _P - 2, _P)
    x = x * inv_z % _P
    y = y * inv_z % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def public_key(seed: bytes) -> bytes:
    """由 32 位元組種子導出公鑰。"""
    if len(seed) != 32:
        raise ValueError("種子必須是 32 位元組")
    h = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(h[:32], "little")
    scalar &= (1 << 254) - 8  # 清低 3 位、設第 254 位（RFC 8032 的 clamping）
    scalar |= 1 << 254
    return _encode_point(_point_mul(scalar, _BASE))


def sign(seed: bytes, message: bytes) -> bytes:
    """以種子對訊息簽章，回傳 64 位元組簽章。"""
    h = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(h[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    prefix = h[32:]
    pk = public_key(seed)

    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    point_r = _point_mul(r, _BASE)
    encoded_r = _encode_point(point_r)
    k = int.from_bytes(hashlib.sha512(encoded_r + pk + message).digest(), "little") % _L
    s = (r + k * scalar) % _L
    return encoded_r + s.to_bytes(32, "little")


__all__ = ["public_key", "sign", "_point_add", "_D"]
