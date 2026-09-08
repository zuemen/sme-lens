"""GraphSAGE 主模型：兩層 SAGEConv 節點分類器。

輸入可為原始 165 維特徵，或串接 SNA 特徵後的擴充向量（消融比較用）。

reverse_mp=True 時啟用 reverse message passing（Egressy et al., AAAI 2024
"Provably Powerful GNNs for Directed Multigraphs"）：對正向與反向邊各做一次
訊息傳遞後串接——交易圖是有向圖，資金的「來源方向」與「去向方向」攜帶
不同訊號（fan-in 看入邊、fan-out 看出邊），單向傳遞會丟失其一。
"""

from __future__ import annotations

import torch
import torch.nn.functional as functional
from torch import Tensor, nn
from torch_geometric.nn import SAGEConv


class GraphSAGE(nn.Module):
    """兩層 GraphSAGE（可選 reverse message passing），輸出各類別 logits。"""

    def __init__(
        self,
        in_dim: int,
        hidden_dim: int = 64,
        num_classes: int = 2,
        dropout: float = 0.5,
        reverse_mp: bool = False,
    ) -> None:
        super().__init__()
        self.reverse_mp = reverse_mp
        self.dropout = dropout
        self.conv1 = SAGEConv(in_dim, hidden_dim)
        if reverse_mp:
            self.conv1_rev = SAGEConv(in_dim, hidden_dim)
            self.conv2 = SAGEConv(hidden_dim * 2, num_classes)
            self.conv2_rev = SAGEConv(hidden_dim * 2, num_classes)
        else:
            self.conv2 = SAGEConv(hidden_dim, num_classes)

    def forward(self, x: Tensor, edge_index: Tensor) -> Tensor:
        if self.reverse_mp:
            reverse_edges = edge_index.flip(0)
            h = torch.cat(
                [self.conv1(x, edge_index), self.conv1_rev(x, reverse_edges)], dim=1
            )
            h = functional.dropout(torch.relu(h), p=self.dropout, training=self.training)
            return self.conv2(h, edge_index) + self.conv2_rev(h, reverse_edges)
        h = torch.relu(self.conv1(x, edge_index))
        h = functional.dropout(h, p=self.dropout, training=self.training)
        return self.conv2(h, edge_index)
