"""Elliptic 載入器測試：以迷你合成 CSV 驗證，不依賴真實資料集。"""

from pathlib import Path

import numpy as np
import pytest

from smelens.data import elliptic

N_FEATURES = 5  # 迷你版特徵數（正式資料為 165）


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    rows = [(101, 1), (102, 1), (103, 34), (104, 35), (105, 35), (106, 49)]
    lines = []
    for i, (tx, t) in enumerate(rows):
        feats = ",".join(str(0.1 * (i + j)) for j in range(N_FEATURES))
        lines.append(f"{tx},{t},{feats}")
    (tmp_path / "elliptic_txs_features.csv").write_text("\n".join(lines))
    (tmp_path / "elliptic_txs_classes.csv").write_text(
        "txId,class\n101,1\n102,2\n103,unknown\n104,1\n105,2\n106,unknown\n"
    )
    (tmp_path / "elliptic_txs_edgelist.csv").write_text(
        "txId1,txId2\n101,102\n102,103\n104,105\n999,101\n"
    )
    return tmp_path


def test_raw_files_exist(raw_dir: Path, tmp_path: Path) -> None:
    assert elliptic.raw_files_exist(raw_dir)
    assert not elliptic.raw_files_exist(tmp_path / "nothing")


def test_load_graph(raw_dir: Path) -> None:
    g = elliptic.load_elliptic_graph(raw_dir)
    assert g.number_of_nodes() == 6
    assert g.number_of_edges() == 3  # 999 不在特徵表中，該邊被剔除
    assert g.nodes[101]["label"] == elliptic.LABEL_ILLICIT
    assert g.nodes[102]["label"] == elliptic.LABEL_LICIT
    assert g.nodes[103]["label"] == elliptic.LABEL_UNKNOWN
    assert g.nodes[106]["time_step"] == 49
    assert len(g.nodes[101]["feat"]) == N_FEATURES
    assert "feat" not in elliptic.load_elliptic_graph(raw_dir, include_features=False).nodes[101]


def test_load_pyg_temporal_split(raw_dir: Path) -> None:
    data = elliptic.load_elliptic_pyg(raw_dir)
    assert data.x.shape == (6, N_FEATURES)
    assert data.edge_index.shape[1] == 3
    # train：t<=34 且有標註 → 101,102；test：t>=35 且有標註 → 104,105
    assert data.train_mask.tolist() == [True, True, False, False, False, False]
    assert data.test_mask.tolist() == [False, False, False, True, True, False]
    assert not (data.train_mask & data.test_mask).any()


def test_extra_features_concat(raw_dir: Path) -> None:
    extra = np.ones((6, 3), dtype=np.float32)
    data = elliptic.load_elliptic_pyg(raw_dir, extra_features=extra)
    assert data.x.shape == (6, N_FEATURES + 3)
    with pytest.raises(ValueError):
        elliptic.load_elliptic_pyg(raw_dir, extra_features=np.ones((2, 3)))
