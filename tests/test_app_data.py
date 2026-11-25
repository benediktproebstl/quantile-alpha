"""The app's data files: what is stored must give the same backtest as the full data.

Written by hand (not exported from the notebook). Uses the synthetic market of tests/test_engine.py.
"""
from dataclasses import replace

import pandas as pd
import pytest

pytest.importorskip("pyarrow")

from quantile_alpha import app_data                      # noqa: E402
from quantile_alpha.engine import run_backtest           # noqa: E402
from test_engine import _toy_data                        # noqa: E402


def test_compact_bundle_gives_the_same_backtest_as_the_full_data():
    data, cfg = _toy_data()
    full = run_backtest(data, cfg)
    small = run_backtest(app_data.compact_bundle(data), cfg)
    assert list(small["returns"].columns) == list(full["returns"].columns)
    assert float((small["returns"] - full["returns"]).abs().max().max()) < 1e-12
    assert float((small["metrics"]["ann_return"] - full["metrics"]["ann_return"]).abs().max()) < 1e-12


def test_compact_bundle_keeps_no_daily_prices_or_share_counts():
    data, _ = _toy_data()
    bundle = app_data.compact_bundle(data)
    assert set(bundle) == {"cfg", "panel", "rf", "forms"}
    assert set(bundle["panel"]) == {"ret", "last_month", "sessions"}
    table = next(iter(bundle["forms"].values()))
    assert list(table.columns) == app_data.FORM_COLUMNS
    assert table["mcap"].sum() == pytest.approx(1.0)      # market values are stored as shares of the universe


def test_snapshot_survives_a_round_trip_through_the_files(tmp_path):
    data, cfg = _toy_data()
    bundle = app_data.compact_bundle(data)
    meta = app_data.save_bundle(bundle, tmp_path, retrieved_utc="2000-01-01 00:00", note="test")
    assert app_data.has_bundle(tmp_path) and not app_data.has_bundle(tmp_path / "missing")
    loaded, meta_read = app_data.load_bundle(tmp_path)
    assert meta_read["data_retrieved_utc"] == "2000-01-01 00:00" and meta_read["engine"] == app_data.engine_fingerprint()
    assert loaded["cfg"] == cfg
    before, after = run_backtest(bundle, cfg), run_backtest(loaded, cfg)
    pd.testing.assert_frame_equal(after["returns"], before["returns"], check_freq=False, rtol=0, atol=1e-14)
    assert meta["base_case"] == app_data.base_case_summary(before)
    for key in ("Strategy", cfg.benchmark):               # the stored headline figures are the engine's
        assert meta_read["base_case"][key]["ann_return"] == pytest.approx(float(before["metrics"].loc[key, "ann_return"]), abs=1e-14)


def test_the_assumptions_the_app_changes_work_on_the_compact_bundle():
    data, cfg = _toy_data()
    bundle = app_data.compact_bundle(data)
    for change in (dict(cost_rate=0.005), dict(weighting="equal"), dict(weighting="cap"), dict(buffer=0.0),
                   dict(rebalance_months=(3, 6, 9, 12)), dict(max_weight=1.0, max_cap_multiple=1e9)):
        full, small = run_backtest(data, replace(cfg, **change)), run_backtest(bundle, replace(cfg, **change))
        assert float((small["returns"] - full["returns"]).abs().max().max()) < 1e-12, change
