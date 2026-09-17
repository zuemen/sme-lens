"""量測「名稱規則抓不到的集團」比率：關係圖歸戶到底比肉眼多找到多少。

為什麼需要這支腳本
------------------
企劃書主張「共用董監事的隱性關聯查不出來」，但先前所有數字都是技術量
（102 萬家公司、67,838 條邊、19,150 個群組），沒有一個回答評審必問的那句話：
**「這些關聯，人工難道找不到嗎？」**

授信人員在沒有關係圖的情況下，能用的線索其實只有兩種：客戶自己申報的關係企業
表，以及公司名稱的字根（「泰昇精密」與「泰昇投資」一看就是一家）。前者我們沒有
銀行的內部資料無法量測；後者完全可以用公開資料量測——這支腳本就做這件事：

    在所有多公司歸戶群組裡，有多少比率的群組，成員之間**沒有任何共同的名稱字根**？

這個比率是「名稱規則與肉眼完全抓不到、只有關係圖找得到」的下界（下界而非精確值：
名稱有共同字根不代表行員真的會去比對，所以實際漏掛只會更多，不會更少）。

方法
----
1. 剝掉組織型態字尾（股份有限公司、有限公司、企業社…）與常見地域詞，取「核心名」。
2. 群組內任兩家公司若共用一個長度 ≥ MIN_ROOT 的子字串，視為「名稱看得出關聯」。
3. 群組內所有配對都沒有共用字根 → 該群組「名稱不可見」。

刻意選最保守的判定：只要**任一對**成員名稱看得出關聯，整個群組就算「可見」，
不計入分子。寧可低估自己的貢獻，也不要報一個經不起追問的數字。

用法（repo 根目錄）::

    ./.venv/Scripts/python.exe scripts/name_invisible_groups.py --source data/raw/gcis_directors.csv
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smelens.credit.group import (  # noqa: E402
    build_company_graph,
    detect_groups,
)
from smelens.data.gcis import (  # noqa: E402
    corporate_edges_to_affiliations,
    load_corporate_director_edges,
)

#: 共用子字串至少要這麼長才算「名稱看得出關聯」。取 2 是因為中文公司名的字根
#: 多為兩字（泰昇、宏益、一詮）；取 1 會讓「大」「台」「新」這類單字造成大量
#: 假可見，反而低估本系統的貢獻——但低估的方向是安全的，故仍取較保守的 2。
MIN_ROOT = 2

#: 組織型態與常見修飾語，比對前先剝掉：它們是所有公司都有的，留著會讓每一對
#: 公司都「共用字根」，整個量測就失去意義。
_SUFFIXES = (
    "股份有限公司",
    "有限公司",
    "股份公司",
    "企業社",
    "商行",
    "公司",
    "分公司",
    "工廠",
)

#: 高頻通用詞：這些字出現在成千上萬家不相干的公司名裡，共用它們不構成「看得出
#: 關聯」。清單刻意保守（只收真正泛用的），以免過度剝除而高估不可見比率。
_GENERIC = (
    "台灣",
    "臺灣",
    "國際",
    "實業",
    "科技",
    "企業",
    "投資",
    "開發",
    "工程",
    "貿易",
    "建設",
    "生技",
    "資訊",
    "控股",
    "管理",
    "顧問",
    "股份",
    "精密",
    "電子",
)


def core_name(name: str) -> str:
    """取公司名的核心字串：剝掉組織型態字尾與高頻通用詞。"""
    text = name.strip()
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = re.sub(r"[（(].*?[）)]", "", text)
    for word in _GENERIC:
        text = text.replace(word, "")
    return re.sub(r"\s+", "", text)


def shares_root(a: str, b: str, min_root: int = MIN_ROOT) -> bool:
    """兩個核心名是否共用長度 >= min_root 的子字串。"""
    if len(a) < min_root or len(b) < min_root:
        return False
    roots = {a[i : i + min_root] for i in range(len(a) - min_root + 1)}
    return any(b[i : i + min_root] in roots for i in range(len(b) - min_root + 1))


def group_is_name_visible(members: list[str]) -> bool:
    """群組內是否**任一對**成員的名稱看得出關聯（保守判定，見模組說明）。"""
    cores = [core_name(m) for m in members]
    return any(shares_root(a, b) for a, b in combinations(cores, 2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/raw/gcis_directors.csv"),
        help="全國董監事資料集 CSV",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/cache/name_invisible_groups.json"),
        help="結果 JSON 輸出路徑",
    )
    parser.add_argument("--examples", type=int, default=10, help="印出幾個不可見群組的例子")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"找不到來源資料：{args.source}")
        return 2

    print("載入 A 層邊…")
    edges = load_corporate_director_edges(args.source)
    affiliations = corporate_edges_to_affiliations(edges)
    groups = detect_groups(build_company_graph(affiliations))

    members_by_group: dict[int, list[str]] = defaultdict(list)
    for company, group_id in groups.items():
        members_by_group[group_id].append(company)
    multi = {gid: names for gid, names in members_by_group.items() if len(names) >= 2}

    invisible: list[list[str]] = []
    visible_count = 0
    for names in multi.values():
        if group_is_name_visible(names):
            visible_count += 1
        else:
            invisible.append(sorted(names))

    total = len(multi)
    ratio = len(invisible) / total if total else 0.0
    size_dist = Counter(len(names) for names in invisible)

    print()
    print(f"多公司歸戶群組總數：{total:,}")
    print(f"名稱看得出關聯（任一對成員共用 {MIN_ROOT} 字以上字根）：{visible_count:,}")
    print(f"**名稱完全看不出關聯**：{len(invisible):,}（{ratio:.1%}）")
    print(f"不可見群組的規模分布（前 8）：{dict(sorted(size_dist.items())[:8])}")
    print()
    print(f"不可見群組範例（前 {args.examples} 個）：")
    for names in sorted(invisible, key=lambda g: (-len(g), g[0]))[: args.examples]:
        print(f"  {len(names)} 家：{'、'.join(names)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "multi_company_groups": total,
                "name_visible": visible_count,
                "name_invisible": len(invisible),
                "name_invisible_ratio": round(ratio, 4),
                "min_root": MIN_ROOT,
                "invisible_size_distribution": dict(sorted(size_dist.items())),
                "invisible_examples": sorted(invisible, key=lambda g: (-len(g), g[0]))[:50],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print()
    print(f"結果已寫入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
