"""Ed25519 簽章驗證（RFC 8032），純 Python 實作。

為什麼要自己實作
----------------
本專案的執行環境沒有任何密碼學套件（cryptography／pynacl／ecdsa 皆未安裝），
且不得安裝新套件。可驗證憑證（VC）的核心就是簽章驗證——沒有它，整個信任層
只是形狀對的 JSON，等於假的。與其放一個永遠回 True 的樁，不如把 RFC 8032
的驗證流程實作出來：它只需要 SHA-512（hashlib 有）與模運算。

**這是刻意的權衡，界線要說清楚：**

- 本模組**只做驗證，不做簽章、不持有私鑰**。攻擊面因此小得多——沒有秘密
  可以從旁通道洩漏。
- 純 Python 的實作**沒有常數時間保證**。對「驗證公開憑證」這件事不構成問題
  （輸入與公鑰都是公開資料，沒有需要保密的祕密值），但若日後要用來簽章或
  處理私鑰，**必須**改用 `cryptography` 或 `pynacl` 的原生實作。
- 生產環境的正解是安裝經審計的套件。本模組的存在理由是「在不能裝套件的
  環境裡，把驗證做真的」，不是主張自己寫的密碼學比別人好。

實作依 RFC 8032 §5.1.7 的驗證步驟：
    1. 解出 R（簽章前 32 位元組）與 s（後 32 位元組，小端序整數）
    2. s 必須小於群階 L，否則拒絕（擋可塑性）
    3. k = SHA-512(R ‖ A ‖ M) mod L
    4. 檢查 [s]B = R + [k]A
"""

from __future__ import annotations

import hashlib

#: 體的質數 2^255 − 19
_P = 2**255 - 19

#: 基點的階（RFC 8032 的 L）
_L = 2**252 + 27742317777372353535851937790883648493

#: 曲線參數 d = −121665 / 121666 (mod p)
_D = (-121665 * pow(121666, _P - 2, _P)) % _P

#: 用於開平方：p ≡ 5 (mod 8)，故 sqrt(−1) = 2^((p−1)/4)
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


# 擴展坐標 (X, Y, Z, T)，滿足 x = X/Z、y = Y/Z、x·y = T/Z。
# 用擴展坐標是為了讓點加法不必每次做模逆元——模逆元是這裡最貴的運算。


def _recover_x(y: int, sign: int) -> int | None:
    """由 y 與 x 的符號位還原 x；不在曲線上時回傳 None。"""
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if x * x % _P != x2:
        x = x * _SQRT_M1 % _P
    if x * x % _P != x2:
        return None  # 不是二次剩餘 → 這個 y 不對應曲線上的點
    if x % 2 != sign:
        x = _P - x
    return x


#: 基點 B：y = 4/5 (mod p)，x 取符號位 0 的那一根（RFC 8032 §5.1）。
_BY = 4 * _inv(5) % _P
_BX = _recover_x(_BY, 0)
assert _BX is not None, "基點推導失敗——曲線參數有誤"
_BASE = (_BX, _BY, 1, _BX * _BY % _P)


def _point_add(p: tuple[int, int, int, int], q: tuple[int, int, int, int]):
    """扭曲愛德華曲線的加法（RFC 8032 §5.1.4 的 add-2008-hwcd-3）。"""
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    dd = 2 * z1 * z2 % _P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _point_mul(scalar: int, point: tuple[int, int, int, int]):
    """純量乘法（double-and-add）。"""
    result = (0, 1, 1, 0)  # 單位元
    while scalar > 0:
        if scalar & 1:
            result = _point_add(result, point)
        point = _point_add(point, point)
        scalar >>= 1
    return result


def _point_equal(p: tuple[int, int, int, int], q: tuple[int, int, int, int]) -> bool:
    """在擴展坐標下比較兩點（需交叉相乘，不能直接比 X、Y）。"""
    x1, y1, z1, _ = p
    x2, y2, z2, _ = q
    if (x1 * z2 - x2 * z1) % _P != 0:
        return False
    return (y1 * z2 - y2 * z1) % _P == 0


def _decode_point(data: bytes) -> tuple[int, int, int, int] | None:
    """解壓 32 位元組的點編碼。"""
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign = (y >> 255) & 1
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """驗證 Ed25519 簽章。任何格式或數學上的不合法都回傳 False，不丟例外。

    不丟例外是刻意的：呼叫端拿到的憑證來自外部，格式錯誤是預期情形而非程式
    錯誤；用回傳值表達「這份憑證不可信」比讓呼叫端到處包 try 更不容易漏接。
    """
    if len(signature) != 64 or len(public_key) != 32:
        return False

    point_a = _decode_point(public_key)
    if point_a is None:
        return False
    point_r = _decode_point(signature[:32])
    if point_r is None:
        return False

    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False  # 擋簽章可塑性：s 必須落在 [0, L)

    digest = hashlib.sha512(signature[:32] + public_key + message).digest()
    k = int.from_bytes(digest, "little") % _L

    # 檢查 [s]B = R + [k]A
    left = _point_mul(s, _BASE)
    right = _point_add(point_r, _point_mul(k, point_a))
    return _point_equal(left, right)
