# The tracker app

`tracker_app.py` is the optional part of the assignment: a Streamlit app around the same strategy. The brief asks for three things: the user can change a meaningful assumption, sees the resulting performance and benchmark comparison, and the calculations stay consistent with the notebook.

## What the user can do

| Control | What it changes in the engine | Values |
|---|---|---|
| Compare with | The benchmark of the comparison and of alpha, beta and the information ratio | S&P 500 fund (SPY), cap-weighted universe, momentum fund (SPMO) |
| Amount invested | The scale of the dollar figures only | Any amount from 100 dollars |
| Weights follow | `Config.weighting` | Market value times score (the prospectus), market value only, equal weights |
| Rebalanced | `Config.rebalance_months` | March and September (the prospectus), every quarter, once a year in March |
| Trading cost | `Config.cost_rate` | 0 to 100 basis points per dollar traded (the prospectus: 10) |
| Largest weight per stock | `Config.max_weight`; "No limit" also switches off the limit of three times the market-value weight | 3% to 20%, or no limit (the prospectus: 9%) |
| Stocks held | `Config.target_count` | The best fifth of the eligible stocks (the prospectus), or a fixed number from 25 to 150 |
| Buffer rule | `Config.buffer` | 20% (the prospectus) or none |
| Period | The months shown and measured | The last 1, 3 or 5 years, or the whole sample |

The page then shows the value of the amount invested against the benchmark, four headline figures, the table of measures the brief asks for (average return, volatility, Sharpe ratio, alpha, beta, information ratio, plus the largest loss), the lead by calendar year, the loss from the previous high, and the holdings at any trade date. When an assumption differs from the prospectus, a line says by how much the average return changed, and the table gains a column with the prospectus settings.

Two combinations cannot work, for example 25 stocks with a limit of 3% each (the weights could not add up to 100%). The engine refuses them and the app says so.

## Why its numbers are the notebook's

* Every change of an assumption calls `run_backtest(data, config)` from `quantile_alpha/engine.py`. That file is exported from the notebook cells marked `# [engine]` and is never edited by hand (`python tools/export_engine.py --check`).
* The measures of the table come from the engine's `performance_stats`, the function behind the notebook's tables. For a period shorter than the whole sample and for the other two benchmarks, the app passes the same function the returns of that period and that benchmark.
* The app itself only multiplies returns into a dollar value, compounds them by calendar year and formats numbers.
* The notebook's section 11.3 runs the same two calls the app makes and compares them with the reported results.

## The data

A backtest reads three things from the engine's data bundle: the monthly returns, the risk-free rate, and the formation tables (score, market value, rank and tradability of every eligible stock at every month-end). `quantile_alpha/app_data.py` keeps exactly that part and drops the rest, in particular the daily prices and the share counts.

* **With a snapshot.** If the folder `app_data/` exists, the app starts from it at once. `python tools/make_app_snapshot.py` writes the folder: it downloads through the engine (or reuses the notebook's downloads of the same day), saves three Parquet files and `meta.json`, and checks that a backtest on the snapshot gives the same monthly returns as a backtest on the full data. Market values are stored as shares of the eligible universe; the engine uses only their proportions. `meta.json` records when the data were retrieved, the configuration, and the headline figures; the app compares them with what the engine returns and says so at the bottom of the page.
* **Without a snapshot.** The app calls the engine's `prepare_data`, which retrieves everything from Yahoo Finance, FRED and Wikipedia. That takes five to fifteen minutes and is repeated whenever the server restarts.

What the snapshot cannot do: change the settings of the momentum score (look-back, risk adjustment, share of the index held). Those need the daily prices; the notebook covers them in section 8.1.

**A point for the group to decide.** The snapshot contains figures derived from Yahoo Finance data. Yahoo's terms restrict redistributing its data. The snapshot holds no prices and no share counts, only monthly returns, scores and weights, but whether to publish it in a public repository is the group's decision. Without it the app still works, with the long first start described above, and Yahoo may limit requests from Streamlit's shared servers.

## Running and testing

```bash
pip install -r requirements.txt
```

```bash
streamlit run tracker_app.py
```

```bash
pytest tests/test_app_data.py tests/test_tracker_app.py
```

`tests/test_app_data.py` builds a small synthetic market, writes it as a snapshot, reads it back and checks that the backtest is unchanged. `tests/test_tracker_app.py` runs the app without a browser: the first page must show the engine's figures, every control must run, an impossible combination must be explained, and the reset must restore the prospectus settings. The second file needs the snapshot and is skipped without it.

Environment variables: `QA_APP_DATA` (another snapshot folder), `QA_APP_LIVE=1` (ignore the snapshot and download), `QA_CACHE_DIR` and `QA_CACHE_STAMP` (where downloads are kept, as in the notebook), `FRED_API_KEY` (optional; also read from Streamlit's secrets).

## Design

The app uses the design of the prospectus: a white page, light-grey tiles with a hairline border and rounded corners, the typeface Inter with tabular figures, green for gains and progress, orange for losses. The light theme is fixed in `.streamlit/config.toml`, the layout is one column of at most 900 pixels, and Streamlit's own menu is hidden. Inter is served from `static/` (SIL Open Font License, `static/OFL.txt`).

## Deployment

The steps are in the README. Deployment needs the Streamlit account of a group member, so it was not done by the AI assistant. After deploying, open the link, check that the prospectus settings show the notebook's figures, and only then enter the link in the notebook and in `prospectus/details.toml`.
