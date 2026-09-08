# 待補充事項

盤點日期：2026-08-06。依「Demo 當天會不會出事」排序，不是依工作量。

---

## P0 — 網站目前不存在於線上

Demo 網站的 17 個 commit 全在本機 `main`，沒有推送，`web/` 也從未建立過 Vercel 專案。
線上 API 實測 `POST /screen` 與 `POST /graph` 皆回 **404**。在完成以下五項之前，沒有網址可以給任何人。

- [ ] `git push origin main`（本機 main 領先 origin 17 commits）
- [ ] 在 Vercel 建立**第二個專案**指向同一個 repo，Root Directory 設為 `web`，Framework 選 Vite
      （不可併進現有 API 專案，會擾動它的框架偵測——本專案已因此壞過兩次）
- [ ] 該前端專案設環境變數 `VITE_API_BASE` = API 專案網址。**這是建置期烘入的**，改值後必須重新部署才會生效
- [ ] API 專案設 `SMELENS_CORS_ORIGINS` = 前端網址（未設時預設全開，能動但不該長期如此）
- [ ] **部署後驗證 SPA rewrite**：`curl -I https://<前端網址>/screening` 應回 200。
      本機無法證實這件事——`vite preview` 自帶 history fallback 會遮住缺失的 rewrite，
      Playwright 因此也抓不到。若回 404，檢查 `web/vercel.json` 是否隨專案一起部署
- [ ] 部署後實打一次 `/screen` 與 `/graph`，確認新端點真的上線

---

## P1 — Demo 可信度：一句站不住腳的話

- [ ] **`narrative_zh` 宣稱「所屬社群 #N 已知非法佔比 100%」，但沒有任何 ground truth 支撐這句話。**

  劇本圖的節點完全沒有 `label` 屬性（實測全為 `None`）。`smelens/explain/evidence.py:31`
  在偵測不到標籤時會代入代理標籤 `{h.center: 1 for h in motif_hits}`——也就是**把圖樣偵測的
  中心點當成「已知非法」**，再回頭算出社群風險比。結果六個社群有五個是 1.0。

  問題不在數字，在措辭：「已知非法」對法遵背景的評審暗示了獨立的既有情資（黑名單、通報紀錄），
  但實際上它與風險分數同源，是拿同一個訊號當自己的佐證。評審只要問一句
  「你怎麼知道那個社群已知非法？」就很難答。

  這句話會出現在出金審查頁的證據面板與離線快照裡。

  **建議修法**（擇一）：
  - 措辭改為反映其真實來源，例如「所屬社群中命中詐騙圖樣的節點佔比 100%」，並在代理標籤生效時
    於 evidence 加一個旗標讓前端標示「此為圖樣推導，非外部情資」
  - 或替劇本圖補上明確的 `label` 屬性，讓這句話真的有依據

---

## P2 — 本次審查延後的技術債

終審列了 11 項次要發現，以下是其中值得處理的。都不影響正確性。

- [ ] **`/graph` 與 `_build_graph` 的 tron 分支近乎逐行重複**（`smelens/api/main.py`），
      包含三段使用者可見的錯誤字串。任一處改動未同步就會產生不一致的訊息。動到任一端點時順手抽共用
- [ ] `toElements`（`web/src/graph/elements.ts`）不防禦端點不存在的邊。目前後端保證不會發生，
      但這是未被強制的邊界假設，兩行可補
- [ ] `POST /graph` 用 `g.number_of_nodes() == 0` 判空，`/score` 用 `address not in g`。
      實測等價，但風格不一致
- [ ] `describeError` 對 `detail` 用真值判斷，後端若送空字串會落到通用訊息（可能反而是想要的行為，未測）
- [ ] `ServiceStatus`（`web/src/pages/Landing.tsx`）的健康檢查 effect 無 cleanup。
      React 19 下 unmount 後 setState 是無操作，故非缺陷，僅風格
- [ ] Workbench 的掛載 effect 無 abort，StrictMode 開發模式下會送兩次相同的 `/graph` 請求（僅開發期）
- [ ] `dagreLayout` 物件在 `layout === 'cose'` 時仍被建立（無影響）
- [ ] STR 下載在 `anchor.click()` 後立即 `revokeObjectURL`，標準做法但未被測試涵蓋
- [ ] `graph_to_json` 的 `attrs.get("role") or DEFAULT_ROLE` 對空字串也會回退（目前無資料來源會產生）
- [ ] **react-router 的兩項 high 等級 npm audit 公告**（RSC-mode CSRF）。本站是純用戶端 SPA 不走 RSC，
      故不適用；修復需破壞性降版。**對外公開前必須重新確認該公告範圍是否擴大**

---

## P3 — 更早審查的遺留（2026-08-04，與 Demo 網站無關）

這些是前一輪三代理審查列出的中低嚴重度項目，至今未修。按對 Demo 的影響排序：

- [ ] **關聯追溯不檢查時間與金額的連貫性**——路徑可能在時序上不成立，卻仍被當成資金關聯證據。
      評審若細看路徑時間戳可能發現
- [ ] TRON 抓取不分頁，只取 200 筆；且單一 neighbor 失敗會導致整批失敗
- [ ] 無驗證集，z-score 用全資料統計（訓練指標有輕微樂觀偏差）
- [ ] `peeling chain` 偵測不檢查時間遞增
- [ ] Streamlit workbench 無 `session_state`（按下載後結果消失）、無 `st.cache`
- [ ] 滑動窗 distinct 計算是 O(m²)
- [ ] `generate_report.py` 缺 PyYAML 依賴
- [ ] CI 未開啟 uv cache
- [ ] `docs/superpowers/` 的內部計畫與 spec 隨 repo 公開（含實作細節與待修清單）

---

## 明確不做（避免重複討論）

- Streamlit workbench 保留，與網站並存——它是本機重度探索工具，且被 README 與提案書引用
- 網站不暴露 Elliptic 模式——需 203k 節點資料集與數分鐘計算，不適合 serverless
- 不清理 `api/index.py`——已是冗餘薄轉出層，但部署正常運作中
