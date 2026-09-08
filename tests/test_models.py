"""GNN 訓練管線測試：小型合成圖冒煙，不依賴真實資料集。"""

from pathlib import Path

import pytest

from smelens.models import train


@pytest.mark.parametrize("model_type", ["gcn", "sage", "sage-rmp"])
def test_train_and_evaluate(model_type: str, tmp_path: Path) -> None:
    data = train.build_synthetic_data(num_nodes=60, num_features=16, seed=1)
    metrics = train.train_and_evaluate(
        data, model_type=model_type, epochs=5, hidden_dim=8, checkpoint_dir=tmp_path
    )
    assert set(metrics) == set(train.METRIC_KEYS)
    assert all(0.0 <= v <= 1.0 for v in metrics.values())
    assert (tmp_path / f"{model_type}.pt").exists()


def test_random_forest_baseline(tmp_path: Path) -> None:
    data = train.build_synthetic_data(num_nodes=60, num_features=16, seed=1)
    metrics = train.train_and_evaluate(data, model_type="rf", checkpoint_dir=tmp_path)
    assert set(metrics) == set(train.METRIC_KEYS)
    assert all(0.0 <= v <= 1.0 for v in metrics.values())
    assert (tmp_path / "rf.joblib").exists()


def test_focal_loss_training(tmp_path: Path) -> None:
    data = train.build_synthetic_data(num_nodes=60, num_features=16, seed=1)
    metrics = train.train_and_evaluate(
        data, model_type="sage", epochs=5, hidden_dim=8, checkpoint_dir=tmp_path,
        loss="focal",
    )
    assert set(metrics) == set(train.METRIC_KEYS)
    with pytest.raises(ValueError):
        train.train_and_evaluate(data, model_type="sage", epochs=1, loss="nope")


def test_focal_loss_formula() -> None:
    """pt 須由無權重 CE 還原（真實機率），α 權重於調變因子外另乘。"""
    import torch

    logits = torch.tensor([[2.0, -1.0], [0.5, 1.5], [-1.0, 3.0]])
    targets = torch.tensor([0, 1, 1])
    weight = torch.tensor([1.0, 5.0])
    gamma = 2.0

    ce_raw = torch.nn.functional.cross_entropy(logits, targets, reduction="none")
    pt = torch.exp(-ce_raw)  # = softmax(logits)[target]，真實機率
    expected = (weight[targets] * (1.0 - pt) ** gamma * ce_raw).mean()
    actual = train._focal_loss(logits, targets, weight, gamma=gamma)
    assert torch.allclose(actual, expected)
    # 易分類樣本（pt 高）須被大幅降權：focal 遠小於加權 CE
    weighted_ce = torch.nn.functional.cross_entropy(logits, targets, weight=weight)
    assert actual < weighted_ce


def test_synthetic_masks_disjoint() -> None:
    data = train.build_synthetic_data(num_nodes=40, num_features=8, seed=2)
    assert not (data.train_mask & data.test_mask).any()
    assert data.train_mask.sum() > 0
    assert data.test_mask.sum() > 0


def test_unknown_model_type() -> None:
    data = train.build_synthetic_data(num_nodes=20, num_features=4)
    with pytest.raises(ValueError):
        train.train_and_evaluate(data, model_type="mlp")
