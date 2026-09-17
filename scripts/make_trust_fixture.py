"""產生前端示範用的可驗證憑證組合（真的簽過的）。

為什麼要腳本產生而不是手寫 JSON
------------------------------
憑證的 proofValue 是對規範化後內容的 Ed25519 簽章。手寫一份假的十六進位字串，
前端按下去只會看到「簽章驗證失敗」——示範就毀了。而且簽章無法手算，必須由
程式產生。

本腳本輸出 web/src/api/trust-fixture.json，內容包含：
- 三層信任模型的 DID（GLEIF 根 → QVI → 法人）與授權表
- 兩份真的簽過的 OOR 角色憑證（對應一詮與世銓）
- 一份刻意無效的憑證（自簽、回溯不到信任根），用來示範「會被擋下來」
- LEI 對統一編號的對照、撤銷清單與鏈上錨定參照

用法（repo 根目錄）：
    PYTHONIOENCODING=utf-8 PYTHONPATH=. ./.venv/Scripts/python.exe \
        scripts/make_trust_fixture.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smelens.trust.did import encode_ed25519_did  # noqa: E402
from smelens.trust.vc import canonicalise  # noqa: E402
from smelens.trust.vlei import OOR_CREDENTIAL_TYPE  # noqa: E402
from tests.ed25519_signer import public_key, sign  # noqa: E402

OUT = Path("web/src/api/trust-fixture.json")

#: 示範用的固定種子。這是**示範資料**，不是任何真實金鑰——真實的 vLEI 簽發者
#: 是 GLEIF 認證的 QVI，私鑰在他們的硬體裡，永遠不會出現在任何 repo。
_SEEDS = {
    "gleif": bytes([11]) * 32,
    "qvi": bytes([22]) * 32,
    "entity_yichuan": bytes([33]) * 32,
    "rogue": bytes([99]) * 32,
}

LEI_YICHUAN = "5493001KJTIIGC8Y1R12"
LEI_SHIQUAN = "5493001KJTIIGC8Y1R34"
COMPANY_YICHUAN = "35866232"
COMPANY_SHIQUAN = "54318252"


def issue(
    *,
    seed: bytes,
    issuer: str,
    credential_id: str,
    lei: str,
    person: str,
    role: str,
    valid_days: int = 365,
) -> dict:
    now = datetime.now(UTC)
    credential = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "id": credential_id,
        "type": ["VerifiableCredential", OOR_CREDENTIAL_TYPE],
        "issuer": issuer,
        "validFrom": (now - timedelta(days=1)).isoformat(),
        "validUntil": (now + timedelta(days=valid_days)).isoformat(),
        "credentialSubject": {
            "lei": lei,
            "personName": person,
            "officialRole": {"roleName": role},
        },
    }
    credential["proof"] = {
        "type": "DataIntegrityProof",
        "verificationMethod": issuer,
        "proofValue": sign(seed, canonicalise(credential)).hex(),
    }
    return credential


def main() -> int:
    dids = {name: encode_ed25519_did(public_key(seed)) for name, seed in _SEEDS.items()}

    valid_a = issue(
        seed=_SEEDS["entity_yichuan"],
        issuer=dids["entity_yichuan"],
        credential_id="urn:vc:oor:yichuan-wang",
        lei=LEI_YICHUAN,
        person="王小明",
        role="董事",
    )
    valid_b = issue(
        seed=_SEEDS["entity_yichuan"],
        issuer=dids["entity_yichuan"],
        credential_id="urn:vc:oor:shiquan-wang",
        lei=LEI_SHIQUAN,
        person="王小明",
        role="董事",
    )
    # 刻意無效：自簽，回溯不到 GLEIF 根。示範「簽章有效但簽發者不可信」也會被擋。
    rogue = issue(
        seed=_SEEDS["rogue"],
        issuer=dids["rogue"],
        credential_id="urn:vc:oor:rogue",
        lei=LEI_YICHUAN,
        person="李大華",
        role="董事",
    )

    fixture = {
        "trust_root": dids["gleif"],
        "authorised_by": {
            dids["gleif"]: dids["gleif"],
            dids["qvi"]: dids["gleif"],
            dids["entity_yichuan"]: dids["qvi"],
        },
        "lei_to_company_id": {
            LEI_YICHUAN: COMPANY_YICHUAN,
            LEI_SHIQUAN: COMPANY_SHIQUAN,
        },
        "revoked_credential_ids": [
            "urn:vc:oor:resigned-director-2025",
            "urn:vc:oor:leaked-key-2026",
        ],
        "anchor_reference": "",
        "affiliations": [
            {
                "company": "一詮精密工業股份有限公司",
                "person": "王小明",
                "role": "董事",
                "company_id": COMPANY_YICHUAN,
                "tier": "B",
                "merge": False,
            },
            {
                "company": "世銓科技股份有限公司",
                "person": "王小明",
                "role": "董事",
                "company_id": COMPANY_SHIQUAN,
                "tier": "B",
                "merge": False,
            },
        ],
        "presentation": {
            "@context": ["https://www.w3.org/ns/credentials/v2"],
            "type": ["VerifiablePresentation"],
            "verifiableCredential": [valid_a, valid_b, rogue],
        },
        "_note": (
            "示範資料。憑證的簽章由 scripts/make_trust_fixture.py 以固定種子真實產生，"
            "可被 /trust/verify 驗證通過；rogue 那份刻意回溯不到信任根，用來示範會被擋下。"
            "真實的 vLEI 由 GLEIF 認證的 QVI 簽發，私鑰不會出現在任何 repo。"
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已產生 {OUT}")
    print(f"  信任根 {dids['gleif'][:32]}…")
    print("  憑證 3 份（2 份有效、1 份刻意無效）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
