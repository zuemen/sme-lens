"""分析腳本：掃全國 CSV，計算每家公司的相異法人董事數分布，供選定
DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD（合資橋接門檻）參考。

輸出寫入 data/cache/coinvestee_scan.json（data/cache 已排除版控，可重新
產生）——每個引用在 docs/GCIS_FINDINGS.md 與 smelens/data/gcis.py 該常數
docstring 裡的分布數字都對應本腳本某次執行的實際輸出，不是手動填的估計值。

用法：
    ./.venv/Scripts/python.exe scripts/coinvestee_threshold_scan.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smelens.data.gcis import load_corporate_director_edges  # noqa: E402

CSV_PATH = Path("data/raw/gcis_directors.csv")
OUT_PATH = Path("data/cache/coinvestee_scan.json")


def _represented_identity_key(edge) -> str:
    if edge.represented_id:
        return f"pid:{edge.represented_id}"
    return edge.represented_name


def main() -> int:
    t0 = time.perf_counter()
    edges = load_corporate_director_edges(CSV_PATH)
    print(f"edges loaded: {len(edges):,} ({time.perf_counter() - t0:.1f}s)", flush=True)

    per_company: dict[str, set[str]] = {}
    for e in edges:
        per_company.setdefault(e.company_id, set()).add(_represented_identity_key(e))

    director_counts = Counter(len(s) for s in per_company.values())
    dist = sorted(director_counts.items())

    # 找出相異法人董事數最多的前 20 家公司（供人工核實合資／被投資結構）。
    top_companies = sorted(per_company.items(), key=lambda kv: -len(kv[1]))[:20]
    top_named = [(cid, len(s)) for cid, s in top_companies]

    elapsed = time.perf_counter() - t0
    result = {
        "elapsed_s": elapsed,
        "company_count": len(per_company),
        "distribution": dist,
        "top_companies": top_named,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done in {elapsed:.1f}s -> {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
