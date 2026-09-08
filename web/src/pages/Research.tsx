import { Panel } from '../components/Panel'

const METRICS = [
  { model: 'GCN', features: '原始 165 維', p: 0.48, r: 0.535, f1: 0.506, auc: 0.524 },
  { model: 'GraphSAGE', features: '原始 165 維', p: 0.581, r: 0.666, f1: 0.62, auc: 0.671 },
  { model: 'GraphSAGE', features: '原始 + SNA（消融）', p: 0.552, r: 0.66, f1: 0.601, auc: 0.648 },
  { model: 'GraphSAGE + RMP', features: '原始 165 維', p: 0.707, r: 0.621, f1: 0.661, auc: 0.692 },
  { model: 'Random Forest', features: '原始 165 維', p: 0.907, r: 0.725, f1: 0.806, auc: 0.795 },
]

const FINDINGS = [
  {
    title: 'Random Forest 仍是最強基線',
    body: 'F1 0.806、PR-AUC 0.795，重現 Weber et al. 2019 的 RF≈0.79–0.83。GNN 未必優於樹模型。',
  },
  {
    title: 'Reverse message passing 讓 GraphSAGE F1 +4.1pp',
    body: '0.620 → 0.661。有向交易圖的入邊與出邊訊號確實互補（AAAI 2024 Multi-GNN）。',
  },
  {
    title: '串接 SNA 特徵未提升 F1',
    body: '0.601 vs 0.620。GNN 的訊息傳遞已隱含學到局部結構——SNA 在本系統的價值在可解釋層，不在特徵層。',
  },
]

export default function Research() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">研究成果</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          遵守 Elliptic 官方時間切分（train ≤ 34 期 / test ≥ 35 期）避免資料洩漏。
          以下為 illicit 類別指標，五列為同一次完整資料集實測。
        </p>
      </div>

      <Panel title="模型指標（illicit 類別）">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-muted">
              <tr>
                {['模型', '特徵', 'Precision', 'Recall', 'F1', 'PR-AUC'].map((head) => (
                  <th key={head} className="py-2 pr-4 font-normal">
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRICS.map((row) => (
                <tr key={`${row.model}-${row.features}`} className="border-t border-line">
                  <td className="py-2 pr-4">{row.model}</td>
                  <td className="py-2 pr-4 text-muted">{row.features}</td>
                  <td className="tabular py-2 pr-4">{row.p.toFixed(3)}</td>
                  <td className="tabular py-2 pr-4">{row.r.toFixed(3)}</td>
                  <td className="tabular py-2 pr-4">{row.f1.toFixed(3)}</td>
                  <td className="tabular py-2 pr-4">{row.auc.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-muted">
          訓練設定：CPU、200 epochs、hidden 64、lr 0.01、加權 CrossEntropy（逆類別頻率）、
          weight decay 5e-4、seed 42；SNA 特徵為 in/out degree、PageRank、k-core、
          近似 betweenness（64 源點）之 z-score。
        </p>
      </Panel>

      <section className="grid gap-5 md:grid-cols-3">
        {FINDINGS.map((finding) => (
          <Panel key={finding.title} title={finding.title}>
            <p className="text-sm leading-relaxed text-muted">{finding.body}</p>
          </Panel>
        ))}
      </section>

      <Panel title="研究基礎">
        <p className="text-sm leading-relaxed text-muted">
          設計選擇與改進方向根據對 14 個主流研究方向的深度調查：Elliptic／Elliptic2 基準、
          IBM Multi-GNN、時序 GNN、洗錢 typology、異質性 GNN、GNN 可解釋性、LLM + 圖、
          TRON／USDT 實證、商用系統、聯邦與隱私 AML 等。完整定位、五大領域痛點對應表與
          Roadmap 見 repo 的 <span className="tabular">docs/RESEARCH.md</span>。
        </p>
      </Panel>
    </div>
  )
}
