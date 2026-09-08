/** HTTP 狀態碼 → 使用者看得懂的中文訊息。後端有給 detail 時一律優先採用。 */
export function describeError(status: number, detail?: string): string {
  if (detail) return detail
  switch (status) {
    case 0:
      return '無法連線到分析服務，請確認網路後重試。'
    case 400:
      return '請求參數不正確。'
    case 401:
      return '缺少或不正確的 API 金鑰。'
    case 404:
      return '查無資料。'
    case 422:
      return '輸入格式不正確。'
    case 502:
      return '鏈上查詢逾時或失敗，可改用內建範例圖繼續。'
    default:
      return `分析服務回應異常（HTTP ${status}）。`
  }
}
