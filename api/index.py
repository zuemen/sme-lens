"""Vercel Python serverless 進入點：直接匯出 FastAPI ASGI app。

Vercel 偵測 api/ 下的檔案為 serverless function；vercel.json 的 rewrite
把所有路徑導到這裡，交由 FastAPI 內部路由（/score、/health、/docs）。
"""

from smelens.api.main import app

__all__ = ["app"]
