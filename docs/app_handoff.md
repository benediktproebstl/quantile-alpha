# Handoff for the Streamlit app (next phase)

The app is worth up to 2 marks, and only if it is **deployed on Streamlit and its source is on GitHub**, with both URLs in the prospectus and the notebook. This note describes what the engine already provides so that the app recalculates real performance with the same code as the notebook. Nothing in this repository claims that an app exists yet.

## The rule the app must respect

The brief says: "Let the user change a meaningful assumption and see the resulting performance and benchmark comparison. Keep the calculations consistent with your notebook." The app must therefore call the engine and show what it returns. It must not draw curves from stored or invented numbers.

## Functions to call

Everything is in `quantile_alpha/engine.py`, which is exported from the notebook (`python tools/export_engine.py`). Do not edit `engine.py` by hand.

```python
from dataclasses import replace
from quantile_alpha.engine import CFG, prepare_data, reconfigure, run_backtest, get_fred_api_key

data = prepare_data(CFG, get_fred_api_key())      # all downloads and preparation; five to fifteen minutes
bt = run_backtest(data, CFG)                      # default configuration = the notebook's headline result
bt["metrics"].loc[["Strategy", "SPY", "Universe"], ["ann_return", "ann_vol", "sharpe", "alpha", "beta", "info_ratio"]]
```

### `prepare_data(cfg, fred_key=None, fetch=None) -> dict`

Downloads FRED, Wikipedia and Yahoo data (prices together with the splits since the end of the sample, and share counts, including those filed under the former tickers of renamed companies) and builds the data bundle. `fetch(name, builder)` is a hook for caching: it receives a name and a function that performs the download.

