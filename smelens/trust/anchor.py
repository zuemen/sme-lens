"""撤銷清單的鏈上錨定：Merkle 樹與包含性證明。

要解決的問題
------------
憑證可以在有效期內被撤銷（董事離任、憑證外洩），所以驗證一定要查撤銷狀態。
但撤銷清單本身是誰在維護？若銀行只信任簽發者自己提供的清單，簽發者就能
**事後悄悄改寫歷史**——把一份當時有效的憑證講成早就撤銷了，或反之。

標準解法是把清單的 Merkle 根雜湊錨定在公開鏈上：根雜湊一旦上鏈就不可改，
任何人都能驗證「某個狀態確實屬於某個時點的清單」，而且不必下載整份清單
——只要一條 log₂(n) 長度的包含性證明。

本模組做什麼、不做什麼
----------------------
**做**：Merkle 根的計算、包含性證明的產生與驗證。這些是真正的密碼學運算，
可獨立驗算。

**不做**：把根雜湊送上區塊鏈。那是一次交易與一個錢包的事，屬於營運步驟，
需要私鑰與金流；本系統刻意不持有私鑰（見 ed25519.py 的界線說明）。因此
`anchor_reference` 是呼叫端填入的外部參照（鏈名、交易雜湊、區塊高度），
本模組只負責「根雜湊對不對」，不聲稱「已經上鏈」。

抗第二原像攻擊
--------------
葉節點與內部節點的雜湊加不同的前綴（0x00 / 0x01）。少了這一步，攻擊者可以
把一個內部節點偽裝成葉節點，構造出兩棵不同的樹卻算出同一個根——這是 Merkle
樹的經典陷阱（CVE-2012-2459 的同類問題）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"


def _leaf_hash(entry: str) -> bytes:
    return hashlib.sha256(_LEAF_PREFIX + entry.encode("utf-8")).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


@dataclass(frozen=True)
class InclusionProof:
    """某一筆項目屬於某個 Merkle 根的證明。

    path 的每一項是 (兄弟節點雜湊, 兄弟是否在左邊)——驗證時要知道左右順序，
    順序錯了算出來的根就不同。
    """

    entry: str
    path: list[tuple[str, bool]]
    root: str


def merkle_root(entries: list[str]) -> str:
    """計算撤銷清單的 Merkle 根（十六進位）。空清單回全零根。

    項目先排序：清單的順序不該影響根雜湊，否則同一份清單換個順序就成了
    另一個根，錨定失去意義。
    """
    if not entries:
        return "00" * 32
    level = [_leaf_hash(e) for e in sorted(set(entries))]
    while len(level) > 1:
        # 奇數個節點時，最後一個與自己配對（標準做法，且已有前綴防第二原像）
        if len(level) % 2:
            level.append(level[-1])
        level = [_node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0].hex()


def build_inclusion_proof(entries: list[str], entry: str) -> InclusionProof | None:
    """為 entry 產生包含性證明；不在清單裡時回 None。"""
    unique = sorted(set(entries))
    if entry not in unique:
        return None
    level = [_leaf_hash(e) for e in unique]
    index = unique.index(entry)
    path: list[tuple[str, bool]] = []
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = index ^ 1
        # 兄弟在左邊時，計算根時要把兄弟放前面
        path.append((level[sibling].hex(), sibling < index))
        level = [_node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        index //= 2
    return InclusionProof(entry=entry, path=path, root=level[0].hex())


def verify_inclusion(proof: InclusionProof) -> bool:
    """驗證包含性證明：沿 path 往上算，看是否得到宣稱的根。"""
    current = _leaf_hash(proof.entry)
    for sibling_hex, sibling_is_left in proof.path:
        try:
            sibling = bytes.fromhex(sibling_hex)
        except ValueError:
            return False
        if len(sibling) != 32:
            return False
        current = (
            _node_hash(sibling, current) if sibling_is_left else _node_hash(current, sibling)
        )
    return current.hex() == proof.root


@dataclass(frozen=True)
class RevocationRegistry:
    """撤銷清單 ＋ 它的 Merkle 根 ＋ 鏈上錨定參照。

    anchor_reference 是外部填入的字串（例如
    "base-sepolia:0x…:區塊 12345678"）。本模組不驗證那筆交易是否真的存在
    ——那需要一個鏈上節點；欄位為空就表示「尚未錨定」，畫面必須照實呈現，
    不得把未錨定的清單講成已上鏈。
    """

    revoked_ids: list[str]
    anchor_reference: str = ""

    @property
    def root(self) -> str:
        return merkle_root(self.revoked_ids)

    @property
    def anchored(self) -> bool:
        return bool(self.anchor_reference)

    def proof_for(self, credential_id: str) -> InclusionProof | None:
        return build_inclusion_proof(self.revoked_ids, credential_id)
