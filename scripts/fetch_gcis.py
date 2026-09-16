"""下載經濟部商業發展署「董監事資料集」到 data/raw/gcis_directors.csv。

來源：https://data.gcis.nat.gov.tw/od/file?oid=7E5201D9-CAD2-494E-8920-5319D66F66A1
資料集頁：https://data.gov.tw/dataset/96731
提供機關：經濟部商業發展署
授權：政府資料開放授權條款－第1版（https://data.gov.tw/license）——使用、修改、
      散布本資料集皆須標示資料來源與提供機關；本檔頭部與 docs/GCIS_FINDINGS.md
      均已載明來源網址與提供機關，下游若引用本資料集衍生的任何結果，請一併
      保留這個標示，這是授權條款要求而非本專案自訂的規矩。
更新頻率：每月——同一份下載內容會隨時間變動，故 docs/GCIS_FINDINGS.md 一律
      記錄實際下載日期，不宣稱數字對所有下載時間點都成立。

data/raw/ 已在 .gitignore 中整批排除，本腳本下載的檔案不會被提交。

用法：
    ./.venv/Scripts/python.exe scripts/fetch_gcis.py
    ./.venv/Scripts/python.exe scripts/fetch_gcis.py --force   # 強制重新下載
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://data.gcis.nat.gov.tw/od/file?oid=7E5201D9-CAD2-494E-8920-5319D66F66A1"
DEST_PATH = Path("data/raw/gcis_directors.csv")


def _count_rows(path: Path) -> int:
    """回傳資料列數（不含表頭）。檔案為 UTF-8 with BOM，逐行讀取不吃記憶體。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in f) - 1


def fetch(dest: Path = DEST_PATH, *, force: bool = False) -> Path:
    """下載資料集到 dest；若檔案已存在且 force=False 則直接略過下載。

    可重跑（resumable/skippable）的意思是：已下載過的情況下重新執行本腳本
    是零成本的——不會重新打一次 119MB 的請求，適合放進任何重跑流程（例如
    scripts/gcis_findings.py 的前置步驟）而不必擔心每次都要等下載完成。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        print(f"已存在，略過下載：{dest}（如需重新下載請加 --force）")
        return dest

    print(f"下載中：{SOURCE_URL}")
    tmp_path = dest.with_suffix(dest.suffix + ".part")
    try:
        urllib.request.urlretrieve(SOURCE_URL, tmp_path)
        tmp_path.replace(dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    print(f"下載完成：{dest}（{dest.stat().st_size:,} bytes）")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEST_PATH, help="輸出路徑")
    parser.add_argument("--force", action="store_true", help="即使已存在也強制重新下載")
    args = parser.parse_args()

    path = fetch(args.dest, force=args.force)
    rows = _count_rows(path)
    print(f"資料列數（不含表頭）：{rows:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
