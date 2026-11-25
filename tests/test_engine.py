"""Engine tests.

AUTO-GENERATED from Financial_Modeling_Quantile_Alpha.ipynb by tools/export_engine.py.
Do not edit by hand: change the notebook cell marked "# [tests]" and re-export.
"""
from quantile_alpha.engine import *  # noqa: F401,F403


# [tests] exported to the repo by tools/export_engine.py - see the README
_TOY_CFG = Config(first_holding_month="2020-01", last_holding_month="2021-12", benchmark="MKT", momentum_fund="MKT",
                  max_weight=0.6)                    # with 12 toy stocks a 9% limit could not be met


def _toy_market(seed=7, shock_after=None):
    """Synthetic daily market: 12 stocks + a calendar ticker, with an IPO, a gap, a delisting, index changes and a
    share count reported about every three months. With `shock_after`, every price and every share count after
    that day is rewritten."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2018-01-01", "2021-12-31")
    names = [f"S{i:02d}" for i in range(12)]
    steps = rng.normal(0.0004, 0.015, (len(days), len(names)))
    adj = pd.DataFrame(100.0 * np.exp(np.cumsum(steps, axis=0)), index=days, columns=names)
    reported = days[::63]
    drift = np.exp(np.cumsum(rng.normal(0.0, 0.02, (len(reported), len(names))), axis=0))
    shares = pd.DataFrame(1e6 * np.arange(1, len(names) + 1) * drift, index=reported, columns=names)
    if shock_after is not None:                      # rewrite the future: every later price and share count is changed
        later = adj.index > pd.Timestamp(shock_after)
        adj.loc[later] = adj.loc[later] * rng.uniform(0.3, 3.0, (int(later.sum()), len(names)))
        later = shares.index > pd.Timestamp(shock_after)
        shares.loc[later] = shares.loc[later] * rng.uniform(0.3, 3.0, (int(later.sum()), len(names)))
    adj["MKT"] = 100.0 * np.exp(np.cumsum(np.full(len(days), 0.0003)))
    adj.loc[adj.index > "2020-08-14", "S03"] = np.nan           # delisted in mid-August 2020
    adj.loc[adj.index < "2019-03-01", "S05"] = np.nan           # IPO in March 2019
    june_end = adj.loc["2019-06"].index[-1]
    adj.loc[june_end, "S04"] = np.nan                           # no quote on the last session of June 2019
    panel = build_monthly_panel(adj, adj.copy(), adj.notna() * 1e6, "MKT")
    panel["price_only_factor"] = price_only_factors(pd.DataFrame(0.0, index=days, columns=adj.columns), panel["sessions"])
    counts = {n: shares[n] for n in names}
    add_market_caps(panel, counts, _TOY_CFG)
    spells = pd.DataFrame({"ticker": names, "name": names, "start": pd.NaT, "end": pd.NaT,
                           "reason_in": "", "reason_out": "", "sector": None})
    spells["start"] = pd.to_datetime(spells["start"]); spells["end"] = pd.to_datetime(spells["end"])
    spells.loc[spells.ticker == "S06", "start"] = pd.Timestamp("2020-02-10")   # joins the index
    spells.loc[spells.ticker == "S07", "end"] = pd.Timestamp("2020-05-20")     # leaves the index
    mapped = map_spells_to_yahoo(spells, panel["first_date"], "2018-01-01")
    rf = pd.Series(0.001, index=panel["sessions"].index)
    return adj, panel, mapped, rf, counts


def test_trade_reference_and_measurement_months_match_the_published_example():
    # S&P methodology, Appendix A, note 1: rebalancing effective in March 2014, reference date 28 February 2014,
    # momentum value from the prices of 31 January 2014 and 31 January 2013
    cfg = Config()
    trade = P("2014-03")
    reference = trade - cfg.reference_lag
    assert reference == P("2014-02")
    assert reference - cfg.skip == P("2014-01") and reference - cfg.skip - cfg.lookback == P("2013-01")
    assert reference - cfg.skip - cfg.fallback_lookback == P("2013-04")       # nine months of history instead of twelve


def test_momentum_value_skips_the_latest_month_and_volatility_uses_daily_price_changes():
    adj, panel, mapped, rf, _ = _toy_market()
    m = P("2020-08")                                                           # reference month
    x = momentum_inputs(panel, m, _TOY_CFG)
    close, daily, sessions = panel["px_signal"], panel["daily_close"], panel["sessions"]
    assert abs(x.loc["S00", "value"] - (close.loc[P("2020-07"), "S00"] / close.loc[P("2019-07"), "S00"] - 1.0)) < 1e-12
    window = daily.loc[sessions[P("2019-07")]:sessions[P("2020-07")], "S00"]
    changes = (window / window.shift(1) - 1.0).iloc[1:]
    assert abs(x.loc["S00", "vol"] - changes.std(ddof=1)) < 1e-15 and x.loc["S00", "days"] == len(changes) and x.loc["S00", "months"] == 12
    later = dict(panel)                                                        # prices of the reference month and after
    later["px_signal"] = close.copy(); later["px_signal"].loc[P("2020-08"):, "S00"] *= 5.0
    later["daily_close"] = daily.copy(); later["daily_close"].loc[sessions[P("2020-07")] + pd.Timedelta(days=1):, "S00"] *= 5.0
    y = momentum_inputs(later, m, _TOY_CFG)
    assert y.loc["S00", "value"] == x.loc["S00", "value"] and y.loc["S00", "vol"] == x.loc["S00", "vol"]   # ... do not enter
    ipo = momentum_inputs(panel, P("2020-01"), _TOY_CFG).loc["S05"]            # listed March 2019: no price 13 months back
    assert ipo["months"] == 9
    assert abs(ipo["value"] - (close.loc[P("2019-12"), "S05"] / close.loc[P("2019-03"), "S05"] - 1.0)) < 1e-12


def test_momentum_score_formula_and_cap_at_three():
    value = pd.Series([0.10, 0.20, 0.30], index=list("ABC")); vol = pd.Series([0.01, 0.02, 0.01], index=list("ABC"))
    x, z, score = momentum_score(value, vol)
    assert np.allclose(x, [10.0, 10.0, 30.0])                                  # risk-adjusted value
    sd = np.std([10.0, 10.0, 30.0], ddof=1); mean = 50.0 / 3.0
    assert np.allclose(z, [(10 - mean) / sd, (10 - mean) / sd, (30 - mean) / sd])
    assert abs(score["C"] - (1.0 + z["C"])) < 1e-12 and abs(score["A"] - 1.0 / (1.0 - z["A"])) < 1e-12
    raw = momentum_score(value, vol, risk_adjust=False)[0]
    assert np.allclose(raw, value)                                             # without risk adjustment the plain value is ranked
    wide = pd.Series(np.r_[np.zeros(40), 100.0, -100.0], index=[f"N{i}" for i in range(42)])
    _, zw, sw = momentum_score(wide, pd.Series(1.0, index=wide.index))
    assert zw.max() == 3.0 and zw.min() == -3.0 and sw.max() == 4.0 and abs(sw.min() - 0.25) < 1e-12
    flat = momentum_score(pd.Series([1.0, 1.0]), pd.Series([1.0, 1.0]))
    assert (flat[1] == 0).all() and (flat[2] == 1.0).all()                     # no dispersion: every score is 1


def test_groups_equal_count_extra_names_to_highest_and_ties_by_identifier():
    score = pd.Series(np.arange(23, dtype=float), index=[f"T{i:02d}" for i in range(23)])
    g = assign_groups(score, 5)
    assert g.value_counts().sort_index().tolist() == [4, 4, 5, 5, 5]
    assert g.notna().all() and set(g.unique()) == {1.0, 2.0, 3.0, 4.0, 5.0}
    tied = pd.Series([0.1, 0.1, 0.1, 0.1], index=["D", "B", "C", "A"])
    gt = assign_groups(tied, 2)
    assert gt["A"] == 1 and gt["B"] == 1 and gt["C"] == 2 and gt["D"] == 2      # alphabetical tie-break
    with_nan = pd.Series([0.3, np.nan, 0.1], index=["X", "Y", "Z"])
    gn = assign_groups(with_nan, 2)
    assert np.isnan(gn["Y"]) and gn["Z"] == 1 and gn["X"] == 2
    for n in (5, 10, 20):
        sizes = assign_groups(pd.Series(np.random.default_rng(1).normal(size=487)), n).value_counts()
        assert sizes.max() - sizes.min() <= 1 and sizes.sum() == 487


def test_buffer_rule_keeps_holdings_near_the_cut_off():
    ranked = list("ABCDEFGHIJKL")
    assert select_with_buffer(ranked, set(), 5, 0.2) == list("ABCDE")          # nothing held: the best five
    assert select_with_buffer(ranked, {"F", "X"}, 5, 0.2) == list("ABCDF")     # F is held and ranks sixth: kept, E waits
    assert select_with_buffer(ranked, {"G"}, 5, 0.2) == list("ABCDE")          # rank seven is outside the buffer
    assert select_with_buffer(ranked, {"E", "F"}, 5, 0.2) == list("ABCDE")     # E fills the last place before F is reached
    assert select_with_buffer(ranked, {"F"}, 5, 0.0) == list("ABCDE")          # no buffer
    assert select_with_buffer(ranked, {"K", "L"}, 10, 0.2) == list("ABCDEFGH") + ["K", "L"]   # ranks 11 and 12 kept
    assert select_with_buffer(ranked, {"L"}, 10, 0.2) == list("ABCDEFGH") + ["L", "I"]        # then the best newcomer
    assert len(select_with_buffer(ranked, set(ranked), 5, 0.2)) == 5


def test_weights_follow_market_value_times_score_and_respect_both_limits():
    assert np.allclose(capped_weights(pd.Series([6.0, 3.0, 1.0]), pd.Series([0.4, 0.4, 0.4])), [0.4, 0.4, 0.2])
    rng = np.random.default_rng(4)
    names = [f"N{i:02d}" for i in range(30)]
    t = pd.DataFrame({"mcap": np.r_[[900.0, 700.0, 500.0], rng.uniform(5, 60, 27)], "score": rng.uniform(1.5, 4.0, 30)}, index=names)
    t["uw"] = t["mcap"] / (4.0 * t["mcap"].sum())                              # the selected stocks are a quarter of the universe
    cfg = Config()
    w, multiple = strategy_weights(t, names, cfg)
    cap_w = t["mcap"] / t["mcap"].sum()
    assert abs(w.sum() - 1.0) < 1e-12 and (w > 0).all() and multiple == 3.0
    assert (w <= 0.09 + 1e-12).all() and (w <= 3.0 * cap_w + 1e-12).all()      # both limits hold
    free = (w < 0.09 - 1e-9) & (w < 3.0 * cap_w - 1e-9)
    ratio = (w / (t["mcap"] * t["score"]))[free]
    assert free.sum() > 5 and np.allclose(ratio, ratio.iloc[0])                # the others stay proportional to value x score
    assert abs(w["N00"] - 0.09) < 1e-12                                        # the largest company sits at the 9% limit
    plain, _ = strategy_weights(t, names, cfg, capped=False)
    assert np.allclose(plain, t["mcap"] * t["score"] / (t["mcap"] * t["score"]).sum())
    assert np.allclose(strategy_weights(t, names, cfg, weighting="cap", capped=False)[0], cap_w)
    assert np.allclose(strategy_weights(t, names, cfg, weighting="equal")[0], 1.0 / 30)
    second, m2 = strategy_weights(t, names, replace(cfg, cap_reference="universe"))
    assert m2 > 3.0 and abs(second.sum() - 1.0) < 1e-12 and (second <= m2 * t["uw"] + 1e-12).all()   # 3 x universe weight is too tight
    try:
        strategy_weights(t, names[:5], cfg)
        raise AssertionError("five stocks cannot each stay below 9%")
    except ValueError:
        pass


def test_weights_drift_from_the_reference_date_and_untradable_stocks_are_dropped():
    m = P("2020-03")
    f = pd.DataFrame({"mcap": [100.0, 100.0, 200.0], "score": 1.0, "uw": [0.25, 0.25, 0.5], "rank": [1, 2, 3], "group": [5.0, 5.0, 5.0],
                      "drift": [1.10, 1.00, 0.50], "tradable": [True, True, False], "carried_back": False}, index=list("ABC"))
    targets, log = build_targets({m: f}, [m], Config(), "all", weighting="cap", capped=False)
    w = targets[m]
    assert list(w.index) == ["A", "B"]                                         # C left the index before the trade date
    assert abs(w["A"] - 110.0 / 210.0) < 1e-12 and abs(w.sum() - 1.0) < 1e-12  # weights moved with prices since the reference date
    assert log.loc[m, "selected"] == 3 and log.loc[m, "bought"] == 2


def test_membership_replay_has_no_future_additions():
    cons = pd.DataFrame({"Symbol": ["AAA", "BBB", "CCC"], "Security": ["A", "B", "C"], "GICS Sector": ["x", "y", "z"]})
    chg = pd.DataFrame([["June 15, 2020", "CCC", "C", "DDD", "D", "swap", ""],
                        ["March 1, 2019", "BBB", "B", "EEE", "E", "swap", ""]])
    spells, issues = build_spells(cons, chg, cutoff="2018-01-01")
    assert issues.empty
    assert set(members_on(spells, "2019-01-31")["ticker"]) == {"AAA", "EEE", "DDD"}
    assert set(members_on(spells, "2019-12-31")["ticker"]) == {"AAA", "BBB", "DDD"}
    assert set(members_on(spells, "2020-06-14")["ticker"]) == {"AAA", "BBB", "DDD"}      # day before the change
    assert set(members_on(spells, "2020-06-15")["ticker"]) == {"AAA", "BBB", "CCC"}      # effective date
    _, bad = build_spells(cons, pd.DataFrame([["June 15, 2020", "ZZZ", "Z", None, None, "?", ""]]), cutoff="2018-01-01")
    assert len(bad) == 1                                                                   # unmatched entries are reported


def test_month_end_prices_use_the_final_session_and_are_not_forward_filled():
    adj, panel, mapped, rf, _ = _toy_market()
    june_end = adj.loc["2019-06"].index[-1]
    assert panel["sessions"][P("2019-06")] == june_end
    assert np.isnan(panel["px"].loc[P("2019-06"), "S04"])                # stale price is not a month-end price
    assert bool(panel["stale"].loc[P("2019-06"), "S04"])
    assert not np.isnan(panel["ret"].loc[P("2019-06"), "S04"])           # but a held position is still valued
    u = universe_at(P("2019-06"), mapped, panel, _TOY_CFG).set_index("ticker")
    assert u.loc["S04", "status"] == "no valid price on the reference date"


def test_universe_respects_membership_dates_listing_history_and_share_counts():
    adj, panel, mapped, rf, counts = _toy_market()
    def status(month, cfg=_TOY_CFG, p=panel):
        return universe_at(P(month), mapped, p, cfg).set_index("ticker")["status"]
    assert "S06" not in status("2019-12").index                            # not yet a member
    assert status("2020-03")["S06"] == "eligible"                          # joined 10 Feb 2020, has a full price history
    assert "S07" in status("2020-03").index and "S07" not in status("2020-06").index
    assert status("2019-12")["S05"] == "listed too recently for the signal"   # IPO March 2019: not even nine months
    assert status("2020-01")["S05"] == "eligible"                          # nine months of prices before the skipped month
    assert status("2020-01", replace(_TOY_CFG, min_trading_days=200))["S05"] == "too few trading days in the measurement period"
    no_count = dict(panel); add_market_caps(no_count, {k: v for k, v in counts.items() if k != "S02"}, _TOY_CFG)
    assert status("2020-03", p=no_count)["S02"] == "no share count on Yahoo"
    FOREIGN_PRICES_BEFORE["S00"] = "2020-06-01"                            # as if Yahoo's earlier S00 prices were another company's
    try:
        assert status("2020-03")["S00"] == "ticker reused: Yahoo series belongs to another issuer"
        assert status("2020-06")["S00"] == "eligible"
    finally:
        del FOREIGN_PRICES_BEFORE["S00"]
    assert "S03" not in formation_table(P("2020-10"), mapped, panel, _TOY_CFG)[0].index   # no price after the delisting
    may = formation_table(P("2020-05"), mapped, panel, _TOY_CFG)[0]        # reference April: S07 is still a member ...
    assert "S07" in may.index and not may.loc["S07", "tradable"] and may.loc["S00", "tradable"]   # ... but not on the trade date
    aug = formation_table(P("2020-08"), mapped, panel, _TOY_CFG)[0]        # S03 stops trading before the August trade date
    assert "S03" in aug.index and not aug.loc["S03", "tradable"]


def test_rebalance_cost_is_exact_and_never_charged_twice():
    c = 0.001
    v, trades, cost = solve_rebalance(100.0, np.zeros(2), np.array([0.5, 0.5]), c)
    assert abs(v - 100.0 / 1.001) < 1e-12 and abs(v + cost - 100.0) < 1e-12
    assert abs(cost - c * np.abs(trades).sum()) < 1e-15
    v2, trades2, cost2 = solve_rebalance(100.0, np.array([60.0, 40.0]), np.array([0.5, 0.5]), c)
    assert abs(cost2 - 0.02) < 1e-12 and abs(v2 - 99.98) < 1e-12           # $20 traded in total
    v3, trades3, cost3 = solve_rebalance(100.0, np.array([50.0, 50.0]), np.array([0.5, 0.5]), c)
    assert cost3 == 0.0 and v3 == 100.0                                    # already on target: nothing to pay
    v4, _, cost4 = solve_rebalance(100.0, np.array([100.0, 0.0]), np.array([0.0, 0.0]), c)
    assert abs(cost4 - 0.1) < 1e-12 and abs(v4 - 99.9) < 1e-12             # selling everything


def test_nav_starts_at_one_costs_hit_the_next_month_and_weights_drift():
    months = pd.period_range("2020-01", "2020-07", freq="M")
    ret = pd.DataFrame({"A": [np.nan, 0.10, 0.00, 0.05, -0.02, 0.01, 0.03],
                        "B": [np.nan, -0.04, 0.02, 0.01, 0.03, 0.00, -0.01]}, index=months)
    rf = pd.Series(0.0, index=months)
    half = pd.Series({"A": 0.5, "B": 0.5})
    c = 0.001
    run = simulate(ret, rf, {P("2020-01"): half, P("2020-04"): half}, c, P("2020-01"), P("2020-07"))
    gross = simulate(ret, rf, {P("2020-01"): half, P("2020-04"): half}, 0.0, P("2020-01"), P("2020-07"))
    assert run["nav"].iloc[0] == 1.0 and gross["nav"].iloc[0] == 1.0       # initial NAV is 1 before costs
    v0 = 1.0 / (1.0 + c)
    assert abs(run["nav"][P("2020-02")] - v0 * (1 + 0.5 * 0.10 + 0.5 * -0.04)) < 1e-12
    assert abs(gross["ret"][P("2020-02")] - 0.03) < 1e-12
    assert run["ret"][P("2020-02")] < gross["ret"][P("2020-02")]           # the launch cost lowers the first month
    hA = 0.5 * v0 * 1.10 * 1.00 * 1.05; hB = 0.5 * v0 * 0.96 * 1.02 * 1.01   # three months of drift, no trading
    assert abs(run["nav"][P("2020-04")] - (hA + hB)) < 1e-12
    v_net, _, cost = solve_rebalance(hA + hB, np.array([hA, hB]), np.array([0.5, 0.5]), c)
    assert abs(run["nav"][P("2020-05")] - v_net * (1 + 0.5 * -0.02 + 0.5 * 0.03)) < 1e-12
    assert list(run["rebalances"].index) == [P("2020-01"), P("2020-04")]   # no trading in between
    assert abs(run["rebalances"].loc[P("2020-01"), "one_way_turnover"] - 1.0) < 1e-12
    drifted = hA / (hA + hB)
    assert abs(run["rebalances"].loc[P("2020-04"), "one_way_turnover"] - abs(0.5 - drifted)) < 1e-12
    assert abs(np.prod(1 + run["ret"]) - run["nav"].iloc[-1]) < 1e-12       # returns reconcile with NAV
    assert abs(run["monthly"].loc[P("2020-04"), "max_weight"] - drifted) < 1e-12


def test_rebalancing_schedules_for_all_frequencies():
    assert schedule(P("2019-12"), P("2020-12"), (3, 9)) == [P("2019-12"), P("2020-03"), P("2020-09")]
    assert schedule(P("2019-12"), P("2020-12"), (3, 6, 9, 12)) == [P("2019-12"), P("2020-03"), P("2020-06"), P("2020-09")]
    assert len(schedule(P("2019-12"), P("2020-12"), tuple(range(1, 13)))) == 12
    assert schedule(P("2020-01"), P("2020-08"), (3, 9))[0] == P("2020-01")              # the launch month always trades
    assert schedule(P("2015-12"), P("2025-12"), Config().rebalance_months)[-1] == P("2025-09")


def test_delisting_proceeds_become_cash_earn_the_risk_free_rate_and_are_reinvested():
    months = pd.period_range("2020-01", "2020-07", freq="M")
    ret = pd.DataFrame({"X": [np.nan, 0.02, 0.20, np.nan, np.nan, np.nan, np.nan],
                        "Y": [np.nan, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]}, index=months)
    rf = pd.Series(0.002, index=months)
    last_month = pd.Series({"X": P("2020-03"), "Y": pd.NaT})
    targets = {P("2020-01"): pd.Series({"X": 0.5, "Y": 0.5}), P("2020-06"): pd.Series({"Y": 1.0})}
    run = simulate(ret, rf, targets, 0.0, P("2020-01"), P("2020-07"), last_month)
    x_end = 0.5 * 1.02 * 1.20
    y = 0.5 * 1.01 ** 3
    assert abs(run["nav"][P("2020-04")] - (x_end * 1.002 + y)) < 1e-12      # cash earns RF from April on
    assert abs(run["monthly"].loc[P("2020-04"), "cash_weight"] - x_end * 1.002 / (x_end * 1.002 + y)) < 1e-12
    assert len(run["events"]) == 1 and run["events"][0]["security"] == "X"
    v_june = x_end * 1.002 ** 3 + 0.5 * 1.01 ** 5
    assert abs(run["nav"][P("2020-07")] - v_june * 1.01) < 1e-12            # everything reinvested in Y in June
    try:                                                                     # a missing return with no explanation
        simulate(ret, rf, targets, 0.0, P("2020-01"), P("2020-07"), None)
        raise AssertionError("an unexplained missing return must stop the backtest")
    except ValueError:
        pass


def test_terminal_month_return_uses_the_last_quote():
    adj, panel, mapped, rf, _ = _toy_market()
    assert panel["last_month"]["S03"] == P("2020-08") and pd.isna(panel["last_month"]["S00"])
    last_quote = adj["S03"].dropna().iloc[-1]
    july_end = adj.loc[panel["sessions"][P("2020-07")], "S03"]
    assert abs(panel["ret"].loc[P("2020-08"), "S03"] - (last_quote / july_end - 1.0)) < 1e-12
    assert np.isnan(panel["ret"].loc[P("2020-09"), "S03"])                  # never replaced by zero


def test_risk_free_uses_only_published_yields_and_converts_annual_percent_to_monthly():
    sessions = pd.Series(pd.to_datetime(["2020-12-31", "2021-01-29", "2021-02-26"]),
                         index=pd.period_range("2020-12", "2021-02", freq="M"))
    y = pd.Series([2.0, 2.0, 5.0, 3.0, np.nan, 4.0],
                  index=pd.to_datetime(["2020-12-29", "2020-12-30", "2020-12-31", "2021-01-28", "2021-01-29", "2021-02-01"]))
    rf = monthly_rf(y, sessions)
    assert abs(rf[P("2021-01")] - (1.02 ** (1 / 12) - 1)) < 1e-15           # the 31 Dec value is not yet published
    assert abs(rf[P("2021-02")] - (1.03 ** (1 / 12) - 1)) < 1e-15           # last value before 29 Jan
    assert 0.0016 < rf[P("2021-01")] < 0.0017                               # a monthly decimal, not 2.0 or 0.02


def test_metric_formulas_alpha_is_annualised_and_beta_is_not():
    rng = np.random.default_rng(3)
    idx = pd.period_range("2015-01", periods=96, freq="M")
    rf = pd.Series(0.001, index=idx)
    bench = pd.Series(rng.normal(0.008, 0.04, 96), index=idx)
    r = 0.002 + 1.3 * (bench - rf) + rf + pd.Series(rng.normal(0, 0.01, 96), index=idx)
    s = performance_stats(r, rf, bench)
    ex, bex = (r - rf).to_numpy(), (bench - rf).to_numpy()
    beta = np.cov(ex, bex, ddof=1)[0, 1] / np.var(bex, ddof=1)
    alpha_m = ex.mean() - beta * bex.mean()
    assert abs(s["beta"] - beta) < 1e-10 and abs(s["alpha"] - 12 * alpha_m) < 1e-10
    assert abs(s["ann_return"] - 12 * r.mean()) < 1e-14
    assert abs(s["ann_vol"] - np.sqrt(12) * np.std(r.to_numpy(), ddof=1)) < 1e-14
    assert abs(s["sharpe"] - np.sqrt(12) * ex.mean() / np.std(ex, ddof=1)) < 1e-12
    a = (r - bench).to_numpy()
    assert abs(s["info_ratio"] - 12 * a.mean() / (np.sqrt(12) * np.std(a, ddof=1))) < 1e-12
    assert abs(s["cagr"] - (np.prod(1 + r.to_numpy()) ** (12 / 96) - 1)) < 1e-14
    doubled = performance_stats(2 * (r - rf) + rf, rf, bench)               # leverage doubles alpha and beta ...
    assert abs(doubled["beta"] - 2 * s["beta"]) < 1e-9 and abs(doubled["alpha"] - 2 * s["alpha"]) < 1e-9
    assert abs(doubled["sharpe"] - s["sharpe"]) < 1e-9                      # ... but not the Sharpe ratio
    b = performance_stats(bench, rf, bench, is_benchmark=True)
    assert b["beta"] == 1.0 and b["alpha"] == 0.0 and np.isnan(b["info_ratio"])   # undefined, reported as missing
    dd = performance_stats(pd.Series([-0.10, 0.05, -0.20, 0.30], index=idx[:4]), rf)
    assert abs(dd["max_drawdown"] - (0.9 * 1.05 * 0.8 - 1.0)) < 1e-12       # the peak is the initial value of 1


def test_changing_future_prices_does_not_change_earlier_decisions():
    cutoff = "2020-06-30"
    _, panel_a, mapped_a, rf, _ = _toy_market(seed=7)
    _, panel_b, mapped_b, _, _ = _toy_market(seed=7, shock_after=cutoff)
    months = schedule(P("2019-12"), P("2021-12"), (3, 6, 9, 12))
    forms_a = {m: formation_table(m, mapped_a, panel_a, _TOY_CFG)[0] for m in months}
    forms_b = {m: formation_table(m, mapped_b, panel_b, _TOY_CFG)[0] for m in months}
    for m in months:
        if m <= P("2020-06"):
            assert list(forms_a[m].index) == list(forms_b[m].index)
            for col in ("value", "vol", "ram", "z", "score", "mcap", "uw", "drift"):
                assert np.allclose(forms_a[m][col], forms_b[m][col], rtol=0, atol=0), col
            assert forms_a[m]["rank"].equals(forms_b[m]["rank"]) and forms_a[m]["group"].equals(forms_b[m]["group"])
            assert forms_a[m]["tradable"].equals(forms_b[m]["tradable"])
    assert not np.allclose(panel_a["px"].loc[P("2020-12")].dropna(), panel_b["px"].loc[P("2020-12")].dropna())
    assert panel_a["shares"].loc[:P("2020-06")].equals(panel_b["shares"].loc[:P("2020-06")])     # share counts as known then
    assert not np.allclose(panel_a["shares"].loc[P("2021-06")], panel_b["shares"].loc[P("2021-06")])
    ta, _ = build_targets(forms_a, months, _TOY_CFG, "top"); tb, _ = build_targets(forms_b, months, _TOY_CFG, "top")
    for m in months:
        if m <= P("2020-06"):
            assert ta[m].equals(tb[m])                                       # the same stocks at the same weights
    run_a = simulate(panel_a["ret"], rf, ta, 0.001, P("2019-12"), P("2021-12"), panel_a["last_month"])
    run_b = simulate(panel_b["ret"], rf, tb, 0.001, P("2019-12"), P("2021-12"), panel_b["last_month"])
    assert np.allclose(run_a["nav"].loc[:P("2020-06")], run_b["nav"].loc[:P("2020-06")], rtol=0, atol=1e-14)
    assert abs(run_a["nav"].iloc[-1] - run_b["nav"].iloc[-1]) > 1e-6        # the future really was different


def test_full_toy_backtest_reconciles_and_stays_fully_invested():
    _, panel, mapped, rf, _ = _toy_market()
    months = schedule(P("2019-12"), P("2021-12"), _TOY_CFG.rebalance_months)
    forms = {m: formation_table(m, mapped, panel, _TOY_CFG)[0] for m in months}
    for m in months:
        sizes = forms[m]["group"].value_counts()
        assert sizes.max() - sizes.min() <= 1 and sizes.sum() == len(forms[m])
        assert sorted(forms[m]["rank"]) == list(range(1, len(forms[m]) + 1))
    targets, log = build_targets(forms, months, _TOY_CFG, "top")
    run = run_portfolio(panel, rf, targets, P("2019-12"), P("2021-12"), 0.001)
    assert run["nav"].iloc[0] == 1.0 and len(run["ret"]) == 24
    assert (run["ret_gross"] >= run["ret"] - 1e-12).all()                   # costs can only reduce returns
    reb = run["rebalances"]
    assert np.allclose(reb["cost"], 0.001 * reb["traded_notional"], rtol=0, atol=1e-15)   # cost = rate x dollars traded
    assert abs(reb["one_way_turnover"].iloc[0] - 1.0) < 1e-12
    for m, w in run["targets"].items():
        assert abs(w.sum() - 1.0) < 1e-12 and (w > 0).all()                 # fully invested, long only
        assert len(w) <= log.loc[m, "selected"] == int(math.floor(len(forms[m]) / 5 + 0.5))
    universe, _ = build_targets(forms, months, _TOY_CFG, "all", weighting="cap", capped=False)
    first = forms[months[0]]
    assert len(universe[months[0]]) == int(first["tradable"].sum())
    assert np.allclose(universe[months[0]], (first["mcap"] * first["drift"])[first["tradable"]] / (first["mcap"] * first["drift"])[first["tradable"]].sum())


def _toy_data():
    """Toy data bundle in the shape run_backtest expects (benchmark and fund are the synthetic market series)."""
    _, panel, mapped, rf, counts = _toy_market()
    forms, members = build_formations(panel, mapped, _TOY_CFG)
    return {"cfg": _TOY_CFG, "panel": panel, "spells": mapped, "rf": rf, "forms": forms, "members": members,
            "share_units": counts, "share_units_todays_symbol": counts, "share_outage": None}, _TOY_CFG


def test_run_backtest_returns_aligned_series_for_every_portfolio():
    data, cfg = _toy_data()
    bt = run_backtest(data, cfg)
    assert bt["strategy"] == "Strategy" and bt["group_names"] == ["Q1", "Q2", "Q3", "Q4", "Q5"]
    assert list(bt["returns"].columns) == ["Strategy", "Q1", "Q2", "Q3", "Q4", "Q5", "Universe", "MKT"]
    assert bt["returns"].index[0] == P("2020-01") and bt["returns"].index[-1] == P("2021-12") and not bt["returns"].isna().any().any()
    assert (bt["nav"].iloc[0] == 1.0).all() and bt["metrics"].loc["MKT", "beta"] == 1.0
    assert abs(bt["metrics"].loc["Strategy", "ann_return"] - 12 * bt["returns"]["Strategy"].mean()) < 1e-14
    assert bt["formation_months"] == [P("2019-12"), P("2020-03"), P("2020-09"), P("2021-03"), P("2021-09")]
    assert list(bt["selection"].index) == bt["formation_months"] and (bt["selection"]["bought"] <= bt["selection"]["selected"]).all()
    monthly = run_backtest(data, replace(cfg, rebalance_months=tuple(range(1, 13))))
    assert len(monthly["formation_months"]) == 24
    free = run_backtest(data, replace(cfg, cost_rate=0.0))
    assert np.allclose(free["returns"]["Strategy"], bt["returns_gross"]["Strategy"], rtol=0, atol=1e-15)   # gross = a zero-cost run
    equal = run_backtest(data, replace(cfg, weighting="equal"))
    assert not equal["returns"]["Strategy"].equals(bt["returns"]["Strategy"])
    plain_cfg = replace(cfg, risk_adjust=False)
    plain = reconfigure(data, plain_cfg)
    m = bt["formation_months"][1]
    assert np.allclose(plain["forms"][m]["ram"], plain["forms"][m]["value"]) and not np.allclose(data["forms"][m]["ram"], data["forms"][m]["value"])
    assert run_backtest(plain, plain_cfg)["strategy"] == "Strategy"


def test_break_even_cost_is_a_root_of_the_net_advantage():
    data, cfg = _toy_data()
    be = break_even_cost(data, cfg, "Universe")
    assert be["status"] and len(be["table"]) == 8
    if not np.isnan(be["break_even"]):
        check = run_backtest(data, replace(cfg, cost_rate=be["break_even"]))
        assert abs(12 * (check["returns"]["Strategy"] - check["returns"]["Universe"]).mean()) < 1e-8
    else:
        assert be["table"].iloc[0] <= 0 or (be["table"] > 0).all()


def test_break_even_cost_finds_the_crossing_when_the_strategy_leads_before_costs():
    start, end = P("2019-12"), P("2021-12")
    months = pd.period_range(start, end, freq="M")
    names = ["H1", "H2", "H3", "H4"] + [f"L{i}" for i in range(6)]
    ret = pd.DataFrame({n: (0.02 if n.startswith("H") else 0.01) for n in names}, index=months)
    cfg = replace(_TOY_CFG, rebalance_months=(3, 6, 9, 12), buffer=0.0)
    dates = schedule(start, end, cfg.rebalance_months)
    forms = {}
    for i, m in enumerate(dates):                                            # the two best names change every quarter: full turnover
        best = ["H1", "H2"] if i % 2 == 0 else ["H3", "H4"]
        order = best + [n for n in names if n not in best]
        f = pd.DataFrame({"mcap": 1.0, "score": 1.0, "uw": 0.1, "drift": 1.0, "tradable": True, "carried_back": False}, index=names)
        f["rank"] = pd.Series(range(1, 11), index=order); f["group"] = assign_groups(-f["rank"], 5)
        forms[m] = f
    rf = pd.Series(0.0, index=months)
    data = {"panel": {"ret": ret, "last_month": pd.Series(pd.NaT, index=names)}, "rf": rf, "forms": forms}
    be = break_even_cost(data, cfg, "Universe")
    assert be["status"].startswith("break-even found") and 0.005 < be["break_even"] < 0.02
    a = simulate(ret, rf, build_targets(forms, dates, cfg, "top")[0], be["break_even"], start, end)["ret"]
    b = simulate(ret, rf, build_targets(forms, dates, cfg, "all", weighting="cap", capped=False)[0], be["break_even"], start, end)["ret"]
    assert abs(12 * (a - b).mean()) < 1e-9                                   # at that cost the advantage is zero


def test_transition_analysis_counts_moves_exits_and_entries():
    a, b = P("2020-03"), P("2020-09")
    fa = pd.DataFrame({"group": [1, 2, 3, 4, 5, 5]}, index=list("ABCDEF")).astype(float)
    fb = pd.DataFrame({"group": [1, 3, 5, 5, 4]}, index=["A", "B", "E", "G", "D"]).astype(float)  # C and F are gone, G is new
    members = {b: pd.DataFrame({"yahoo": ["A", "B", "E", "G", "D", "F"]})}                       # F still a member, C left
    t = transition_analysis({a: fa, b: fb}, members, [a, b], 5)
    c = t["counts"]
    assert c.loc[1, 1] == 1 and c.loc[2, 3] == 1 and c.loc[4, 4] == 1 and c.loc[5, 5] == 1
    assert c.loc[3, "left the index"] == 1 and c.loc[5, "member but not eligible"] == 1
    assert np.allclose(t["probabilities"].sum(axis=1), 1.0) and t["entries"][5] == 1 and t["entries"].sum() == 1
    assert abs(t["retention"][b] - 0.5) < 1e-12                                                  # E stays, F does not
    stays = t["stays"].set_index("security")["periods"]
    assert stays["E"] == 2 and stays["F"] == 1 and stays["G"] == 1 and bool(t["stays"]["censored"].all())


def test_cross_sectional_slope_and_rank_correlation_recover_a_known_relation():
    months = pd.period_range("2020-03", "2020-06", freq="M")
    names = [f"N{i}" for i in range(20)]
    score = pd.Series(np.linspace(-0.3, 0.6, 20), index=names)
    z = (score - score.mean()) / score.std(ddof=1)
    ret = pd.DataFrame(0.0, index=months, columns=names)
    ret.loc[P("2020-04")] = (0.02 + 0.01 * z).to_numpy()                 # one-month forward return, exactly linear in z
    forms = {P("2020-03"): pd.DataFrame({"ram": score})}
    xs = cross_sectional_tests(forms, ret, [P("2020-03")], horizon=1)
    assert abs(xs["slope"].iloc[0] - 0.01) < 1e-12 and abs(xs["intercept"].iloc[0] - 0.02) < 1e-12
    assert abs(xs["rank_ic"].iloc[0] - 1.0) < 1e-12 and xs["stocks"].iloc[0] == 20
    two = pd.DataFrame({"X": [0.10, 0.10, np.nan], "Y": [0.0, 0.0, 0.0]}, index=pd.period_range("2020-04", "2020-06", freq="M"))
    f = forward_returns(two, P("2020-03"), 3, ["X", "Y"])
    assert abs(f["X"] - (1.1 * 1.1 - 1)) < 1e-12 and f["Y"] == 0.0       # a name that stops trading keeps its value
    mt = mean_test(pd.Series([0.01, 0.03, 0.02, 0.02, 0.01, 0.03] * 10))
    assert abs(mt["mean"] - 12 * 0.02) < 1e-12 and mt["n"] == 60 and mt["share_positive"] == 1.0 and mt["ci_low"] < mt["mean"] < mt["ci_high"]


def test_block_bootstrap_is_reproducible_and_resamples_all_series_together():
    rng = np.random.default_rng(5)
    x = rng.normal(0.01, 0.04, 96)
    frame = pd.DataFrame({"a": x, "b": x + 0.001})                       # b is always exactly 0.1 points above a
    stats_ = {"gap": lambda v: (v[:, 1] - v[:, 0]).mean(), "mean_a": lambda v: v[:, 0].mean()}
    one = block_bootstrap(frame, stats_, 300, 6, 2270)
    two = block_bootstrap(frame, stats_, 300, 6, 2270)
    assert one.equals(two)                                               # same seed, same answer
    assert abs(one.loc["gap", "ci_low"] - 0.001) < 1e-12 and abs(one.loc["gap", "ci_high"] - 0.001) < 1e-12
    assert one.loc["mean_a", "ci_low"] < x.mean() < one.loc["mean_a", "ci_high"]
    assert not block_bootstrap(frame, stats_, 300, 12, 2270).loc["mean_a"].equals(one.loc["mean_a"])
    inside = np.arange(95) % 6 != 5                                      # steps that do not cross from one block to the next
    in_order = {"share": lambda v: float(np.mean((np.diff(v[:, 0]) % 96 == 1)[inside]))}
    months = pd.DataFrame({"t": np.arange(96.0)})
    assert block_bootstrap(months, in_order, 50, 6, 1).loc["share", "ci_low"] == 1.0     # inside a block the months keep their order
    assert block_bootstrap(months, in_order, 50, 1, 1).loc["share", "ci_high"] < 0.5     # single months would not


def test_hac_t_statistic_matches_a_newey_west_calculation_by_hand():
    rng = np.random.default_rng(11)
    e = rng.normal(0.0, 0.03, 61)
    x = pd.Series(0.004 + e[1:] + 0.5 * e[:-1])                          # a positively autocorrelated monthly series
    out = mean_test(x, scale=1.0)
    n, lags = len(x), out["hac_lags"]
    u = (x - x.mean()).to_numpy()
    s = (u @ u) / n + 2.0 * sum((1.0 - j / (lags + 1.0)) * (u[j:] @ u[:-j]) / n for j in range(1, lags + 1))   # Bartlett weights
    se = math.sqrt(s / n * n / (n - 1.0))                                # with the small-sample correction n / (n - 1)
    assert lags >= 1 and abs(out["t_hac"] - x.mean() / se) < 1e-9
    assert out["t_hac"] < out["t_simple"]                                # positive autocorrelation makes the mean less certain


def test_random_portfolios_follow_the_strategy_rules():
    data, cfg = _toy_data()
    bt = run_backtest(data, cfg)
    months, forms, chosen = bt["formation_months"], data["forms"], bt["selection"]["selected"]
    pools = random_pools(forms, months, chosen)
    rng = np.random.default_rng(3)
    seen = set()
    for _ in range(25):
        targets = random_targets(pools, cfg, rng)
        for m in months:
            f, w = forms[m], targets[m]
            assert abs(w.sum() - 1.0) < 1e-12 and (w > 0).all()
            assert set(w.index) <= set(f.index[f["tradable"]]) and len(w) <= chosen[m]      # eligible, still buyable, as many as the strategy
            if len(w) == chosen[m]:                                                         # nothing dropped: undo the drift ...
                at_reference = w / f.loc[w.index, "drift"]
                assert (at_reference / at_reference.sum()).max() <= cfg.max_weight + 1e-9  # ... and the weight limit held on the reference date
            seen |= set(w.index)
    assert len(seen) > max(chosen)                                                          # different stocks from draw to draw
    ten, caps = np.array([f"N{i}" for i in range(10)]), np.arange(1.0, 11.0)
    free = replace(cfg, max_weight=1.0, max_cap_multiple=1e9)
    all_ten = random_targets({months[0]: (ten, caps, np.ones(10), np.ones(10, dtype=bool), 10)}, free, np.random.default_rng(1))[months[0]]
    assert np.allclose(all_ten.reindex(ten), caps / caps.sum())                             # weighted by market value, not equally
    r1 = random_portfolio_baseline(data, bt, 20, 7)
    assert r1.shape == (20, 3) and r1.equals(random_portfolio_baseline(data, bt, 20, 7)) and r1["ann_return"].nunique() > 1
    first = random_targets(pools, cfg, np.random.default_rng(7))
    r = simulate(data["panel"]["ret"], data["rf"], first, 0.0, bt["start"], bt["end"], data["panel"]["last_month"])["ret"]
    assert abs(r1.loc[0, "ann_return"] - 12.0 * r.mean()) < 1e-14                           # returns before costs
    every = replace(cfg, rebalance_months=tuple(range(1, 13)), target_count=12)             # all stocks, every month: some cannot be bought
    bt_all = run_backtest(data, every)
    sel = bt_all["selection"]
    assert (sel["bought"] < sel["selected"]).any()
    drawn = random_targets(random_pools(forms, bt_all["formation_months"], sel["selected"]), every, np.random.default_rng(7))
    r = simulate(data["panel"]["ret"], data["rf"], drawn, 0.0, bt_all["start"], bt_all["end"], data["panel"]["last_month"])["ret"]
    assert abs(random_portfolio_baseline(data, bt_all, 3, 7).loc[0, "ann_return"] - 12.0 * r.mean()) < 1e-14   # as many as the strategy SELECTED


def test_markov_chain_reproduces_persistence_and_the_coin_flip_does_not():
    tm = transition_matrix([0, 0, 1, 1, 1, 0, 0, 0, 1, 0])
    assert np.allclose(tm, [[3 / 5, 2 / 5], [2 / 4, 2 / 4]])
    assert abs(long_run_recession_share(tm) - (0.4 / 0.9)) < 1e-12
    assert list(recession_spells([0, 1, 1, 0, 1, 0, 0, 1, 1, 1])) == [2, 1, 3]
    sticky = np.array([[0.98, 0.02], [0.10, 0.90]])
    rng = np.random.default_rng(11)
    markov = simulate_states(sticky, 1, 200_000, rng, markov=True)[0]
    coin = simulate_states(sticky, 1, 200_000, rng, markov=False)[0]
    share = long_run_recession_share(sticky)
    assert abs(markov.mean() - share) < 0.02 and abs(coin.mean() - share) < 0.01          # same long-run share ...
    assert abs(recession_spells(markov).mean() - 10.0) < 1.0                                # ... recessions last 1/(1-0.9) months
    assert abs(recession_spells(coin).mean() - 1.0 / (1.0 - share)) < 0.1                   # ... but not with a coin flip


def test_simulated_wealth_follows_the_market_model():
    rng = np.random.default_rng(3)
    states = simulate_states(np.array([[0.95, 0.05], [0.2, 0.8]]), 50, 36, rng)
    pools = {0: np.array([0.01, 0.02]), 1: np.array([-0.05, -0.02])}
    same = simulate_wealth(states, pools, 0.0, 1.0, np.zeros(5), 0.001, 100.0, rng)
    assert np.allclose(same["strategy"], same["benchmark"])                                 # beta 1, no alpha, no noise
    flat = simulate_wealth(states, pools, 0.002, 0.0, np.zeros(5), 0.001, 100.0, rng)
    assert np.allclose(flat["strategy"][:, -1], 100.0 * 1.003 ** 36)                        # beta 0: grows at rf + alpha
    ps = path_statistics(flat["strategy"], 100.0)
    assert ps["probability of a loss at the horizon"] == 0.0 and ps["median worst drawdown"] == 0.0
    assert abs(ps["median growth rate p.a."] - (1.003 ** 12 - 1)) < 1e-12
    down = path_statistics(np.array([[90.0, 60.0, 120.0]] * 4), 100.0)
    assert abs(down["median worst drawdown"] + 0.4) < 1e-12 and down["probability of a drawdown worse than 30%"] == 1.0


def test_sector_weights_and_retail_example_add_up():
    targets = {P("2020-03"): pd.Series({"A": 0.5, "B": 0.25, "C": 0.25})}
    w = sector_weights(targets, {"A": "Energy", "B": "Energy"})
    assert abs(w.loc[P("2020-03"), "Energy"] - 0.75) < 1e-12 and abs(w.loc[P("2020-03"), "Unknown"] - 0.25) < 1e-12
    m = P("2020-03")
    panel = {"px_close": pd.DataFrame({k: [v] for k, v in zip("ABE", [10.0, 20.0, 5000.0])}, index=[m]),
             "adv": pd.DataFrame({k: [1e6] for k in "ABE"}, index=[m])}
    ex = retail_example(pd.Series({"A": 0.5, "B": 0.3, "E": 0.2}), panel, m, 9000.0, 0.001)
    invested = 9000.0 / 1.001
    assert ex["holdings"] == 3 and abs(ex["largest position"] - 0.5 * invested) < 1e-9 and abs(ex["smallest position"] - 0.2 * invested) < 1e-9
    assert abs(invested + ex["initial cost"] - 9000.0) < 1e-9 and ex["ten largest positions, share of capital"] == 1.0
    assert ex["positions smaller than one share"] == 1                                      # the 5,000-dollar share
    assert ex["uninvested with whole shares only"] > 0.2 * invested - 1e-9                  # that position stays in cash


def test_spin_off_counted_twice_by_yahoo_is_repaired_and_real_distributions_are_kept():
    days = pd.bdate_range("2020-01-01", periods=8)
    mkt = pd.Series([100, 101, 101, 102, 102, 103, 103, 104.0], index=days)
    # A: on day 4 Yahoo has a split factor AND a dividend for one spin-off: adjusted close jumps +60%, close +3%
    close_a = pd.Series([50, 50, 51, 51, 52.53, 53, 53, 54.0], index=days)
    adj_a = close_a.copy(); adj_a.iloc[:4] = close_a.iloc[:4] / (1.6 / 1.03)
    # B: on day 4 a real split and a real cash distribution: close falls 20%, adjusted (correctly) rises 1%
    close_b = pd.Series([40, 40, 40, 40, 32.0, 32, 33, 33.0], index=days)
    adj_b = close_b.copy(); adj_b.iloc[:4] = close_b.iloc[:4] * (32.0 / 40.0) / 1.01
    adj = pd.DataFrame({"A": adj_a, "B": adj_b, "MKT": mkt}); close = pd.DataFrame({"A": close_a, "B": close_b, "MKT": mkt})
    zero = pd.DataFrame(0.0, index=days, columns=adj.columns)
    splits, dividends = zero.copy(), zero.copy()
    splits.loc[days[4], ["A", "B"]] = [1.3, 2.0]; dividends.loc[days[4], ["A", "B"]] = [12.0, 8.0]
    fixed, table = repair_double_adjustments(adj, close, dividends, splits, "MKT")
    t = table.set_index("security")
    assert t.loc["A", "decision"] == "close return used" and t.loc["B", "decision"] == "adjusted return kept"
    assert abs(t.loc["A", "adj_close_return"] - 0.60) < 1e-9 and abs(t.loc["A", "close_return"] - 0.03) < 1e-9
    ra = fixed["A"] / fixed["A"].shift(1) - 1
    assert abs(ra[days[4]] - 0.03) < 1e-12                                   # the false +60% is gone
    assert np.allclose(ra.drop(days[4]).dropna(), (adj_a / adj_a.shift(1) - 1).drop(days[4]).dropna())   # nothing else moved
    assert fixed["B"].equals(adj_b) and fixed["MKT"].equals(mkt)             # the real distribution is untouched
    assert repair_double_adjustments(adj, close, zero, zero, "MKT")[1].empty  # no split-and-dividend day, no change


def test_later_splits_are_undone_to_recover_the_price_actually_quoted():
    days = pd.bdate_range("2025-09-29", periods=6)
    splits = pd.DataFrame(0.0, index=days, columns=["N", "K"])
    splits.loc[days[3], "N"] = 10.0                                          # a 10-for-1 split three days later
    f = later_split_factor(splits, days[1])
    assert f["N"] == 10.0 and f["K"] == 1.0 and later_split_factor(splits, days[4])["N"] == 1.0
    m = P("2025-09")
    half = pd.Series({"K": 0.5, "N": 0.5})
    panel = {"px_close": pd.DataFrame({"K": [50.0], "N": [120.0]}, index=[m]), "adv": pd.DataFrame({"K": [1e6], "N": [1e6]}, index=[m])}
    plain = retail_example(half, panel, m, 1000.0, 0.0)
    true_ = retail_example(half, panel, m, 1000.0, 0.0, f)
    assert plain["highest share price"] == 120.0 and plain["positions smaller than one share"] == 0
    assert true_["highest share price"] == 1200.0 and true_["positions smaller than one share"] == 1


def test_real_splits_are_told_apart_from_spin_off_factors():
    for factor in (2.0, 3.0, 4.0, 10.0, 20.0, 1.5, 1.25, 0.5, 0.25, 0.125, 0.1, 0.3333, 0.0667, 0.05):
        assert is_share_split(factor), factor
    for factor in (1.319, 1.518, 1.7412, 1.082, 3.502, 1.0071, 0.807, 0.4873, 2.39, 1.402):
        assert not is_share_split(factor), factor


def test_share_counts_are_put_in_todays_units_and_unit_errors_near_splits_are_repaired():
    days = pd.bdate_range("2019-01-01", "2026-12-31")
    splits = pd.DataFrame(0.0, index=days, columns=["A", "B", "C", "D", "E", "G"])
    splits.loc[pd.Timestamp("2020-08-31"), "A"] = 4.0                        # a real 4-for-1 split
    splits.loc[pd.Timestamp("2020-06-01"), "B"] = 1.3                        # a spin-off, listed by Yahoo as a "split factor"
    splits.loc[pd.Timestamp("2026-04-06"), "C"] = 2.0                        # a split AFTER the sample
    splits.loc[pd.Timestamp("2020-03-02"), "D"] = 2.0                        # two splits, one after the other
    splits.loc[pd.Timestamp("2022-06-01"), "D"] = 3.0
    splits.loc[pd.Timestamp("2021-06-01"), "E"] = 2.0
    splits.loc[pd.Timestamp("2021-06-01"), "G"] = 2.0
    counts = {"A": pd.Series([100.0, 400.0, 100.0, 100.0, 400.0, 400.0],     # 20 Aug: already post-split; 31 Aug: still pre-split
                             index=pd.to_datetime(["2019-01-10", "2020-08-20", "2020-08-28", "2020-08-31", "2020-09-15", "2021-03-01"])),
              "B": pd.Series([50.0, 50.0], index=pd.to_datetime(["2020-01-15", "2020-12-15"])),
              "C": pd.Series([100.0], index=pd.to_datetime(["2019-06-28"])),
              "D": pd.Series([10.0, 20.0, 60.0], index=pd.to_datetime(["2019-06-03", "2021-06-01", "2023-06-01"])),
              "E": pd.Series([100.0, 400.0, 400.0], index=pd.to_datetime(["2020-08-05", "2023-01-10", "2023-06-10"])),
              "G": pd.Series([100.0, 330.0, 340.0, 345.0],                   # the company grew by a merger around the split
                             index=pd.to_datetime(["2020-06-01", "2021-06-15", "2021-12-01", "2022-03-01"])),
              "Z": pd.Series([1.0], index=pd.to_datetime(["2019-06-28"]))}   # no price data: ignored
    clean, changed = clean_share_counts(counts, splits)
    assert np.allclose(clean["A"], 400.0) and changed == 2                   # every count in today's units; two units repaired
    assert np.allclose(clean["D"], 60.0)                                     # ALL later splits are applied, not only the next one
    assert np.allclose(clean["E"], [200.0, 400.0, 400.0])                    # 300 days from the split: read as dated, although later counts are twice as high
    assert np.allclose(clean["G"], [200.0, 330.0, 340.0, 345.0])             # the unit is judged by the counts before AND after the split
    assert np.allclose(clean["B"], [50.0, 50.0])                             # a spin-off does not change the number of shares
    assert np.allclose(clean["C"], [200.0]) and "Z" not in clean
    only_sample = clean_share_counts(counts, splits.loc[:"2025-12-31"])[0]
    assert np.allclose(only_sample["C"], [100.0])                            # without the later split the company would look half as large


def test_market_value_is_the_share_count_times_the_price_actually_quoted():
    # B has 50 shares throughout. It is quoted at 143 until a spin-off on 1 June 2020, at 110 until a second one on
    # 31 July 2020 and at 100 from that day on; Yahoo restates every earlier close to 100 (143 / 1.3 / 1.1). C has 100
    # shares quoted at 80; a 2-for-1 split in 2026 restates its close to 40. Both have a single share count, reported
    # in January 2020.
    days = pd.bdate_range("2020-01-01", "2026-12-31")
    splits = pd.DataFrame(0.0, index=days, columns=["B", "C"])
    splits.loc[pd.Timestamp("2020-06-01"), "B"] = 1.3
    splits.loc[pd.Timestamp("2020-07-31"), "B"] = 1.1                            # on a month-end session: that day's close is already the new price
    splits.loc[pd.Timestamp("2026-04-06"), "C"] = 2.0
    months = pd.period_range("2020-04", "2020-07", freq="M")
    sessions = pd.Series([days[days <= m.end_time][-1] for m in months], index=months)
    factor = price_only_factors(splits, sessions)
    assert np.allclose(factor["B"], [1.43, 1.43, 1.1, 1.0]) and (factor["C"] == 1.0).all()   # C's split is a real one
    one_count = pd.to_datetime(["2020-01-15"])
    clean, _ = clean_share_counts({"B": pd.Series([50.0], index=one_count), "C": pd.Series([100.0], index=one_count)}, splits)
    panel = {"sessions": sessions, "px_close": pd.DataFrame({"B": 100.0, "C": 40.0}, index=months), "price_only_factor": factor}
    add_market_caps(panel, clean, Config())
    assert np.allclose(panel["mcap"]["B"], [7150.0, 7150.0, 5500.0, 5000.0])   # 50 shares x 143, 143, 110 and 100 dollars
    assert np.allclose(panel["mcap"]["C"], 8000.0)                              # 100 shares x 80 dollars


def test_month_end_share_count_is_the_latest_count_and_is_carried_back_only_briefly():
    months = pd.period_range("2015-08", "2016-06", freq="M")
    sessions = pd.Series([m.end_time.normalize() for m in months], index=months)
    kept = {"A": pd.Series([100.0, 110.0, 120.0], index=pd.to_datetime(["2015-10-20", "2016-01-15", "2016-03-31"])),
            "B": pd.Series([70.0], index=pd.to_datetime(["2016-05-10"])),
            "C": pd.Series([30.0], index=pd.to_datetime(["2015-01-05"]))}
    shares, back, age = month_end_shares(kept, sessions, ["A", "B", "C", "D"], carry_back_days=120)
    assert shares.loc[P("2015-12"), "A"] == 100.0 and shares.loc[P("2016-01"), "A"] == 110.0   # the latest count on or before the month-end
    assert age.loc[P("2015-12"), "A"] == 72 and age.loc[P("2016-01"), "A"] == 16               # its age in days
    assert shares.loc[P("2016-02"), "A"] == 110.0 and shares.loc[P("2016-03"), "A"] == 120.0   # a count dated on the month-end counts for it
    assert age.loc[P("2016-03"), "A"] == 0
    assert shares.loc[P("2015-09"), "A"] == 100.0 and back.loc[P("2015-09"), "A"]              # 20 days before the first count: carried back
    assert age.loc[P("2015-09"), "A"] == -20 and not back.loc[P("2015-12"), "A"]
    assert shares.loc[P("2015-08"), "A"] == 100.0 and back.loc[P("2015-08"), "A"]              # 50 days: still within 120
    assert np.isnan(shares.loc[P("2015-12"), "B"]) and not back.loc[P("2015-12"), "B"]         # 131 days before B's first count: none
    assert shares.loc[P("2016-01"), "B"] == 70.0 and back.loc[P("2016-01"), "B"]               # 100 days: carried back
    assert shares.loc[P("2016-05"), "B"] == 70.0 and not back.loc[P("2016-05"), "B"]
    assert shares.loc[P("2015-12"), "C"] == 30.0 and age.loc[P("2015-12"), "C"] == 360         # an old count stays in use until a newer one arrives
    assert shares["D"].isna().all()
    strict, strict_back, _ = month_end_shares(kept, sessions, ["A"], carry_back_days=0)
    assert np.isnan(strict.loc[P("2015-09"), "A"]) and not strict_back.to_numpy().any()        # no carrying back at all


def test_a_change_in_the_share_count_needs_a_second_count():
    d = pd.to_datetime
    one_off = pd.Series([100.0, 101.0, 260.0, 102.0, 103.0], index=d(["2020-01-10", "2020-04-10", "2020-07-10", "2020-10-10", "2021-01-10"]))
    assert list(confirmed_counts(one_off, 0.25)) == [100.0, 101.0, 102.0, 103.0]               # the isolated 260 is never used
    merger = pd.Series([100.0, 180.0, 181.0, 182.0], index=d(["2020-01-10", "2020-04-10", "2020-04-17", "2020-07-10"]))
    kept = confirmed_counts(merger, 0.25)
    assert list(kept) == [100.0, 181.0, 182.0] and kept.index[1] == pd.Timestamp("2020-04-17")   # believed from the second count on
    classes = pd.Series([230.0, 371.0, 229.0, 371.0, 228.0, 371.0], index=pd.date_range("2020-01-01", periods=6, freq="30D"))
    assert list(confirmed_counts(classes, 0.25)) == [230.0, 229.0, 228.0]                      # two share classes reported in turn
    gradual = pd.Series([100.0, 124.0, 150.0], index=d(["2020-01-10", "2020-04-10", "2020-07-10"]))
    assert confirmed_counts(gradual, 0.25).equals(gradual)                                     # each step is within 25%
    assert confirmed_counts(one_off, None).equals(one_off)                                     # rule switched off
    two = pd.to_datetime(["2020-01-10", "2020-04-10"])
    assert list(confirmed_counts(pd.Series([100.0, 81.0], index=two), 0.25)) == [100.0, 81.0]  # 19% lower: within a factor of 1.25
    assert list(confirmed_counts(pd.Series([100.0, 78.0], index=two), 0.25)) == [100.0]        # 22% lower is a factor of 1.28: needs a second count
    assert list(confirmed_counts(pd.Series([100.0, 126.0], index=two), 0.25)) == [100.0]
    for k in range(1, len(merger) + 1):                    # a longer history never changes what was decided before
        assert confirmed_counts(merger.iloc[:k], 0.25).equals(kept[kept.index <= merger.index[k - 1]])
    sessions = pd.Series(d(["2020-03-31", "2020-04-13", "2020-04-30"]), index=["m1", "m2", "m3"])
    shares, _, _ = month_end_shares({"M": kept}, sessions, ["M"], carry_back_days=0)
    assert list(shares["M"]) == [100.0, 100.0, 181.0]      # on 13 April the merger has been reported once: not yet used


def test_counts_directly_before_yahoos_outage_are_not_used():
    d = pd.to_datetime
    usual = d(["2016-02-10", "2016-05-10", "2016-08-10", "2016-11-10", "2017-02-10", "2017-05-10", "2017-08-10", "2018-11-15", "2019-02-10"])
    counts = {f"S{i}": pd.Series(100.0 + i, index=usual) for i in range(8)}                    # silent from August 2017 to November 2018
    counts["OWN"] = pd.Series(50.0, index=d(["2016-02-10", "2017-04-10", "2017-08-10", "2017-11-10", "2018-02-10", "2018-05-10",
                                             "2018-08-10", "2018-11-15"]))                     # a gap of its own in 2016-17, none in 2017-18
    outage = reporting_outage(counts, gap_days=180)
    assert outage == (pd.Timestamp("2017-08-10"), pd.Timestamp("2018-11-15"))                  # where most symbols are silent
    kept = skip_before_outage(counts["S0"], outage, 180)
    assert pd.Timestamp("2017-08-10") not in kept.index and len(kept) == len(usual) - 1        # only the count before the silence goes
    assert skip_before_outage(counts["OWN"], outage, 180).equals(counts["OWN"])                # its own gap is not Yahoo's outage
    part = pd.Series(60.0, index=d(["2016-02-10", "2017-03-01", "2017-10-15", "2018-01-10", "2018-04-10", "2018-07-10", "2018-10-10", "2018-11-15"]))
    assert skip_before_outage(part, outage, 180).equals(part)          # a gap of 228 days of which only 66 lie in the outage
    assert reporting_outage({"A": counts["S0"].iloc[:6]}, 180) is None
    twice = d(["2015-10-01", "2016-04-20", "2016-07-01", "2016-10-01", "2017-01-01", "2017-04-01", "2017-08-10", "2018-11-15", "2019-02-10"])
    assert reporting_outage({f"T{i}": pd.Series(1.0, index=twice) for i in range(6)}, 180) == outage   # of two silences, the longer one
    assert skip_before_outage(counts["S0"], None).equals(counts["S0"])
    sessions = pd.Series(d(["2017-08-31", "2018-08-31", "2018-11-30"]), index=["m1", "m2", "m3"])
    panel = {"sessions": sessions, "px_close": pd.DataFrame({"S0": 10.0}, index=sessions.index),
             "price_only_factor": pd.DataFrame({"S0": 1.0}, index=sessions.index)}
    late = dict(counts); late["S0"] = counts["S0"].copy(); late["S0"].loc["2017-08-10"] = 120.0   # a value entered later under the old date
    add_market_caps(panel, late, Config(), outage)
    assert list(panel["shares"]["S0"]) == [100.0, 100.0, 100.0] and panel["shares_age_days"].loc["m2", "S0"] == 478
    add_market_caps(panel, late, replace(Config(), share_skip_before_outage=False), outage)
    assert list(panel["shares"]["S0"]) == [120.0, 120.0, 100.0]
    wrong = dict(counts)                                               # the count before the silence is a one-off wrong value
    wrong["S0"] = pd.Series([100.0, 101.0, 260.0, 102.0], index=d(["2017-02-10", "2017-05-10", "2017-08-10", "2018-11-15"]))
    add_market_caps(panel, wrong, Config(), outage)
    assert list(panel["shares"]["S0"]) == [101.0, 101.0, 102.0]        # rule 4 comes first: 101 is then the latest count, not 100


def test_share_counts_follow_the_ticker_a_company_had_at_the_time():
    d = pd.to_datetime
    counts = {"OLD": pd.Series([100.0, 101.0, 30.0], index=d(["2020-01-10", "2021-01-10", "2023-01-10"])),   # by 2023 OLD is someone else's ticker
              "NEW": pd.Series([7.0, 7.0, 101.0, 102.0], index=d(["2019-06-01", "2020-06-01", "2021-03-01", "2022-03-01"])),   # so was NEW until 2020
              "SAME": pd.Series([5.0, 6.0], index=d(["2020-01-10", "2021-01-10"]))}
    out, table = splice_ticker_history(counts, {"NEW": [("OLD", "2021-03-01")]})
    assert list(out["NEW"]) == [100.0, 101.0, 101.0, 102.0]                    # the company's own counts, under whichever ticker
    assert list(out["NEW"].index) == list(d(["2020-01-10", "2021-01-10", "2021-03-01", "2022-03-01"]))
    assert out["SAME"].equals(counts["SAME"])
    assert list(out["OLD"]) == [30.0]                                          # today's user of OLD keeps only what is its own
    row = table.iloc[0]
    assert row["last count before"] == 101.0 and row["first count after"] == 101.0 and row["ratio"] == 1.0   # the counts join up
    back, _ = splice_ticker_history(counts, {"SAME": [("SAME", "2020-06-01"), ("OLD", "2021-06-01")]})       # away for a year and back
    assert list(back["SAME"]) == [5.0, 101.0]
    none, t2 = splice_ticker_history(counts, {"NEW": [("GONE", "2021-03-01")]})                              # Yahoo has nothing under the old ticker
    assert list(none["NEW"]) == [101.0, 102.0] and np.isnan(t2["last count before"].iloc[0])
    assert former_symbols(["META", "AAPL", "FISV"]) == ["FB", "FI"]


def test_prices_from_before_regular_trading_do_not_count_for_the_signal():
    adj, panel, mapped, rf, counts = _toy_market()
    volume = adj.notna() * 1e6
    early = volume.index[volume.index < "2019-10-01"]
    volume.loc[early, "S01"] = 0.0                                             # Yahoo shows prices from before the listing ...
    volume.loc[early[:-5:7], "S01"] = 200.0                                    # ... with a few shares traded now and then
    volume.loc[pd.Timestamp("2020-07-31"), "S00"] = 0.0                        # one day without reported volume in a listed stock
    first = first_regular_trading_day(adj, volume)
    assert first["S01"] == pd.Timestamp("2019-10-01") and first["S00"] == adj.index[0]
    quiet = build_monthly_panel(adj, adj.copy(), volume, "MKT")
    quiet["price_only_factor"] = panel["price_only_factor"]
    add_market_caps(quiet, counts, _TOY_CFG)
    assert quiet["px_close"].loc[P("2019-06"), "S01"] > 0 and np.isnan(quiet["px_signal"].loc[P("2019-06"), "S01"])
    assert quiet["daily_close"].loc[:"2019-09-30", "S01"].isna().all() and quiet["daily_close"].loc["2019-10-01":, "S01"].notna().all()
    assert quiet["px_signal"]["S00"].equals(panel["px_signal"]["S00"])         # a single day without volume is not a gap
    def status(month):
        return universe_at(P(month), mapped, quiet, _TOY_CFG).set_index("ticker")["status"]
    assert status("2020-03")["S01"] == "listed too recently for the signal"    # five months of regular trading
    assert status("2020-09")["S01"] == "eligible" and status("2020-09")["S00"] == "eligible"
    x, plain = momentum_inputs(quiet, P("2020-09"), _TOY_CFG), momentum_inputs(panel, P("2020-09"), _TOY_CFG)
    assert x.loc["S01", "months"] == 9 and plain.loc["S01", "months"] == 12   # the price twelve months back is from before the listing
    assert x.loc["S01", "days"] < plain.loc["S01", "days"] and x.loc["S00"].equals(plain.loc["S00"])


def test_a_price_restatement_without_a_listed_factor_is_added_by_hand():
    days = pd.bdate_range("2020-03-25", periods=8)
    raw = {"splits": pd.DataFrame(0.0, index=days, columns=["HWM", "X"]),
           "later_splits": pd.DataFrame({"X": [2.0]}, index=[pd.Timestamp("2026-04-06")])}
    table = all_split_factors(raw)
    day = pd.Timestamp("2020-04-01")
    assert table.loc[day, "HWM"] == UNLISTED_PRICE_FACTORS[("HWM", "2020-04-01")] and not is_share_split(table.loc[day, "HWM"])
    assert table.loc[pd.Timestamp("2026-04-06"), "X"] == 2.0 and table.loc[pd.Timestamp("2026-04-06"), "HWM"] == 0.0
    assert raw["splits"].to_numpy().sum() == 0.0                               # the download itself is left as it was
    sessions = pd.Series([pd.Timestamp("2020-03-31"), pd.Timestamp("2020-04-03")], index=["m1", "m2"])
    assert list(price_only_factors(table.loc[:"2020-04-03"], sessions)["HWM"]) == [1.304, 1.0]


def test_the_buffer_rule_favours_only_stocks_that_are_actually_held():
    names = list("ABCDEFGHIJ")
    def table(order, cannot_buy=()):
        f = pd.DataFrame({"mcap": 100.0, "score": 1.0, "uw": 0.1, "rank": [order.index(n) + 1 for n in names], "group": 5.0,
                          "drift": 1.0, "tradable": [n not in cannot_buy for n in names], "carried_back": False}, index=names)
        return f
    cfg = replace(Config(), target_count=5, max_weight=1.0)                    # five stocks, 20% buffer: ranks 1-4 sure, 5-6 depend on holdings
    m1, m2, m3 = P("2020-03"), P("2020-09"), P("2021-03")
    forms = {m1: table(list("ABCDEFGHIJ"), cannot_buy=("E",)),                 # E is selected but can no longer be bought
             m2: table(list("ABCDFEGHIJ")),                                     # F is now fifth, E sixth
             m3: table(list("ABCDEFGHIJ"))}                                     # and back: E fifth, F sixth
    targets, log = build_targets(forms, [m1, m2, m3], cfg, "top")
    assert list(targets[m1].index) == list("ABCD") and log.loc[m1, "selected"] == 5 and log.loc[m1, "bought"] == 4
    assert sorted(targets[m2].index) == list("ABCDF") and log.loc[m2, "already held"] == 4   # E was never held: no preference over F
    assert sorted(targets[m3].index) == list("ABCDF") and log.loc[m3, "already held"] == 5   # F is held and ranks sixth: it stays
    assert sorted(build_targets(forms, [m1, m2, m3], replace(cfg, buffer=0.0), "top")[0][m3].index) == list("ABCDE")
    fifth = replace(Config(), max_weight=1.0)                                  # ten stocks: one fifth is two
    assert build_targets(forms, [m1], fifth, "top")[1].loc[m1, "selected"] == 2
    assert build_targets(forms, [m1], replace(fifth, target_shift=1), "top")[1].loc[m1, "selected"] == 3


def test_unfinished_last_month_is_not_treated_as_a_month_end():
    full = month_end_sessions(pd.bdate_range("2025-10-01", "2025-12-31"))
    assert list(full.index) == [P("2025-10"), P("2025-11"), P("2025-12")]
    cut = month_end_sessions(pd.bdate_range("2025-10-01", "2025-12-15"))
    assert list(cut.index) == [P("2025-10"), P("2025-11")]                   # 15 December is not a month-end
    easter = month_end_sessions(pd.bdate_range("2024-02-01", "2024-03-28"))  # Good Friday: last session 28 March
    assert easter.index[-1] == P("2024-03")


def test_a_stale_yield_is_not_carried_forward():
    sessions = pd.Series(pd.to_datetime(["2025-11-28", "2025-12-31", "2026-01-30", "2026-02-27"]),
                         index=pd.period_range("2025-11", "2026-02", freq="M"))
    y = pd.Series([3.6, 3.7], index=pd.to_datetime(["2025-11-26", "2025-12-30"]))    # the yield series stops in December
    rf = monthly_rf(y, sessions)
    assert abs(rf[P("2025-12")] - (1.036 ** (1 / 12) - 1)) < 1e-15 and abs(rf[P("2026-01")] - (1.037 ** (1 / 12) - 1)) < 1e-15
    assert np.isnan(rf[P("2026-02")])                                        # a month-old yield is not reused


def test_turnover_per_year_is_the_average_per_rebalance_times_rebalances_per_year():
    months = pd.period_range("2019-12", "2020-12", freq="M")
    ret = pd.DataFrame({"A": 0.0, "B": 0.0}, index=months)
    rf = pd.Series(0.0, index=months)
    flip = [pd.Series({"A": 1.0}), pd.Series({"B": 1.0})]
    targets = {m: flip[i % 2] for i, m in enumerate(schedule(P("2019-12"), P("2020-12"), (3, 6, 9, 12)))}
    run = simulate(ret, rf, targets, 0.001, P("2019-12"), P("2020-12"))
    t = turnover_summary(run)
    assert len(run["rebalances"]) == 4 and t["rebalances_per_year"] == 4.0   # three recurring trades in the year, at a rate of four
    assert abs(t["one_way_turnover_pa"] - 4.0) < 1e-12                       # 100% replaced at each of four dates a year
    assert abs(t["cost_pa"] - 4 * 0.002 / 1.001) < 1e-9 and t["orders_pa"] == 8.0      # each switch trades V + V*, at 10 bp
    hold = turnover_summary(simulate(ret, rf, {P("2019-12"): flip[0]}, 0.001, P("2019-12"), P("2020-12")))
    assert hold["one_way_turnover_pa"] == 0.0 and hold["cost_pa"] == 0.0 and abs(hold["initial_cost"] - 0.001 / 1.001) < 1e-12
    half_yearly = {m: flip[i % 2] for i, m in enumerate(schedule(P("2019-12"), P("2021-12"), (3, 9)))}
    months2 = pd.period_range("2019-12", "2021-12", freq="M")
    run2 = simulate(pd.DataFrame({"A": 0.0, "B": 0.0}, index=months2), pd.Series(0.0, index=months2), half_yearly, 0.001, P("2019-12"), P("2021-12"))
    assert turnover_summary(run2)["rebalances_per_year"] == 2.0 and abs(turnover_summary(run2)["one_way_turnover_pa"] - 2.0) < 1e-12


def test_two_companies_that_shared_a_ticker_get_the_right_price_series():
    assert yahoo_symbol("DOW", None, "2017-09-01") == "DD"                   # Dow Chemical before the merger
    assert yahoo_symbol("DOW", "2019-04-02", None) == "DOW"                  # today's Dow Inc.
    assert yahoo_symbol("Q", "2017-08-29", "2017-11-15") == "IQV" and yahoo_symbol("Q", None, "2011-03-31") == "Q"
    assert yahoo_symbol("BRK.B") == "BRK-B" and yahoo_symbol("GPS") == "GAP"
    spells = pd.DataFrame({"ticker": ["DOW", "DD", "DD", "DWDP"], "name": ["Dow Chemical", "old DuPont", "DuPont de Nemours", "DowDuPont"],
                           "start": pd.to_datetime([None, None, "2019-06-03", "2017-09-01"]),
                           "end": pd.to_datetime(["2017-09-01", "2017-09-01", None, "2019-06-03"])})
    first = pd.Series({"DD": pd.Timestamp("2009-06-01"), "DOW": pd.Timestamp("2019-03-20")})
    m = map_spells_to_yahoo(spells, first, "2009-06-01").set_index("name")
    assert m.loc["Dow Chemical", "yahoo"] == "DD" and m.loc["Dow Chemical", "block"] == ""
    assert m.loc["old DuPont", "block"].startswith("ticker reused")          # Yahoo's DD history is not old DuPont's
    assert m.loc["DuPont de Nemours", "block"] == "" and m.loc["DowDuPont", "yahoo"] == "DD" and m.loc["DowDuPont", "block"] == ""
