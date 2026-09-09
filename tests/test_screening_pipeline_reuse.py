"""screen_withdrawal 的選配 pipeline 參數：重用不得改變結果。"""

from __future__ import annotations

import pytest

from smelens.data import scenario
from smelens.explain.evidence import run_pipeline
from smelens.explain.screening import screen_withdrawal


def test_passing_precomputed_pipeline_gives_identical_result() -> None:
    g = scenario.load_withdrawal_scenario()
    fresh = screen_withdrawal(g, "TOtcOut01", 500000.0)
    reused = screen_withdrawal(g, "TOtcOut01", 500000.0, pipeline=run_pipeline(g))
    assert fresh == reused


def test_default_pipeline_argument_keeps_existing_behaviour() -> None:
    g = scenario.load_withdrawal_scenario()
    result = screen_withdrawal(g, "TOtcOut01", 500000.0)
    # 0.7307 → 0.6596：數字改變是因為社群風險比標註缺陷被修正（不再把整個社群
    # 灌高成 1.0），與本測試要驗證的「重用/自建 pipeline 結果一致」無關。
    assert result["risk_score"] == pytest.approx(0.6596, abs=1e-4)
