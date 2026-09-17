import type { GraphPayload } from '../api/types'

/** 圖譜的等效文字替代：把每一條邊列成鄰接表。
 *
 * 網路圖對螢幕閱讀器的可及性評級為 D，不能是資訊的唯一載體——本專案在授信頁
 * 與工作台都遵守這條，出金審查頁原本漏了（該頁只有六條「資金關聯證據鏈」，
 * 涵蓋不到 53 節點／63 邊的全貌）。抽成共用元件以免同一份表格在三頁各寫一次
 * 又各自漂移。
 */
export function EdgeTable({
  payload,
  unit,
  caption,
}: {
  payload: GraphPayload
  /** 金額單位，顯示在欄位標題上（例如 USDT、新台幣元）。 */
  unit: string
  /** 給螢幕閱讀器的表格說明。 */
  caption: string
}) {
  return (
    <>
      <p className="mb-3 text-xs text-muted">
        圖譜對螢幕閱讀器不可讀，此表為等效的文字替代，列出圖中每一條資金流向。
      </p>
      <div className="max-h-80 overflow-auto">
        <table className="tabular w-full text-left text-xs">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 bg-panel text-muted">
            <tr>
              <th scope="col" className="py-2 pr-4 font-normal">
                來源
              </th>
              <th scope="col" className="py-2 pr-4 font-normal">
                目標
              </th>
              <th scope="col" className="py-2 pr-4 font-normal">
                金額（{unit}）
              </th>
            </tr>
          </thead>
          <tbody>
            {payload.edges.map((edge) => (
              <tr key={`${edge.source}->${edge.target}`} className="border-t border-line">
                <td className="py-2 pr-4">{edge.source}</td>
                <td className="py-2 pr-4">{edge.target}</td>
                <td className="py-2 pr-4">{edge.amount.toLocaleString('zh-TW')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