Returned keys: `panel` (month-end prices, monthly returns, session dates, dollar volume, daily closes, share counts and market capitalisation), `spells` (index membership with Yahoo symbols), `rf` (monthly risk-free return), `forms` (for every month: the eligible stocks with momentum value, volatility, z-score, momentum score, market value, rank and group), `members` (every index member with its status), `status` (download outcome per symbol), `adjustment_repairs` (the days on which Yahoo's adjusted return was replaced), `share_units` (one share-count series per company, in today's split units), `share_units_todays_symbol` (the same without the ticker table, for the sensitivity analysis), `share_outage` (Yahoo's general gap in share counts), `ticker_handovers` (the last count before and the first after each change of ticker), `splits`, `yield`, `constituents`, `changes`, `cfg`.

### `run_backtest(data, cfg=None) -> dict`

| Returned key | Content |
|---|---|
| `returns`, `returns_gross` | Monthly net and gross returns: `Strategy`, the score quintiles `Q1` to `Q5`, `Universe` (all eligible stocks by market value), `SPY`, `SPMO` |
| `nav`, `drawdowns` | Cumulative value starting at 1, and percentage below the running peak |
| `rf` | Monthly risk-free return aligned with `returns` |
| `metrics`, `metrics_gross` | One row per portfolio: `ann_return`, `ann_vol`, `sharpe`, `alpha`, `beta`, `info_ratio`, `cagr`, `max_drawdown`, `tracking_error`, `sortino`, `profit_factor`, `alpha_t`, `alpha_p`, `r_squared`, ... |
| `trading` | Turnover, costs, orders per year, number of holdings, effective holdings, largest weight |
| `selection` | One row per rebalance of the strategy: stocks eligible, selected, bought, already held, at the weight limit; largest weight; share of the ten largest |
| `runs` | Per portfolio: `targets` (target weights at each trade date), `rebalances`, `monthly`, `events` |
| `strategy`, `groups`, `group_names`, `formation_months`, `start`, `end`, `universe_size` | Bookkeeping |
| `warnings` | Plain-language warnings, for example an eligible universe below 400 stocks |

The holdings and weights at any trade date are in `bt["runs"]["Strategy"]["targets"][month]`; scores and market values of all eligible stocks in `data["forms"][month]`.

## Assumptions the user can change

| Assumption | How | Notes |
|---|---|---|
| Transaction cost | `run_backtest(data, replace(CFG, cost_rate=0.0025))` | Instant: no new download |
| Rebalancing months | `replace(CFG, rebalance_months=(3, 6, 9, 12))` for quarterly, `(3,)` for once a year | Instant |
| Weighting | `replace(CFG, weighting="cap")` (market value only) or `"equal"` | Instant |
| Weight limit per stock | `replace(CFG, max_weight=0.05)`; no limits: `max_weight=1.0, max_cap_multiple=1e9` | Instant; a limit below 1 / (number of holdings) raises an error |
| Buffer rule | `replace(CFG, buffer=0.0)` | Instant |
| Number of stocks held | `replace(CFG, target_count=100)` (the default, 0, holds one fifth of the eligible stocks); `target_shift=1` or `-1` moves the cut-off by one place | Instant |
| Share of the universe held | `cfg = replace(CFG, n_groups=10)`; `run_backtest(reconfigure(data, cfg), cfg)` | A few seconds; no new download |
| Risk adjustment of the signal | `cfg = replace(CFG, risk_adjust=False)`; `run_backtest(reconfigure(data, cfg), cfg)` | A few seconds |

Suggested main control: the weight limit per stock or the weighting, because concentration is the strategy's main specific risk and the client can see what it does to return and drawdown. A second control for the transaction cost shows the break-even logic.

Other ready-made functions: `performance_stats`, `market_model`, `rolling_stats`, `block_bootstrap`, `random_portfolio_baseline`, `break_even_cost`, `transition_analysis`, `sector_weights`, `retail_example`, and for the Monte Carlo `transition_matrix`, `simulate_states`, `simulate_wealth`, `path_statistics`.

## Caching

`prepare_data` takes five to fifteen minutes, depending on how fast Yahoo answers, and should run once per app session at most.

```python
import streamlit as st

@st.cache_data(ttl=24 * 3600, show_spinner="Downloading market data ...")
def load():
    return prepare_data(CFG, st.secrets.get("FRED_API_KEY"))
```

`run_backtest` takes a fraction of a second and needs no caching. The download step briefly needs a few hundred megabytes of memory for the daily prices, so it should not run more than once at a time.

## Credentials

None are required. If a FRED key is used, store it in Streamlit's secrets, never in the repository. The engine never prints the key.

## Things to watch

* **Yahoo rate limits.** Streamlit Community Cloud shares IP addresses. The share counts need one request per symbol (about 650, including former tickers). `yahoo_daily` and `yahoo_shares` retry and stop with a clear message if Yahoo keeps refusing; the app should show that message instead of an empty chart.
* **Data licensing.** Yahoo data are for personal use. The app should show computed results and charts, not offer raw prices for download. Wikipedia tables are CC BY-SA 4.0 (attribute the source). FRED asks for a citation of the series. "S&P 500" is a trademark of S&P Global; the app must not suggest that it is an S&P product.
* **Results drift over time.** Yahoo removes delisted companies and revises share counts, so the app's numbers will slowly move away from the prospectus. State the data retrieval date in the app.
* **Extending the sample.** The end of the sample comes from `Config` (`last_holding_month`, `data_end_exclusive`); the FRED window follows it. The start cannot be moved before January 2016: Yahoo's share counts begin in October 2015.
* **Dependencies.** Add `streamlit` to `requirements.txt`. The engine needs `numpy`, `pandas`, `statsmodels`, `yfinance`, `requests` and `lxml`; it does not need matplotlib.
* **Consistency check.** Section 11.3 of the notebook shows that `prepare_data` + `run_backtest` reproduce the notebook exactly. Keep that check green after any change.

## Still to do in the app phase

1. Write `app.py` and add `streamlit` to the requirements.
2. Deploy on Streamlit Community Cloud. The repository has to be reachable for the deployment and for the graders.
3. Verify the deployed URL in a private browser window.
4. Add both URLs to the notebook (top table) and to the prospectus.
5. Update `README.md` with run instructions for the app.
