"""產生前端離線快照（credit / group / screening）：現場斷網或後端冷啟動逾時時，demo 仍能演完。

三份快照都由本腳本對正在跑的後端發出與前端 demo 完全相同的請求並落盤，
確保它們可重現、不會與後端行為漂移——這正是 screening 快照過去手工產生、
未納入本腳本時發生過的問題（見 web/e2e/screening.spec.ts 的說明）。

Windows 下務必以 PYTHONIOENCODING=utf-8 執行，否則 stdout 會弄壞中文。
`smelens` 未以 editable 方式裝進 .venv，故需一併指定 PYTHONPATH。

用法（在 repo 根目錄執行）：
    PYTHONIOENCODING=utf-8 PYTHONPATH=. ./.venv/Scripts/python.exe scripts/make_snapshots.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from smelens.api.main import app

OUT_DIR = Path("web/src/api")

DEMO_AFFILIATIONS = [
    {"company": "泰昇精密", "person": "陳大明", "role": "董事長"},
    {"company": "泰昇投資", "person": "陳大明", "role": "董事"},
    {"company": "昇泰貿易", "person": "王秀英", "role": "董事"},
    {"company": "泰昇投資", "person": "王秀英", "role": "監察人"},
    {"company": "禾昌五金", "person": "林志豪", "role": "董事長"},
]
DEMO_DECLARED = {
    "泰昇精密": "泰昇集團",
    "泰昇投資": "泰昇集團",
    "昇泰貿易": "昇泰集團",
}
DEMO_EXPOSURES = {"泰昇精密": 30_000_000, "泰昇投資": 12_000_000, "昇泰貿易": 8_000_000}


def main() -> None:
    client = TestClient(app)

    credit = client.post("/credit", json={"target": "泰昇精密"})
    credit.raise_for_status()
    (OUT_DIR / "credit-snapshot.json").write_text(
        json.dumps(credit.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    group = client.post(
        "/group",
        json={
            "affiliations": DEMO_AFFILIATIONS,
            "declared_groups": DEMO_DECLARED,
            "exposures": DEMO_EXPOSURES,
        },
    )
    group.raise_for_status()
    (OUT_DIR / "group-snapshot.json").write_text(
        json.dumps(group.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 與 Screening.tsx 的 postScreen('TOtcOut01', 500000) 完全一致的請求
    # （含 postScreen 內固定帶上的 request_id），避免快照與畫面實際打的請求脫鉤。
    screening = client.post(
        "/screen",
        json={"target": "TOtcOut01", "amount_usdt": 500000.0, "request_id": "DEMO-2026-001"},
    )
    screening.raise_for_status()
    (OUT_DIR / "screening-snapshot.json").write_text(
        json.dumps(screening.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("wrote credit-snapshot.json / group-snapshot.json / screening-snapshot.json")


if __name__ == "__main__":
    main()
