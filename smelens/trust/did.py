"""`did:key` 解析：從 DID 字串本身取出 Ed25519 公鑰。

為什麼從 did:key 起手
---------------------
可驗證憑證要驗簽，得先知道簽發者的公鑰。一般的 DID 方法（did:web、did:ion、
KERI 的 AID）需要對外查詢或維護見證人網路；`did:key` 把公鑰直接編進識別碼裡，
**離線就能解析**——這對「會場沒網路也要能演示」的需求正好（見
docs/DEMO_SCRIPT.md 的全離線程序），也讓驗證流程不必信任任何解析服務。

格式：`did:key:z<multibase-base58btc(<multicodec><公鑰位元組>)>`
Ed25519 的 multicodec 前綴是 0xED 0x01。

界線
----
本模組只支援 did:key 的 Ed25519。行內要接真正的 vLEI 時，簽發者是 GLEIF 的
QVI，識別碼是 KERI 的 AID（did:keri），需要另外實作 KEL（金鑰事件日誌）的
重播驗證——那是可插拔的下一步，不是本模組假裝已經做到的事。
"""

from __future__ import annotations

#: base58btc（比特幣字母表）：刻意不含 0、O、I、l，避免肉眼混淆。
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {char: i for i, char in enumerate(_ALPHABET)}

#: multicodec：Ed25519 公鑰的前綴（varint 0xED01）
_ED25519_PREFIX = b"\xed\x01"

DID_KEY_PREFIX = "did:key:z"


def base58btc_decode(text: str) -> bytes | None:
    """base58btc 解碼；含非字母表字元時回傳 None。"""
    value = 0
    for char in text:
        digit = _INDEX.get(char)
        if digit is None:
            return None
        value = value * 58 + digit
    # 前導的 '1' 在 base58btc 代表前導的 0x00 位元組，必須各自還原
    leading_zeros = len(text) - len(text.lstrip("1"))
    body = value.to_bytes((value.bit_length() + 7) // 8, "big") if value else b""
    return b"\x00" * leading_zeros + body


def resolve_ed25519_public_key(did: str) -> bytes | None:
    """從 did:key 取出 32 位元組 Ed25519 公鑰；不是合法的 Ed25519 did:key 時回 None。"""
    if not did.startswith(DID_KEY_PREFIX):
        return None
    decoded = base58btc_decode(did[len(DID_KEY_PREFIX) :])
    if decoded is None or not decoded.startswith(_ED25519_PREFIX):
        return None
    key = decoded[len(_ED25519_PREFIX) :]
    return key if len(key) == 32 else None


def encode_ed25519_did(public_key: bytes) -> str:
    """把公鑰編成 did:key 字串。測試與示範資料產生時需要，故一併提供。"""
    if len(public_key) != 32:
        raise ValueError("Ed25519 公鑰必須是 32 位元組")
    payload = _ED25519_PREFIX + public_key
    value = int.from_bytes(payload, "big")
    chars = ""
    while value:
        value, remainder = divmod(value, 58)
        chars = _ALPHABET[remainder] + chars
    leading_zeros = len(payload) - len(payload.lstrip(b"\x00"))
    return DID_KEY_PREFIX + "1" * leading_zeros + chars
