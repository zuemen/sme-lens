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
    assert result["risk_score"] == pytest.approx(0.7307, abs=1e-4)
