"""vLEI 角色憑證：把「B 層候選」升級為「A 層可歸戶」。

這一層要解決的，正是本系統最深的限制
------------------------------------
公開登記資料沒有身分證字號，所以自然人董監事只能做成 B 層候選——「陳建宏」
一個姓名掛 411 家公司，程式不敢也不該自動合併。原本的解法是「等銀行拿行內
KYC 的身分證字號來解析」，但那要求銀行把身分資料送進本系統，是導入上最大的
阻力。

vLEI（verifiable LEI，GLEIF 的可驗證法人識別碼框架）給了第三條路：
**企業自己出示一份可驗證憑證，證明「某個人確實在本法人擔任某職務」**。
銀行不必交出任何身分資料，本系統也不必持有任何個資——只驗證一份帶簽章的
憑證，就能把那條關聯從「候選」升為「證據」。

GLEIF 的角色憑證分兩種，本模組對應的是前者：

- **OOR（Official Organizational Role）**：法定／官方職務，例如董事、董事長、
  監察人。正好對應公司登記的董監事欄位。
- ECR（Engagement Context Role）：業務往來中的角色（例如採購聯絡人），
  與歸戶無關，本模組不處理。

升級的判準（三者都要成立，缺一不可）
------------------------------------
1. 憑證本身通過完整驗證（簽章、有效期、信任鏈、未撤銷——見 vc.py）。
2. 憑證聲明的法人，其 LEI 對應的統一編號，與該筆關聯的公司相符。
3. 憑證聲明的職務屬於 OOR，且姓名與該筆 B 層關聯的姓名相符。

第 2 點的 LEI ↔ 統一編號對照是刻意外部注入的：那份對照表在真實世界由 GLEIF
的 LOU（本地營運單位）維護，不是本系統能自己編出來的。沒有對照就不升級，
不猜。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from smelens.credit.group import Affiliation, normalise_name
from smelens.trust.vc import TrustAnchor, verify_presentation

#: 屬於 OOR（法定職務）的職稱。只有這些能作為歸戶依據——業務往來角色不算。
OOR_ROLES = frozenset(
    {"董事", "董事長", "監察人", "獨立董事", "常務董事", "執行業務股東", "代表人"}
)

#: 憑證型別：GLEIF 的 OOR 憑證在本模組裡以此型別表示。
OOR_CREDENTIAL_TYPE = "LegalEntityOfficialOrganizationalRolevLEICredential"


@dataclass(frozen=True)
class RolePromotion:
    """一筆成功升級的紀錄——這是要交給授信人員看的來源說明。"""

    company: str
    person: str
    role: str
    lei: str
    company_id: str
    #: 簽發這份憑證的 DID
    issuer: str
    #: 簽發者回溯到信任根的授權鏈
    issuer_chain: list[str]
    credential_id: str


def _subject_fields(credential: dict[str, Any]) -> tuple[str, str, str, str]:
    """取出 (LEI, 姓名, 職稱, 憑證 id)；缺漏時回空字串，由呼叫端判定。"""
    subject = credential.get("credentialSubject") or {}
    role_claim = subject.get("officialRole") or subject.get("role") or {}
    if isinstance(role_claim, str):
        role_name = role_claim
    else:
        role_name = role_claim.get("roleName") or role_claim.get("name") or ""
    return (
        str(subject.get("lei") or subject.get("LEI") or ""),
        str(subject.get("personName") or subject.get("name") or ""),
        str(role_name),
        str(credential.get("id") or ""),
    )


def promote_affiliations(
    affiliations: list[Affiliation],
    presentation: dict[str, Any],
    anchor: TrustAnchor,
    lei_to_company_id: dict[str, str],
    *,
    now: datetime | None = None,
    revoked_ids: set[str] | None = None,
) -> tuple[list[Affiliation], list[RolePromotion], list[str]]:
    """以可驗證展示裡的 OOR 憑證，把符合的 B 層關聯升級為 A 層。

    回傳 (升級後的關聯清單, 升級紀錄, 被拒原因)。

    **只升級、不新增**：憑證不會讓一條原本不存在的關聯冒出來。這是刻意的
    ——本系統的關聯一律來自公開登記資料，憑證的作用是把「可能是同一人」
    確認為「就是這個人」，而不是憑一份憑證就在圖上多畫一條邊。否則任何人
    簽一份憑證就能影響歸戶結果，信任模型會反過來被憑證持有者操縱。
    """
    accepted, results = verify_presentation(
        presentation, anchor, now=now, revoked_ids=revoked_ids
    )
    rejected = [
        f"憑證 {i + 1}：{'；'.join(r.reasons)}" for i, r in enumerate(results) if not r.valid
    ]
    valid_results = [r for r in results if r.valid]
    chain_by_id = {
        str(c.get("id") or ""): r.issuer_chain
        for c, r in zip(accepted, valid_results)
    }

    # 建立 (公司統編, 姓名) → 憑證 的索引，之後逐筆關聯比對
    claims: dict[tuple[str, str], tuple[dict[str, Any], str, str, str]] = {}
    for credential in accepted:
        types = credential.get("type") or []
        if OOR_CREDENTIAL_TYPE not in types:
            rejected.append(f"憑證 {credential.get('id')}：不是 OOR 角色憑證，不作歸戶依據")
            continue
        lei, person, role, credential_id = _subject_fields(credential)
        if role not in OOR_ROLES:
            rejected.append(f"憑證 {credential_id}：職稱「{role}」不屬於法定職務")
            continue
        company_id = lei_to_company_id.get(lei)
        if not company_id:
            rejected.append(f"憑證 {credential_id}：LEI {lei} 查不到對應統一編號")
            continue
        if not person:
            rejected.append(f"憑證 {credential_id}：缺少姓名")
            continue
        claims[(company_id, normalise_name(person))] = (credential, lei, role, credential_id)

    promotions: list[RolePromotion] = []
    upgraded: list[Affiliation] = []
    for item in affiliations:
        key = (item.company_id or "", normalise_name(item.person))
        claim = claims.get(key)
        if item.tier == "B" and claim is not None:
            credential, lei, role, credential_id = claim
            upgraded.append(
                replace(
                    item,
                    tier="A",
                    merge=True,
                    role=f"{item.role}（vLEI 已驗證）",
                )
            )
            promotions.append(
                RolePromotion(
                    company=item.company,
                    person=item.person,
                    role=role,
                    lei=lei,
                    company_id=item.company_id or "",
                    issuer=str(credential.get("issuer") or ""),
                    issuer_chain=chain_by_id.get(credential_id, []),
                    credential_id=credential_id,
                )
            )
        else:
            upgraded.append(item)

    return upgraded, promotions, rejected
