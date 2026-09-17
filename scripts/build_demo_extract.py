"""從全國董監事索引抽出「A 層專用」精簡索引，供線上 Demo 直接查真實統一編號。

為什麼需要這支腳本
------------------
全國原始 CSV 約 119 MB、完整 SQLite 索引約 193 MB，兩者都在 .gitignore 裡，
也都超過雲端函式的部署體積上限。但一頁式企劃書與 Demo 腳本都宣稱「可輸入
真實統一編號」——要讓這句話成立，線上版必須帶著一份能進 repo 的資料。

抽什麼、為什麼是這個抽法
------------------------
保留「A 層宇宙」內每一家公司的**全部**董監事列。A 層宇宙 = 有法人董事的
公司（子公司側）∪ 被列為所代表法人且查得到統一編號的公司（母公司側）。

只留 A 層列是不夠的，而且錯得很安靜：母公司自己的董監事通常是自然人，
名下沒有任何 A 層列，BFS 從母公司統編出發會一筆都找不到，鄰域直接是空的
（本腳本第一版就踩到，由結尾的對照驗證擋下）。歸戶要從任何一端都走得通，
就必須連這些公司的自然人列一起帶走。

但整包只留部分公司，會讓「某個姓名掛幾家公司」的席次統計低估，樞紐姓名
（菜市場名）因此濾不掉，BFS 會沿著同名過度展開。故本腳本另外寫入一張由
**全國完整資料**算好的 person_seats 表；smelens.data.gcis._seat_counts 偵測
到這張表時會優先採用（見該函式說明）。法人席次與合資橋接的判定只用到 A 層
列，而 A 層列一筆都沒刪，因此本來就是精確的。

至於 B 層（自然人同名）本來就宣告「需銀行以 KYC 身分證字號解析、不自動
合併」——Affiliation.merge 對 B 層恆為 False——所以線上版沒有身分證字號
這件事不影響歸戶結果，只影響候選清單的完整度。

用法（repo 根目錄）::

    ./.venv/Scripts/python.exe scripts/build_demo_extract.py \
        --source <全國 directors.csv 路徑> \
        --out data/demo/gcis_a_tier.sqlite

產出的檔案與全國索引 schema 完全相同，故可直接當作 extract_neighborhood 的
db_path 傳入；由於 build_index 在 db_path 已存在時會直接沿用，線上環境不需要
（也不會去碰）原始 CSV。
"""

from __future__ import annotations

import argparse
import gzip
import random
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smelens.credit.group import build_company_graph, detect_groups  # noqa: E402
from smelens.data.gcis import (  # noqa: E402
    _INDEX_SCHEMA,
    PERSON_SEAT_TABLE,  # noqa: E402
    _default_index_path,
    build_index,
    extract_neighborhood,
)

#: 一定要驗的統編：企劃書與 Demo 腳本實際會示範的公司。
VERIFY_COMPANY_IDS = ("35866232",)

#: 除了上面這些，再從 A 層宇宙隨機抽這麼多家一起驗——只驗示範公司等於只驗
#: 自己挑過的案例，證明不了線上版對任意統編都可靠。種子固定，結果可重現。
VERIFY_SAMPLE_SIZE = 100
VERIFY_SAMPLE_SEED = 20261014

#: 驗證時兩邊都放寬鄰域上限，把「上限截斷順序不同」這種與索引無關的雜訊排除，
#: 只留下真正因精簡而產生的差異。產品預設仍是 extract_neighborhood 的 300。
VERIFY_MAX_COMPANIES = 3000

#: 可容忍的遺漏率上限。精簡索引只保留 A 層宇宙內公司的列，少數查詢原本要
#: 「借道」一家純自然人公司才走得到的成員會因此走不到——這是可量測、已量測
#: 的代價，不是未知風險。超過此上限代表抽法出了問題，腳本會失敗。
VERIFY_MAX_MISS_RATE = 0.05


