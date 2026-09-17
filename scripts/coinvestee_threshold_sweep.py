"""分析腳本：對候選合資橋接門檻掃描全國最大歸戶群組規模，供選定
DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD 的實測依據（機構橋接門檻固定在
DEFAULT_HUB_SEAT_THRESHOLD，只變動合資橋接門檻）。

輸出寫入 data/cache/coinvestee_sweep.json（data/cache 已排除版控，可重新
產生）——docs/GCIS_FINDINGS.md 與 smelens/data/gcis.py 該常數 docstring
裡引用的門檻掃描表格對應本腳本某次執行的實際輸出。

用法：
    ./.venv/Scripts/python.exe scripts/coinvestee_threshold_sweep.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smelens.credit.group import build_company_graph, detect_groups  # noqa: E402
from smelens.data.gcis import (  # noqa: E402
    DEFAULT_HUB_SEAT_THRESHOLD,
    corporate_edges_to_affiliations,
    load_corporate_director_edges,
)

CSV_PATH = Path("data/raw/gcis_directors.csv")
OUT_PATH = Path("data/cache/coinvestee_sweep.json")

SWEEP = (2, 3, 4, 5, 6, 7, 10, 1_000_000)  # 1_000_000 = 相當於「不啟用合資橋接防護」


def main() -> int:
    t0 = time.perf_counter()
    edges = load_corporate_director_edges(CSV_PATH)
    print(f"edges loaded: {len(edges):,} ({time.perf_counter() - t0:.1f}s)", flush=True)

    rows = []
    for threshold in SWEEP:
        t1 = time.perf_counter()
        affiliations = list(
            corporate_edges_to_affiliations(
                edges,
                hub_seat_threshold=DEFAULT_HUB_SEAT_THRESHOLD,
                coinvestee_director_threshold=threshold,
            )
        )
        graph = build_company_graph(affiliations)
        groups = detect_groups(graph)
        elapsed = time.perf_counter() - t1

        sizes: Counter[int] = Counter(groups.values())
        multi = {gid: c for gid, c in sizes.items() if c >= 2}
        largest = max(multi.values()) if multi else 0
        largest_gid = max(multi, key=lambda g: multi[g]) if multi else None
        inv: dict[int, list[str]] = {}
        for company, gid in groups.items():
            inv.setdefault(gid, []).append(company)
        sample = sorted(inv[largest_gid])[:5] if largest_gid is not None else []

        row = {
            "threshold": threshold,
            "largest_group": largest,
            "multi_company_groups": len(multi),
            "elapsed_s": elapsed,
            "largest_sample": sample,
        }
        rows.append(row)
        print(
            f"threshold={threshold}: largest={largest}, multi={len(multi)}, "
            f"{elapsed:.1f}s",
            flush=True,
        )

    total = time.perf_counter() - t0
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({"rows": rows, "total_elapsed_s": total}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"done in {total:.1f}s -> {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
