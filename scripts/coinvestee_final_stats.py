"""分析腳本：以修復後的預設門檻（機構橋接=5、合資橋接=4）重跑全國 A 層
歸戶，取完整規模分布與最大幾個群組樣本，供本次修復報告與
docs/GCIS_FINDINGS.md 引用的「修復後最大群組 60 家」等數字提供實測依據。

輸出寫入 data/cache/coinvestee_final_stats.json（data/cache 已排除版控，
可重新產生）。

用法：
    ./.venv/Scripts/python.exe scripts/coinvestee_final_stats.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smelens.credit.group import build_company_graph, detect_groups  # noqa: E402
from smelens.data.gcis import (  # noqa: E402
    DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD,
    DEFAULT_HUB_SEAT_THRESHOLD,
    corporate_edges_to_affiliations,
    load_corporate_director_edges,
)

CSV_PATH = Path("data/raw/gcis_directors.csv")
OUT_PATH = Path("data/cache/coinvestee_final_stats.json")


def main() -> int:
    t0 = time.perf_counter()
    edges = load_corporate_director_edges(CSV_PATH)
    print(f"edges loaded: {len(edges):,} ({time.perf_counter() - t0:.1f}s)", flush=True)

    t1 = time.perf_counter()
    affiliations = list(
        corporate_edges_to_affiliations(
            edges,
            hub_seat_threshold=DEFAULT_HUB_SEAT_THRESHOLD,
            coinvestee_director_threshold=DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD,
        )
    )
    graph = build_company_graph(affiliations)
    groups = detect_groups(graph)
    elapsed = time.perf_counter() - t1
    print(f"build+group: {elapsed:.1f}s", flush=True)

    sizes: Counter[int] = Counter(groups.values())
    multi = {gid: c for gid, c in sizes.items() if c >= 2}
    size_dist = sorted(Counter(multi.values()).items())

    inv: defaultdict[int, list[str]] = defaultdict(list)
    for company, gid in groups.items():
        inv[gid].append(company)
    largest = sorted(multi.items(), key=lambda kv: -kv[1])[:10]
    largest_named = [(gid, size, sorted(inv[gid])[:6]) for gid, size in largest]

    result = {
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "total_groups": len(sizes),
        "multi_company_groups": len(multi),
        "size_distribution": size_dist,
        "largest_groups": largest_named,
        "build_and_group_s": elapsed,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done -> {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
