"""Elliptic Data Set 載入器：CSV → NetworkX 圖與 PyTorch Geometric Data。

三個 CSV（放在 data/raw/，自 Kaggle 下載）：
- elliptic_txs_features.csv：無 header，167 欄 = txId, time_step, 165 維特徵
- elliptic_txs_classes.csv：header txId,class（'1'=illicit、'2'=licit、'unknown'）
- elliptic_txs_edgelist.csv：header txId1,txId2
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import networkx as nx
import numpy as np
import pandas as pd

if TYPE_CHECKING:  # 僅型別檢查用；執行期由 load_elliptic_pyg 內延遲載入
    from torch_geometric.data import Data

TRAIN_MAX_STEP = 34  # 官方時間切分：train <= 34、test >= 35，避免資料洩漏

LABEL_ILLICIT = 1
LABEL_LICIT = 0
LABEL_UNKNOWN = -1

_CLASS_MAP = {"1": LABEL_ILLICIT, "2": LABEL_LICIT, "unknown": LABEL_UNKNOWN}

FEATURES_FILE = "elliptic_txs_features.csv"
CLASSES_FILE = "elliptic_txs_classes.csv"
EDGELIST_FILE = "elliptic_txs_edgelist.csv"


def raw_files_exist(raw_dir: Path) -> bool:
    """檢查三個 Elliptic CSV 是否齊備。"""
    return all((raw_dir / name).exists() for name in (FEATURES_FILE, CLASSES_FILE, EDGELIST_FILE))


def _load_frames(raw_dir: Path) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    features = pd.read_csv(raw_dir / FEATURES_FILE, header=None)
    classes = pd.read_csv(raw_dir / CLASSES_FILE)
    edges = pd.read_csv(raw_dir / EDGELIST_FILE)
    labels = classes.set_index("txId")["class"].astype(str).map(_CLASS_MAP)
    return features, labels, edges


def load_elliptic_graph(raw_dir: Path, include_features: bool = True) -> nx.DiGraph:
    """載入為 NetworkX 有向圖。

    節點屬性：time_step、label（1=illicit / 0=licit / -1=unknown）、
    feat（include_features=True 時附 165 維特徵）。
    節點順序與 features CSV 列順序一致，供 SNA 特徵對齊使用。
    """
    features, labels, edges = _load_frames(raw_dir)
    g = nx.DiGraph()
    for row in features.itertuples(index=False):
        tx_id = int(row[0])
        attrs: dict = {
            "time_step": int(row[1]),
            "label": int(labels.get(tx_id, LABEL_UNKNOWN)),
        }
        if include_features:
            attrs["feat"] = [float(v) for v in row[2:]]
        g.add_node(tx_id, **attrs)
    for src, dst in edges.itertuples(index=False):
        if g.has_node(int(src)) and g.has_node(int(dst)):
            g.add_edge(int(src), int(dst))
    return g


def load_elliptic_pyg(raw_dir: Path, extra_features: np.ndarray | None = None) -> Data:
    """載入為 PyG Data，含官方時間切分 train_mask / test_mask（僅涵蓋有標註節點）。

    extra_features：shape=(節點數, k) 的額外特徵（如 SNA 指標），
    列順序須與 features CSV 一致，會串接到 data.x 之後。

    torch / torch_geometric 於此延遲載入——讓不需訓練的服務（如 Vercel 上的 API）
    可完全不安裝這批重依賴（torch CPU wheel 遠超 serverless 250MB 上限）。
    """
    import torch
    from torch_geometric.data import Data

    features, labels, edges = _load_frames(raw_dir)
    tx_ids = features[0].astype(int).to_numpy()
    index_of = {tx: i for i, tx in enumerate(tx_ids)}

    x = features.iloc[:, 2:].to_numpy(dtype=np.float32)
    if extra_features is not None:
        if extra_features.shape[0] != x.shape[0]:
            raise ValueError("extra_features 列數需等於節點數")
        x = np.concatenate([x, extra_features.astype(np.float32)], axis=1)

    y = np.array([labels.get(tx, LABEL_UNKNOWN) for tx in tx_ids], dtype=np.int64)
    pairs = [
        (index_of[int(s)], index_of[int(d)])
        for s, d in edges.itertuples(index=False)
        if int(s) in index_of and int(d) in index_of
    ]
    edge_index = (
        torch.tensor(pairs, dtype=torch.long).t().contiguous()
        if pairs
        else torch.empty((2, 0), dtype=torch.long)
    )

    time_step = torch.tensor(features[1].astype(int).to_numpy(), dtype=torch.long)
    labeled = torch.from_numpy(y >= 0)
    data = Data(x=torch.from_numpy(x), edge_index=edge_index, y=torch.from_numpy(y))
    data.time_step = time_step
    data.train_mask = labeled & (time_step <= TRAIN_MAX_STEP)
    data.test_mask = labeled & (time_step > TRAIN_MAX_STEP)
    return data
