"""GCN baseline：兩層圖卷積節點分類器。"""

from __future__ import annotations

import torch
import torch.nn.functional as functional
from torch import Tensor, nn
from torch_geometric.nn import GCNConv


class GCN(nn.Module):
    """兩層 GCN，輸出各類別 logits。"""

    def __init__(
        self, in_dim: int, hidden_dim: int = 64, num_classes: int = 2, dropout: float = 0.5
    ) -> None:
        super().__init__()
        self.conv1 = GCNConv(in_dim, hidden_dim)
        self.conv2 = GCNConv(hidden_dim, num_classes)
        self.dropout = dropout

    def forward(self, x: Tensor, edge_index: Tensor) -> Tensor:
        x = torch.relu(self.conv1(x, edge_index))
        x = functional.dropout(x, p=self.dropout, training=self.training)
        return self.conv2(x, edge_index)
