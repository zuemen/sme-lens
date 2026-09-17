"""Vercel Python serverless 進入點：直接匯出 FastAPI ASGI app。

Vercel 只把 api/ 目錄下的檔案當 serverless function，所以進入點必須是這個
檔案——vercel.json 的 functions 鍵也必須寫 "api/index.py"，寫成模組真正的位置
（smelens/api/main.py）會匹配不到任何 function，build 直接失敗。

vercel.json 另有一條 rewrite 把所有路徑導到這裡，交由 FastAPI 內部路由
（/credit、/group、/gcis/group、/screen、/graph、/score、/health、/docs）。
少了那條 rewrite 時 build 會過，但每一個 API 路徑都會落到靜態檔案查找而回
404——曾經實際發生過，且只看 /health（它剛好被靜態站台或舊部署接走）是驗不
出來的。部署後至少要對 /credit 與 /group 各打一次確認 200。
"""

from smelens.api.main import app

__all__ = ["app"]