def build_extract(source_csv: Path, out_path: Path) -> tuple[Path, int]:
    """建立 A 層精簡索引，回傳 (輸出路徑, 列數)。

    來源是全國索引而非 CSV：索引若尚未建立會先建（耗時一到兩分鐘），已建立
    則直接沿用，避免為了抽樣又全檔掃描一次。
    """
    national_db = build_index(source_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".building")
    tmp_path.unlink(missing_ok=True)

    conn = sqlite3.connect(tmp_path)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute(_INDEX_SCHEMA)
        conn.execute("ATTACH DATABASE ? AS src", (str(national_db),))
        # A 層宇宙：有法人董事的公司（子公司側）＋ 被列為所代表法人且查得到
        # 統一編號的公司（母公司側）。兩側都要，否則從母公司統編查不到東西。
        conn.execute(
            "INSERT INTO rows SELECT * FROM src.rows WHERE company_id IN ("
            "  SELECT company_id FROM src.rows WHERE represented_norm != ''"
            "  UNION"
            "  SELECT represented_id FROM src.rows WHERE represented_id IS NOT NULL"
            ")"
        )
        (count,) = conn.execute("SELECT COUNT(*) FROM rows").fetchone()
        # 自然人席次由全國完整資料算出後寫入，不可由精簡後的 rows 重算。
        conn.execute(
            f"CREATE TABLE {PERSON_SEAT_TABLE} (person_norm TEXT PRIMARY KEY, seats INTEGER)"
        )
        # 只存席次 ≥2 的姓名：席次 1 的姓名占了絕大多數，而查不到的姓名在
        # _seat_counts 取用端會退回 0，一樣低於任何 ≥2 的樞紐門檻，判定不變。
        # 這讓這張表從七十餘萬列降到十餘萬列。唯一的例外是把 hub_name_threshold
        # 調成 1（等於關閉自然人展開），該情境不需要精確席次。
        conn.execute(
            # 不可加 represented_norm='' 的條件：全國索引的 _seat_counts 是對
            # 整張 rows 聚合的，法人代表列上的自然人姓名一樣計入席次。加了條件
            # 會低估「既自己掛董事、又代表法人掛董事」的人，樞紐姓名因此濾不掉
            # 而過度合併——本腳本開發時實測到一家公司在精簡索引下從 1 家暴增為
            # 5 家，就是這個原因。
            f"INSERT INTO {PERSON_SEAT_TABLE} "
            "SELECT person_norm, COUNT(DISTINCT company_id) AS seats FROM src.rows "
            "WHERE person_norm != '' "
            "GROUP BY person_norm HAVING seats >= 2"
        )
        conn.execute("CREATE INDEX idx_rows_company ON rows(company_id)")
        conn.execute("CREATE INDEX idx_rows_person ON rows(person_norm)")
        conn.execute("CREATE INDEX idx_rows_represented ON rows(represented_norm)")
        conn.commit()
        conn.execute("DETACH DATABASE src")
        conn.execute("VACUUM")
    finally:
        conn.close()

    tmp_path.replace(out_path)
    return out_path, count


def _query_group(source_csv: Path, db_path: Path, company_id: str) -> tuple[str, list[str]]:
    """回傳 (被查公司名稱, 它所屬歸戶群組的成員清單)。查不到時回傳空群組。"""
    affiliations = extract_neighborhood(
        source_csv, company_id, db_path=db_path, max_companies=VERIFY_MAX_COMPANIES
    )
    own = next((a.company for a in affiliations if a.company_id == company_id), "")
    if not own:
        return "", []
    groups = detect_groups(build_company_graph(affiliations))
    target = groups.get(own)
    if target is None:
        return own, []
    return own, sorted(c for c, gid in groups.items() if gid == target)


def _sample_company_ids(extract_path: Path, count: int) -> list[str]:
    """從精簡索引裡隨機抽 count 家公司統編（固定種子，可重現）。"""
    conn = sqlite3.connect(extract_path)
    try:
        ids = [r[0] for r in conn.execute("SELECT DISTINCT company_id FROM rows")]
    finally:
        conn.close()
    ids.sort()
    return random.Random(VERIFY_SAMPLE_SEED).sample(ids, min(count, len(ids)))


