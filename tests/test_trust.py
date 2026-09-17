"""可驗證憑證信任層測試：簽章、DID、五道驗證關卡、vLEI 升級、Merkle 錨定。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smelens.credit.group import Affiliation, build_company_graph, detect_groups
from smelens.trust.anchor import (
    RevocationRegistry,
    build_inclusion_proof,
    merkle_root,
    verify_inclusion,
)
from smelens.trust.did import encode_ed25519_did, resolve_ed25519_public_key
from smelens.trust.ed25519 import verify as ed25519_verify
from smelens.trust.vc import TrustAnchor, canonicalise, verify_credential
from smelens.trust.vlei import OOR_CREDENTIAL_TYPE, promote_affiliations
from tests.ed25519_signer import public_key, sign

# ── RFC 8032 §7.1 官方測試向量 ──────────────────────────────
_RFC_VECTORS = [
    (
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc"
        "61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e4"
        "58f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae"
        "67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
]

_GLEIF_SEED = bytes([1]) * 32
_QVI_SEED = bytes([2]) * 32
_ENTITY_SEED = bytes([3]) * 32
_ROGUE_SEED = bytes([9]) * 32

GLEIF_DID = encode_ed25519_did(public_key(_GLEIF_SEED))
QVI_DID = encode_ed25519_did(public_key(_QVI_SEED))
ENTITY_DID = encode_ed25519_did(public_key(_ENTITY_SEED))
ROGUE_DID = encode_ed25519_did(public_key(_ROGUE_SEED))

#: vLEI 的三層信任模型：GLEIF 根 → QVI → 法人
ANCHOR = TrustAnchor(
    root=GLEIF_DID,
    authorised_by={GLEIF_DID: GLEIF_DID, QVI_DID: GLEIF_DID, ENTITY_DID: QVI_DID},
)

LEI = "5493001KJTIIGC8Y1R12"
COMPANY_ID = "35866232"
LEI_MAP = {LEI: COMPANY_ID}


def _issue(
    *,
    seed: bytes = _ENTITY_SEED,
    issuer: str = ENTITY_DID,
    person: str = "王小明",
    role: str = "董事",
    lei: str = LEI,
    credential_id: str = "urn:vc:oor:1",
    types: list[str] | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> dict:
    """簽發一份真的有簽章的 OOR 憑證。"""
    now = datetime.now(UTC)
    credential = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "id": credential_id,
        "type": types if types is not None else ["VerifiableCredential", OOR_CREDENTIAL_TYPE],
        "issuer": issuer,
        "validFrom": (valid_from or now - timedelta(days=1)).isoformat(),
        "validUntil": (valid_until or now + timedelta(days=365)).isoformat(),
        "credentialSubject": {
            "lei": lei,
            "personName": person,
            "officialRole": {"roleName": role},
        },
    }
    signature = sign(seed, canonicalise(credential))
    credential["proof"] = {
        "type": "DataIntegrityProof",
        "verificationMethod": issuer,
        "proofValue": signature.hex(),
    }
    return credential


def _presentation(*credentials: dict) -> dict:
    return {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "type": ["VerifiablePresentation"],
        "verifiableCredential": list(credentials),
    }


# ── Ed25519 ────────────────────────────────────────────────


def test_ed25519_matches_rfc8032_official_vectors():
    """自行實作的密碼學若不對照官方向量驗證，等於沒有驗證。"""
    for pk_hex, msg_hex, sig_hex in _RFC_VECTORS:
        assert ed25519_verify(
            bytes.fromhex(pk_hex), bytes.fromhex(msg_hex), bytes.fromhex(sig_hex)
        ), pk_hex


def test_ed25519_rejects_tampering():
    """改一個位元組就必須驗不過——簽章的全部價值就在這裡。"""
    pk_hex, msg_hex, sig_hex = _RFC_VECTORS[1]
    pk, msg, sig = bytes.fromhex(pk_hex), bytes.fromhex(msg_hex), bytes.fromhex(sig_hex)

    tampered_sig = bytearray(sig)
    tampered_sig[0] ^= 1
    assert not ed25519_verify(pk, msg, bytes(tampered_sig))
    assert not ed25519_verify(pk, b"\x73", sig)  # 改訊息
    assert not ed25519_verify(bytes(32), msg, sig)  # 換公鑰
    assert not ed25519_verify(pk, msg, sig[:63])  # 長度不對


def test_ed25519_rejects_oversized_scalar():
    """s 必須小於群階 L，否則同一份訊息會有多個有效簽章（可塑性）。"""
    pk_hex, msg_hex, sig_hex = _RFC_VECTORS[1]
    sig = bytearray(bytes.fromhex(sig_hex))
    sig[32:] = (2**252 + 27742317777372353535851937790883648493).to_bytes(32, "little")

    assert not ed25519_verify(bytes.fromhex(pk_hex), bytes.fromhex(msg_hex), bytes(sig))


# ── did:key ────────────────────────────────────────────────


def test_did_key_round_trip():
    pk = public_key(_ENTITY_SEED)

    assert resolve_ed25519_public_key(encode_ed25519_did(pk)) == pk


def test_did_key_rejects_malformed_input():
    for bad in ("", "did:web:example.com", "did:key:zzz!!!", "did:key:z2"):
        assert resolve_ed25519_public_key(bad) is None


# ── 五道驗證關卡 ────────────────────────────────────────────


def test_valid_credential_is_accepted_with_issuer_chain():
    result = verify_credential(_issue(), ANCHOR)

    assert result.valid, result.reasons
    # 授權鏈要能一路回溯到 GLEIF 根，這是 vLEI 信任模型的重點
    assert result.issuer_chain == [ENTITY_DID, QVI_DID, GLEIF_DID]


def test_credential_with_altered_content_fails_signature():
    """改內容後簽章必須失效——否則憑證可以被持有者任意改寫。"""
    credential = _issue()
    credential["credentialSubject"]["personName"] = "李大華"

    result = verify_credential(credential, ANCHOR)

    assert not result.valid
    assert any("簽章驗證失敗" in r for r in result.reasons)


def test_expired_and_not_yet_valid_credentials_are_rejected():
    now = datetime.now(UTC)
    expired = _issue(valid_until=now - timedelta(days=1))
    future = _issue(valid_from=now + timedelta(days=1))

    assert any("已過期" in r for r in verify_credential(expired, ANCHOR).reasons)
    assert any("尚未生效" in r for r in verify_credential(future, ANCHOR).reasons)


def test_untrusted_issuer_is_rejected_even_with_valid_signature():
    """簽章有效但簽發者回溯不到信任根——任何人都能自簽，所以這一關不可少。"""
    rogue = _issue(seed=_ROGUE_SEED, issuer=ROGUE_DID)

    result = verify_credential(rogue, ANCHOR)

    assert not result.valid
    assert any("無法回溯到信任根" in r for r in result.reasons)


def test_revoked_credential_is_rejected():
    credential = _issue(credential_id="urn:vc:oor:revoked")

    result = verify_credential(credential, ANCHOR, revoked_ids={"urn:vc:oor:revoked"})

    assert not result.valid
    assert any("已被撤銷" in r for r in result.reasons)


def test_trust_chain_survives_a_cyclic_authorisation_table():
    """授權表被寫成環時不得無限迴圈，而是判定不可信。"""
    cyclic = TrustAnchor(root=GLEIF_DID, authorised_by={QVI_DID: ENTITY_DID, ENTITY_DID: QVI_DID})

    assert cyclic.chain(ENTITY_DID) is None


def test_canonicalisation_is_key_order_independent():
    """規範化必須與鍵順序無關，否則同一份憑證換個序就驗不過。"""
    assert canonicalise({"a": 1, "b": {"c": 2, "d": 3}}) == canonicalise(
        {"b": {"d": 3, "c": 2}, "a": 1}
    )


# ── vLEI 升級 ───────────────────────────────────────────────

_AFFILIATIONS = [
    Affiliation(
        "一詮精密工業", "王小明", role="董事", company_id=COMPANY_ID, tier="B", merge=False
    ),
    Affiliation("世銓科技", "王小明", role="董事", company_id="54318252", tier="B", merge=False),
]


def test_verified_credential_promotes_candidate_to_evidence():
    """通過驗證的 OOR 憑證把 B 層候選升為 A 層可歸戶，並留下來源紀錄。"""
    upgraded, promotions, rejected = promote_affiliations(
        _AFFILIATIONS, _presentation(_issue()), ANCHOR, LEI_MAP
    )

    promoted = [a for a in upgraded if a.tier == "A"]
    assert len(promoted) == 1
    assert promoted[0].company == "一詮精密工業"
    assert promoted[0].merge is True
    assert "vLEI 已驗證" in promoted[0].role
    # 沒有憑證的那一筆維持候選，不受影響
    assert [a.tier for a in upgraded] == ["A", "B"]

    assert len(promotions) == 1
    assert promotions[0].lei == LEI
    assert promotions[0].issuer_chain == [ENTITY_DID, QVI_DID, GLEIF_DID]
    assert not rejected


def test_credential_for_an_unknown_person_promotes_nothing():
    """憑證指到名冊上沒有的人時，不得讓一條關聯憑空出現。

    否則任何人簽一份憑證就能影響歸戶結果，信任模型會被憑證持有者操縱。
    """
    credential = _issue(person="不存在的人")

    upgraded, promotions, _ = promote_affiliations(
        _AFFILIATIONS, _presentation(credential), ANCHOR, LEI_MAP
    )

    assert len(upgraded) == len(_AFFILIATIONS)
    assert promotions == []
    assert all(a.tier == "B" for a in upgraded)


def test_already_a_tier_affiliation_is_not_re_promoted():
    """已經是 A 層的關聯不得被憑證再「升級」一次。

    這一條釘住的是 promote_affiliations 裡的 `tier == "B"` 守衛。先前只測了
    「憑證指到不存在的人」，那在守衛被拿掉時也照樣通過——守衛等於沒有測到
    （實測把守衛改成無條件，測試全綠）。A 層列的 person 是所代表法人，
    對它套用自然人角色憑證在語意上就是錯的，也會產生重複的升級紀錄。
    """
    a_tier = [
        Affiliation(
            "一詮精密工業",
            "王小明",
            role="法人董事",
            company_id=COMPANY_ID,
            person_id="99999999",
            tier="A",
            merge=True,
        )
    ]

    upgraded, promotions, _ = promote_affiliations(
        a_tier, _presentation(_issue()), ANCHOR, LEI_MAP
    )

    assert promotions == []
    assert upgraded[0].role == "法人董事"  # 不得被加上「（vLEI 已驗證）」


def test_non_oor_role_is_not_a_basis_for_attribution():
    """業務往來角色（ECR）不是法定職務，不得作為歸戶依據。"""
    credential = _issue(role="採購聯絡人")

    upgraded, promotions, rejected = promote_affiliations(
        _AFFILIATIONS, _presentation(credential), ANCHOR, LEI_MAP
    )

    assert promotions == []
    assert all(a.tier == "B" for a in upgraded)
    assert any("不屬於法定職務" in r for r in rejected)


def test_credential_type_must_be_an_oor_credential():
    credential = _issue(types=["VerifiableCredential", "SomeOtherCredential"])

    _, promotions, rejected = promote_affiliations(
        _AFFILIATIONS, _presentation(credential), ANCHOR, LEI_MAP
    )

    assert promotions == []
    assert any("不是 OOR 角色憑證" in r for r in rejected)


def test_unmapped_lei_does_not_promote():
    """LEI 對不到統一編號就不升級——不猜。"""
    credential = _issue(lei="0000000000000000TEST")

    _, promotions, rejected = promote_affiliations(
        _AFFILIATIONS, _presentation(credential), ANCHOR, LEI_MAP
    )

    assert promotions == []
    assert any("查不到對應統一編號" in r for r in rejected)


def test_one_bad_credential_does_not_disqualify_the_others():
    """一份壞掉不該讓整批連坐，否則銀行送一批憑證進來時一份過期就全滅。"""
    good = _issue(credential_id="urn:vc:good")
    bad = _issue(
        seed=_ROGUE_SEED, issuer=ROGUE_DID, credential_id="urn:vc:bad", person="李大華"
    )

    _, promotions, rejected = promote_affiliations(
        _AFFILIATIONS, _presentation(bad, good), ANCHOR, LEI_MAP
    )

    assert len(promotions) == 1
    assert promotions[0].credential_id == "urn:vc:good"
    assert rejected  # 壞的那份有回報原因


def test_promotion_changes_the_grouping_outcome():
    """升級要真的影響歸戶：升級前兩家分屬兩戶，升級後仍不合併（只有一邊有憑證）。

    這一條釘住的是「兩端都要同意才合併」的既有規則不被憑證繞過——一份憑證
    只證明一端的身分，另一端仍是未解析的候選，合併仍不成立。
    """
    before = detect_groups(build_company_graph(_AFFILIATIONS))
    upgraded, _, _ = promote_affiliations(
        _AFFILIATIONS, _presentation(_issue()), ANCHOR, LEI_MAP
    )
    after = detect_groups(build_company_graph(upgraded))

    assert len(set(before.values())) == 2
    assert len(set(after.values())) == 2


def test_both_ends_verified_does_merge():
    """兩端都有憑證時才真的併成一戶——這才是這個功能的最終價值。"""
    presentation = _presentation(
        _issue(credential_id="urn:vc:a"),
        _issue(credential_id="urn:vc:b", lei="LEI-SHIQUAN"),
    )
    lei_map = {LEI: COMPANY_ID, "LEI-SHIQUAN": "54318252"}

    upgraded, promotions, _ = promote_affiliations(
        _AFFILIATIONS, presentation, ANCHOR, lei_map
    )
    groups = detect_groups(build_company_graph(upgraded))

    assert len(promotions) == 2
    assert len(set(groups.values())) == 1  # 併成同一戶


# ── Merkle 錨定 ─────────────────────────────────────────────


def test_merkle_root_is_order_independent():
    """清單順序不該影響根雜湊，否則換個順序就成了另一個根，錨定失去意義。"""
    assert merkle_root(["b", "a", "c"]) == merkle_root(["c", "b", "a"])


def test_inclusion_proof_verifies_and_detects_tampering():
    entries = [f"urn:vc:{i}" for i in range(7)]
    proof = build_inclusion_proof(entries, "urn:vc:3")

    assert proof is not None
    assert verify_inclusion(proof)

    tampered = type(proof)(entry="urn:vc:6", path=proof.path, root=proof.root)
    assert not verify_inclusion(tampered)


def test_inclusion_proof_is_none_for_absent_entry():
    assert build_inclusion_proof(["a", "b"], "c") is None


def test_leaf_and_node_hashes_use_different_prefixes():
    """葉節點與內部節點必須加不同前綴（域分離），否則可構造出兩棵不同的樹卻
    算出同一個根——Merkle 樹的第二原像攻擊。

    這一條要直接釘住「前綴確實被加上去了」。先前的版本只斷言
    merkle_root(["a"]) != merkle_root(["a","b"])，那在**沒有任何前綴**時也成立，
    所以把前綴拿掉測試照樣全綠（實測過）。改為與「沒有前綴時會算出的值」比對。
    """
    import hashlib

    # 若葉節點沒有 0x00 前綴，單項目的根會等於 sha256(項目本身)
    naive_leaf = hashlib.sha256(b"a").hexdigest()
    assert merkle_root(["a"]) != naive_leaf

    # 若內部節點沒有 0x01 前綴，兩項目的根會等於 sha256(葉a ‖ 葉b)
    leaf_a = hashlib.sha256(b"\x00a").digest()
    leaf_b = hashlib.sha256(b"\x00b").digest()
    naive_node = hashlib.sha256(leaf_a + leaf_b).hexdigest()
    assert merkle_root(["a", "b"]) != naive_node


def test_registry_reports_whether_it_is_anchored():
    """未錨定就要照實說未錨定，不得把本機清單講成已上鏈。"""
    unanchored = RevocationRegistry(["urn:vc:x"])
    anchored = RevocationRegistry(["urn:vc:x"], "base-sepolia:0xabc:12345678")

    assert not unanchored.anchored
    assert anchored.anchored
    assert unanchored.root == anchored.root  # 錨定與否不改變根


# ── API 端點 ────────────────────────────────────────────────


def _api_body(**overrides) -> dict:
    body = {
        "affiliations": [
            {
                "company": "一詮精密工業",
                "person": "王小明",
                "role": "董事",
                "company_id": COMPANY_ID,
                "tier": "B",
                "merge": False,
            },
            {
                "company": "世銓科技",
                "person": "王小明",
                "role": "董事",
                "company_id": "54318252",
                "tier": "B",
                "merge": False,
            },
        ],
        "presentation": _presentation(
            _issue(credential_id="urn:vc:a"),
            _issue(credential_id="urn:vc:b", lei="LEI-B"),
        ),
        "trust_root": GLEIF_DID,
        "authorised_by": {GLEIF_DID: GLEIF_DID, QVI_DID: GLEIF_DID, ENTITY_DID: QVI_DID},
        "lei_to_company_id": {LEI: COMPANY_ID, "LEI-B": "54318252"},
    }
    body.update(overrides)
    return body


def test_trust_endpoint_promotes_and_merges():
    from fastapi.testclient import TestClient

    from smelens.api.main import app

    body = _api_body(
        revoked_credential_ids=["urn:vc:old"],
        anchor_reference="base-sepolia:0xabc:12345678",
    )
    payload = TestClient(app).post("/trust/verify", json=body).json()

    assert len(payload["promoted"]) == 2
    # 升級的價值要看得見：兩戶併成一戶
    assert payload["groups_before"] == 2
    assert payload["groups_after"] == 1
    # 授權鏈要一路回溯到 GLEIF 根
    assert payload["promoted"][0]["issuer_chain"] == [ENTITY_DID, QVI_DID, GLEIF_DID]
    assert payload["revocation"]["anchored"] is True
    assert payload["revocation"]["revoked_count"] == 1


def test_trust_endpoint_masks_natural_person_names_even_after_promotion():
    """升級後 tier 變成 A，若用 tier 判斷是否遮蔽，真實姓名就會漏出去。

    遮蔽的判準必須是「這個 person 是不是自然人」，不是升級後的層級。
    """
    import json

    from fastapi.testclient import TestClient

    from smelens.api.main import app

    body = _api_body(
        affiliations=[
            {
                "company": "一詮精密工業",
                "person": "王小明",
                "role": "董事",
                "company_id": COMPANY_ID,
                "tier": "B",
                "merge": False,
            },
            {
                "company": "甲公司",
                "person": "乙母公司",
                "role": "法人董事",
                "company_id": "11111111",
                "person_id": "22222222",
                "tier": "A",
                "merge": True,
            },
        ],
        presentation=_presentation(_issue()),
        lei_to_company_id={LEI: COMPANY_ID},
    )
    payload = TestClient(app).post("/trust/verify", json=body).json()

    assert "王小明" not in json.dumps(payload, ensure_ascii=False)
    by_company = {a["company"]: a["person"] for a in payload["affiliations"]}
    assert by_company["一詮精密工業"] == "王○明"
    # 所代表法人是公司名，屬登記公示資訊，不得遮蔽
    assert by_company["甲公司"] == "乙母公司"


def test_trust_endpoint_reports_rejection_reasons():
    """被拒的憑證要說得出原因，否則呼叫端無法告知使用者哪裡不對。"""
    from fastapi.testclient import TestClient

    from smelens.api.main import app

    body = _api_body(
        presentation=_presentation(
            _issue(seed=_ROGUE_SEED, issuer=ROGUE_DID, credential_id="urn:vc:rogue")
        )
    )
    payload = TestClient(app).post("/trust/verify", json=body).json()

    assert payload["promoted"] == []
    assert any("無法回溯到信任根" in r for r in payload["rejected"])
    assert payload["groups_before"] == payload["groups_after"] == 2
