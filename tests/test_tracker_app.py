"""The tracker app, run without a browser: its figures must be the engine's, and every control must work.

Written by hand (not exported from the notebook). Needs streamlit and the data snapshot in app_data/ (or in the
folder named by QA_APP_DATA); skipped otherwise, because the alternative is a download of several minutes.
"""
import os
import re
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")
pytest.importorskip("pyarrow")

from streamlit.testing.v1 import AppTest                 # noqa: E402

from quantile_alpha import app_data                      # noqa: E402
from quantile_alpha.engine import performance_stats, run_backtest   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FOLDER = Path(os.environ.get("QA_APP_DATA", ROOT / "app_data"))
pytestmark = pytest.mark.skipif(not app_data.has_bundle(FOLDER), reason="no data snapshot for the app")
MINUS = "−"


def start():
    at = AppTest.from_file(str(ROOT / "tracker_app.py"), default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def page_text(at):
    blocks = [re.sub(r"<style.*?</style>|<[^>]+>", " ", getattr(h, "body", "") or "", flags=re.S) for h in at.get("html")]
    return re.sub(r"\s+", " ", " ".join(blocks).replace("&nbsp;", " ").replace("&amp;", "&"))


def pct(x, digits=1):
    return f"{x * 100:.{digits}f}%".replace("-", MINUS)


def num(x):
    return f"{x:.2f}".replace("-", MINUS)


@pytest.fixture(scope="module")
def bundle():
    return app_data.load_bundle(FOLDER)[0]


def test_first_page_shows_the_engines_figures(bundle):
    bt = run_backtest(bundle, bundle["cfg"])
    m = bt["metrics"]
    text = page_text(start())
    value = 10_000 * float((1 + bt["returns"]["Strategy"]).prod())
    assert f"${value:,.0f}" in text
    for field in ("ann_return", "ann_vol", "alpha", "max_drawdown"):
        assert pct(m.loc["Strategy", field]) in text, field
    for field in ("sharpe", "beta", "info_ratio"):
        assert num(m.loc["Strategy", field]) in text, field
    assert pct(m.loc["SPY", "ann_return"]) in text and "120 monthly returns" in text


def test_changing_an_assumption_reruns_the_engine(bundle):
    at = start()
    at.slider(key="cost").set_value(50).run()
    assert not at.exception, at.exception
    expected = run_backtest(bundle, replace(bundle["cfg"], cost_rate=0.005))["metrics"].loc["Strategy", "ann_return"]
    base = run_backtest(bundle, bundle["cfg"])["metrics"].loc["Strategy", "ann_return"]
    text = page_text(at)
    assert pct(expected) in text and f"instead of {pct(base)}" in text and "Trading cost 50 bp" in text


@pytest.mark.parametrize("kind, key, value", [
    ("button_group", "weighting", "equal"), ("button_group", "weighting", "cap"),
    ("button_group", "calendar", "Quarterly"), ("button_group", "calendar", "Yearly"),
    ("select_slider", "limit", 0.05), ("select_slider", "limit", 1.0), ("select_slider", "count", 50),
    ("toggle", "buffer", False), ("slider", "cost", 0)])
def test_every_assumption_can_be_changed(kind, key, value):
    at = start()
    getattr(at, kind)(key=key).set_value(value).run()
    assert not at.exception, at.exception
    assert "instead of" in page_text(at)


def test_benchmarks_and_periods(bundle):
    bt = run_backtest(bundle, bundle["cfg"])
    at = start()
    for bench in ("Universe", "SPMO"):
        at.button_group(key="bench").set_value(bench).run()
        assert not at.exception, at.exception
        r = bt["returns"][["Strategy", bench]].dropna()
        stats = performance_stats(r["Strategy"], bt["rf"].reindex(r.index), r[bench])
        text = page_text(at)
        assert num(stats["info_ratio"]) in text and pct(stats["alpha"]) in text, bench
    at.button_group(key="bench").set_value("SPY").run()
    for period, months in (("1Y", 12), ("3Y", 36), ("5Y", 60)):
        at.button_group(key="range").set_value(period).run()
        assert not at.exception, at.exception
        r = bt["returns"]["Strategy"].iloc[-months:]
        text = page_text(at)
        assert f"{months} monthly returns" in text and f"${10_000 * float((1 + r).prod()):,.0f}" in text, period


def test_an_impossible_combination_is_explained_and_reset_restores_the_prospectus(bundle):
    at = start()
    at.select_slider(key="count").set_value(25).run()
    at.select_slider(key="limit").set_value(0.03).run()
    assert not at.exception, at.exception
    assert "cannot be combined" in page_text(at)
    at.button[0].click().run()
    assert not at.exception, at.exception
    value = 10_000 * float((1 + run_backtest(bundle, bundle["cfg"])["returns"]["Strategy"]).prod())
    assert f"${value:,.0f}" in page_text(at)