def compress(sqlite_path: Path) -> Path:
    """把索引壓成 .gz——進版控的是壓縮檔。

    47 MB 的 SQLite 逼近 GitHub 的單檔警告線，壓縮後約 14 MB；執行期由
    smelens.data.gcis.demo_index_path 解壓到快取目錄，只做一次。未壓縮的
    .sqlite 留在原地方便本機比對，已由 .gitignore 排除。
    """
    gz_path = sqlite_path.with_suffix(sqlite_path.suffix + ".gz")
    with open(sqlite_path, "rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    return gz_path


def verify(source_csv: Path, extract_path: Path) -> tuple[list[str], dict[str, int]]:
    """對照全國索引與精簡索引重跑查詢，回傳 (致命問題清單, 統計)。

    比對的是**被查公司自己的歸戶群組成員**——那就是線上 Demo 實際顯示、
    也是授信人員實際會用的輸出。不比整個鄰域的關係集合：鄰域是計算過程的
    中間產物，精簡索引的 BFS 觸及範圍本來就比較小，但只要被查公司的群組
    一致，對外結果就一致。

    分三類計數：identical（逐字相同）、missing（精簡版少了成員——精簡的真實
    代價）、extra（精簡版多了成員）。示範統編只要有任何差異就是致命問題；
    隨機抽樣則允許 VERIFY_MAX_MISS_RATE 以內的遺漏率。
    """
    fatal: list[str] = []
    stats = {"identical": 0, "missing": 0, "extra": 0}
    national_db = _default_index_path(source_csv)
    sample = [
        cid
        for cid in _sample_company_ids(extract_path, VERIFY_SAMPLE_SIZE)
        if cid not in VERIFY_COMPANY_IDS
    ]
    for cid in list(VERIFY_COMPANY_IDS) + sample:
        _, full_group = _query_group(source_csv, national_db, cid)
        name, slim_group = _query_group(source_csv, extract_path, cid)
        lost = sorted(set(full_group) - set(slim_group))
        gained = sorted(set(slim_group) - set(full_group))
        if not lost and not gained:
            stats["identical"] += 1
            continue
        if lost:
            stats["missing"] += 1
        else:
            stats["extra"] += 1
        detail = (
            f"{cid} {name}：全國 {len(full_group)} 家、精簡 {len(slim_group)} 家"
            f"（少 {lost[:3]}、多 {gained[:3]}）"
        )
        if cid in VERIFY_COMPANY_IDS:
            fatal.append(f"示範統編結果不一致──{detail}")
        else:
            print(f"  · {detail}")

    checked = len(VERIFY_COMPANY_IDS) + len(sample)
    miss_rate = stats["missing"] / checked if checked else 0.0
    if miss_rate > VERIFY_MAX_MISS_RATE:
        fatal.append(
            f"遺漏率 {miss_rate:.1%} 超過上限 {VERIFY_MAX_MISS_RATE:.0%}"
            f"（{stats['missing']}/{checked} 家）"
        )
    stats["checked"] = checked
    return fatal, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="全國 directors.csv 路徑")
    parser.add_argument(
        "--out", type=Path, default=Path("data/demo/gcis_a_tier.sqlite"), help="輸出索引路徑"
    )
    parser.add_argument("--skip-verify", action="store_true", help="略過對照驗證（不建議）")
    args = parser.parse_args()

    out_path, count = build_extract(args.source, args.out)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"已產生 {out_path}（{count:,} 列、{size_mb:.1f} MB）")

    gz_path = compress(out_path)
    gz_mb = gz_path.stat().st_size / 1024 / 1024
    print(f"已壓縮 {gz_path}（{gz_mb:.1f} MB，進版控的就是這一份）")

    if args.skip_verify:
        print("已略過對照驗證")
        return 0

    print(
        f"對照驗證中（{VERIFY_SAMPLE_SIZE} 家抽樣，"
        f"兩邊鄰域上限皆放寬至 {VERIFY_MAX_COMPANIES}）…"
    )
    fatal, stats = verify(args.source, out_path)
    print(
        f"驗證 {stats['checked']} 家：逐字相同 {stats['identical']}、"
        f"精簡版少成員 {stats['missing']}、精簡版多成員 {stats['extra']}"
    )
    if fatal:
        for p in fatal:
            print(f"✗ {p}")
        return 1
    print("✓ 對照驗證通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
