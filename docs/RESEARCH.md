# ChainLens 研究基礎與定位

> 本文件彙整 2026-07 對「GNN/SNA 加密貨幣詐騙與洗錢金流偵測」主流研究的深度調查
> （14 個研究項目的結構化結果見 `research/results/*.json`、彙整報告見 `research/report.md`），
> 並說明 ChainLens 的設計如何對應文獻、哪些改進已落地、哪些列入 Roadmap。

## 1. 基準與要打的數字（Elliptic 官方時間切分，illicit 類別 F1）

| 模型 | 來源 | Illicit F1 |
|---|---|---|
| Random Forest（全特徵） | Weber et al. 2019 | **0.788** |
| EvolveGCN | Weber et al. 2019 | 0.720 |
| Skip-GCN | Weber et al. 2019 | 0.705 |
| vanilla GCN | Weber et al. 2019 | 0.628 |
| Inspection-L（DGI+GIN 自監督 + RF head） | Lo et al. 2022/23 | ~0.828 |
| **ChainLens Random Forest** | 本專案（2026-07-03 實測） | **0.806** |
| **ChainLens GraphSAGE + RMP** | 本專案（2026-07-03 實測） | **0.661** |
| **ChainLens GraphSAGE（原始 165 維）** | 本專案 | 0.620 |

本專案實測驗證了兩個文獻預期：RF 基線重現 Weber 的 0.788（我們 0.806）；
reverse message passing 讓 GraphSAGE +4.1pp（0.620→0.661，precision 0.581→0.707）。

文獻共識：**先打敗 Random Forest 再談花俏模型**——RF 在工程特徵上勝過 vanilla GCN，
因此本專案已加入 `--model rf` 基線；skip 連接（保留節點自身特徵）是 Skip-GCN > GCN 的關鍵，
GraphSAGE 天然具備此性質。另需注意 time step 43 暗網市場關閉造成的分布漂移：
headline 指標普遍樂觀，illicit F1 / PR-AUC 必須在官方時間切分上報告。

## 2. 領域五大痛點與 ChainLens 的對應

「GNN for Financial Fraud Detection: A Review」（Cheng et al., 2024, arXiv 2411.05815，
100+ 篇綜述）歸納五大挑戰，恰為 ChainLens 的設計靶心：

| 痛點 | 文獻代表 | ChainLens 現況 |
|---|---|---|
| 極度類別不平衡（~2% illicit） | 加權 CE、focal loss、GraphSMOTE、PC-GNN | ✅ 加權 CE + `--loss focal` |
| 異質性/偽裝（詐騙戶連向正常戶） | CARE-GNN→SEC-GFD、DGA-GNN、SCFCRC | ⬜ Roadmap（RMP 部分緩解） |
| 時序動態與漂移 | EvolveGCN、TGN/TGAT、LAS-GNN | ✅ 官方時間切分；⬜ 時序模型 |
| 標註稀缺 | Inspection-L 自監督、主動學習（~5% 標註逼近全監督） | ⬜ Roadmap |
| 可解釋性與落地 | GNNExplainer/PGExplainer/SubgraphX、SEFraud | ✅ 規則圖樣＋證據敘事（by construction） |

## 3. 已落地的研究驅動改進（2026-07-03）

1. **Random Forest 基線**（`--model rf`）：Weber 2019 最強基線；StableAML（arXiv 2602.17842）
   進一步顯示破碎的穩定幣圖上「行為特徵＋樹模型」勝過 GNN——ChainLens 的 SNA 特徵管線
   因此同時服務 RF 與 GNN 兩條線。
2. **Focal loss**（`--loss focal`）：不平衡文獻的標準第一步，聚焦難分類的少數 illicit 樣本。
3. **Reverse message passing GraphSAGE**（`--model sage-rmp`）：Multi-GNN
   （Egressy et al., AAAI 2024，開源 github.com/IBM/Multi-GNN）證明在有向多重交易圖上，
   反向訊息傳遞＋port numbering 貢獻了幾乎全部 ~30% 的 minority-F1 增益
   （GIN 28.7%→57.2%）；交易圖的入邊（誰給我錢）與出邊（我給誰錢）攜帶不同訊號。
