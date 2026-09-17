"""可驗證憑證（W3C VC）與可驗證展示（VP）的驗證。

驗證一份憑證要通過五道關，缺任何一道就不算可信：

1. **結構**：型別、簽發者、主體、有效期間欄位齊備。
2. **簽章**：簽發者 DID 解出公鑰，對規範化後的內容驗 Ed25519（見 ed25519.py）。
3. **有效期間**：未到生效時間或已過期都不算。
4. **簽發者信任鏈**：簽發者必須能沿「誰授權誰」的鏈路回溯到信任根
   （vLEI 的模型是 GLEIF 根 → QVI → 法人），不是隨便一個 DID 說了算。
5. **撤銷狀態**：憑證可能在有效期內被撤銷，狀態清單說了才算。

規範化的界線（重要）
--------------------
W3C Data Integrity 的正式做法是 JSON-LD 的 URDNA2015 標準化，需要完整的
JSON-LD 處理器。本模組改用 **RFC 8785（JCS）風格的確定性 JSON 序列化**：
鍵遞迴排序、不留空白、UTF-8。這在「同一套系統簽發與驗證」的情境下是正確且
可重現的，但**與生產環境的 vLEI（KERI／ACDC 或 URDNA2015）不能直接互通**
——要對接真實 GLEIF 憑證，必須換成對應的規範化器。這一點寫在這裡，不在
簡報上假裝已經互通。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from smelens.trust.did import resolve_ed25519_public_key
from smelens.trust.ed25519 import verify as ed25519_verify

#: 憑證的簽章欄位名稱（比照 Data Integrity 的 proof.proofValue）
PROOF_KEY = "proof"


@dataclass(frozen=True)
class TrustAnchor:
    """信任根與被授權的簽發者。

    vLEI 的信任模型是三層：GLEIF 根簽發給合格憑證簽發者（QVI），QVI 再簽發給
    法人。這裡用 {簽發者 DID: 授權者 DID} 表達那條鏈，根的授權者是自己。
    """

    #: 信任根的 DID（GLEIF 根的類比）
    root: str
    #: {簽發者 DID: 由誰授權}。根自己映到自己。
    authorised_by: dict[str, str] = field(default_factory=dict)

    def chain(self, issuer: str, *, max_depth: int = 8) -> list[str] | None:
        """回傳從 issuer 回溯到 root 的授權鏈；回溯不到則 None。

        max_depth 是防呆：授權表若被寫成環（A 授權 B、B 授權 A），沒有上限
        就會無限迴圈。回溯不到根與陷入環都一樣不可信，回 None。
        """
        path = [issuer]
        current = issuer
        for _ in range(max_depth):
            if current == self.root:
                return path
            parent = self.authorised_by.get(current)
            if parent is None or parent in path:
                return None
            path.append(parent)
            current = parent
        return None


@dataclass(frozen=True)
class VerificationResult:
    """驗證結果。失敗時 reasons 逐條列出原因——只回 False 會讓呼叫端無從告知使用者。"""

    valid: bool
    reasons: list[str] = field(default_factory=list)
    #: 通過時，簽發者回溯到信任根的授權鏈
    issuer_chain: list[str] = field(default_factory=list)


def canonicalise(document: dict[str, Any]) -> bytes:
    """RFC 8785（JCS）風格的確定性序列化：鍵遞迴排序、無多餘空白、UTF-8。

    確定性是簽章能重現的前提：同一份文件在不同機器、不同 Python 版本序列化
    出來的位元組必須一致，否則驗簽會隨機失敗。
    """
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def verify_credential(
    credential: dict[str, Any],
    anchor: TrustAnchor,
    *,
    now: datetime | None = None,
    revoked_ids: set[str] | None = None,
) -> VerificationResult:
    """驗證單一份可驗證憑證，逐項回報失敗原因。"""
    reasons: list[str] = []
    now = now or datetime.now(UTC)
    revoked_ids = revoked_ids or set()

    # ── 1. 結構 ─────────────────────────────────────────
    types = credential.get("type")
    if not isinstance(types, list) or "VerifiableCredential" not in types:
        reasons.append("type 必須是陣列且包含 VerifiableCredential")
    issuer = credential.get("issuer")
    if not isinstance(issuer, str) or not issuer:
        reasons.append("缺少 issuer")
    subject = credential.get("credentialSubject")
    if not isinstance(subject, dict) or not subject:
        reasons.append("缺少 credentialSubject")
    proof = credential.get(PROOF_KEY)
    if not isinstance(proof, dict):
        reasons.append("缺少 proof")
    if reasons:
        return VerificationResult(False, reasons)

    # ── 2. 有效期間 ─────────────────────────────────────
    valid_from = _parse_time(credential.get("validFrom") or credential.get("issuanceDate"))
    valid_until = _parse_time(credential.get("validUntil") or credential.get("expirationDate"))
    if valid_from and now < valid_from:
        reasons.append(f"憑證尚未生效（validFrom {valid_from.isoformat()}）")
    if valid_until and now > valid_until:
        reasons.append(f"憑證已過期（validUntil {valid_until.isoformat()}）")

    # ── 3. 撤銷 ─────────────────────────────────────────
    credential_id = credential.get("id")
    if isinstance(credential_id, str) and credential_id in revoked_ids:
        reasons.append(f"憑證已被撤銷（{credential_id}）")

    # ── 4. 簽發者信任鏈 ─────────────────────────────────
    chain = anchor.chain(str(issuer))
    if chain is None:
        reasons.append(f"簽發者無法回溯到信任根：{issuer}")

    # ── 5. 簽章 ─────────────────────────────────────────
    # 驗簽放最後，因為它最貴（純 Python 的純量乘法）；前面任一項不合格就沒必要算。
    proof_value = proof.get("proofValue")
    verification_method = proof.get("verificationMethod") or issuer
    if not isinstance(proof_value, str):
        reasons.append("proof.proofValue 必須是十六進位字串")
    else:
        public_key = resolve_ed25519_public_key(str(verification_method))
        if public_key is None:
            reasons.append(f"無法從 verificationMethod 解出公鑰：{verification_method}")
        else:
            try:
                signature = bytes.fromhex(proof_value)
            except ValueError:
                signature = b""
                reasons.append("proof.proofValue 不是合法的十六進位字串")
            if signature:
                payload = {k: v for k, v in credential.items() if k != PROOF_KEY}
                if not ed25519_verify(public_key, canonicalise(payload), signature):
                    reasons.append("簽章驗證失敗（內容被改動，或不是該簽發者簽的）")

    if reasons:
        return VerificationResult(False, reasons)
    return VerificationResult(True, [], chain or [])


def verify_presentation(
    presentation: dict[str, Any],
    anchor: TrustAnchor,
    *,
    now: datetime | None = None,
    revoked_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[VerificationResult]]:
    """驗證一份可驗證展示，回傳 (通過的憑證清單, 每份憑證的驗證結果)。

    展示裡的憑證**逐份獨立驗證**：一份壞掉不該讓其他份連坐，否則銀行送一批
    憑證進來時，一份過期就全部作廢，實務上不可用。
    """
    raw = presentation.get("verifiableCredential")
    credentials = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    results = [
        verify_credential(c, anchor, now=now, revoked_ids=revoked_ids)
        if isinstance(c, dict)
        else VerificationResult(False, ["憑證不是物件"])
        for c in credentials
    ]
    accepted = [c for c, r in zip(credentials, results) if r.valid]
    return accepted, results