4. **Gather-scatter（smurfing）圖樣**：AML typology 文獻（LAS-GNN ICAIF 2025、
   Smurf-based AML、temporal motifs Sci Reports 2024）中 layering 的典型結構——
   同一節點先集資後分散、含時間順序檢查；detections 即證據，可解釋 by construction。

## 4. ChainLens 的差異化定位

商用系統（Chainalysis Reactor、Elliptic Navigator、TRM Labs）的護城河是**專有實體歸屬資料庫**
（交易所合作、傳票、OSINT），演算法不是。VASP 合規工具的五大標配：實體聚類、多跳曝險評分、
typology 庫、視覺化調查圖譜＋證據匯出、持續監控。ChainLens 無法在標註上競爭，
差異化路線是：**透明開源的可解釋層**（中心性百分位＋社群風險＋圖樣命中＋中文調查敘事）
＋ **TRON/USDT 聚焦**（Griffin & Mei 估計殺豬盤年金流 ~$27.8B、~84% 轉為 Tether）＋成本。

## 5. Roadmap（依整合成本排序）

1. **Tether USDT 黑名單作為免費 ground truth**：2025 年 4,163 個地址、$1.26B 遭凍結
   （TRON 佔 ~$506M）——抓取黑名單地址作為 TRON 側正標籤，解決最大的標註缺口。
2. **PGExplainer 即時解釋**：PyG 內建、amortized、CPU 便宜，適合警示分流；
   SubgraphX 保留給高價值深查（連通子圖對合規報告最有價值）。
3. **自監督預訓練（Inspection-L 路線）**：DGI+GIN 嵌入 + RF head 在 Elliptic 達 F1 ~0.828，
   且無標註即可用於 TRON。
4. **PC-GNN 標籤平衡採樣**：一次處理偽裝與不平衡，開源、低整合成本。
5. **時序模型（EvolveGCN / 輕量時序注意力）**：CPU 可行，建模 49 期概念漂移。
6. **Elliptic2 子圖分類**：學習洗錢的「形狀」（122k 標註子圖 / 49M 節點背景圖）——
   與 ChainLens 圖樣層的長期匯合點。
7. **LLM 證據敘事升級（RiskTagger 路線）**：FATF 結構化、證據引用的報告生成
   （開源，84.1% 專家一致率）；敘事必須 evidence-grounded，規則圖樣＋子圖解釋仍是骨幹。
8. **BlazingAML 式多階段圖樣編譯**：把手寫 motif 規則重構為可編譯的模糊多階段模式
   （210–333× 吞吐），支撐即時監控。

## 6. 主要參考文獻

- Weber et al., *Anti-Money Laundering in Bitcoin*, KDD Workshop 2019（arXiv 1908.02591）
- Elmougy & Liu, *Elliptic++*, KDD 2023（arXiv 2306.06108）；Bellei et al., *Elliptic2*, 2024（arXiv 2404.19109）
- Egressy et al., *Provably Powerful GNNs for Directed Multigraphs*, AAAI 2024（arXiv 2306.11586）
- Altman et al., *AMLworld*, NeurIPS 2023 D&B（arXiv 2306.16424）
- Cheng et al., *GNNs for Financial Fraud Detection: A Review*, 2024（arXiv 2411.05815）
- Lo et al., *Inspection-L*；Lin et al., *Focal Loss*, ICCV 2017
- LAS-GNN, ICAIF 2025；*Temporal motifs in cryptocurrency networks*, Sci Reports 2024
- SEFraud（arXiv 2406.11389）；GNNExplainer/PGExplainer/SubgraphX（PyG）
- RiskTagger（arXiv 2510.17848）；UniDetect（arXiv 2604.12329）
- Griffin & Mei, *Pig-butchering economics*, SSRN 4742235；StableAML（arXiv 2602.17842）
- BlazingAML（arXiv 2604.12241）；Collaborative AML, WWW 2025（arXiv 2502.19952）

完整逐項結構化結果（26 欄位×14 項）：`research/results/`；彙整報告：`research/report.md`。
