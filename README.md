# Quantile Alpha

A rules-based U.S. large-cap momentum strategy, built for the group assignment of **2270 Financial Modeling**: the best fifth of the S&P 500 by risk-adjusted momentum, weighted by company size and momentum score, following the published construction rules of the S&P 500 Momentum index. This repository holds the research notebook, the calculation engine exported from it, the investor prospectus, the tracker app, the tests and the project documentation.

Repository: <https://github.com/benediktproebstl/quantile-alpha> · [Open the notebook in Google Colab](https://colab.research.google.com/github/benediktproebstl/quantile-alpha/blob/main/Financial_Modeling_Quantile_Alpha.ipynb)

**Status (25 November 2026).** The notebook runs from start to finish and reproduces every number, table and figure. The investor prospectus (`investor_prospectus.pdf`, a cover and seven pages) and the tracker app (`tracker_app.py`) are built. Still open: the submission date, the deployment of the app on Streamlit and its link (see the list at the end).

## The strategy

Twice a year, at the end of February and August, every eligible S&P 500 member is scored by its price change over twelve months, leaving out the most recent month, divided by the volatility of its daily price changes. The best fifth is selected, with a buffer that favours stocks already held, and weighted by market value times momentum score, with a limit of 9% per stock when the weights are set. The trades are made at the end of March and September. Long-only, fully invested, 10 basis points per dollar traded. Benchmark: SPY. Two checks: a cap-weighted portfolio of all eligible stocks, and SPMO, a real fund that tracks the same index.

## What the backtest shows

January 2016 to December 2025, 120 monthly returns, net of costs:

<!-- RESULTS:START -->
| | Average return p.a. | Volatility p.a. | Sharpe ratio | Alpha p.a. | Beta | Information ratio | Max drawdown | Value of 1 invested |
|---|---|---|---|---|---|---|---|---|
| Quantile Alpha, net of costs | 17.8% | 16.3% | 0.96 | 3.5% | 0.95 | 0.38 | -23.1% | 5.15 |
| S&P 500 (SPY), benchmark | 14.9% | 15.1% | 0.84 | – | 1.00 | – | -23.9% | 3.94 |
| Cap-weighted universe | 15.3% | 15.1% | 0.87 | 0.3% | 1.00 | 0.68 | -23.9% | 4.08 |
<!-- RESULTS:END -->

**The strategy finished ahead of the index fund, by 2.9 percentage points a year.** The notebook attaches four reservations to that figure:

* **It is not statistically significant.** The alpha has a t-statistic of 1.35, and the 95% bootstrap interval for the return difference to SPY runs from -2.4 pp to +8.5 pp a year.
* **Most of it was earned in 2024 and 2025.** At the end of 2023 one dollar in the strategy was worth 2% more than one dollar in SPY; at the end of 2025, 30% more. The strategy was ahead of SPY in 6 of 10 calendar years.
* **It depends on weighting by company size, and the portfolio is concentrated.** The same selected stocks in equal weights earned 13.9% a year, -1.0 pp against SPY. The ten largest positions make up about 53% of the portfolio, and a single position at the cut-off can matter: with one stock fewer or one more at every rebalance the return is 17.8% or 17.5%.
* **It is an in-sample result.** The rule set was chosen for this project with knowledge of how momentum strategies had performed over the period. Past performance is not a reliable guide to future performance.

A real fund on the same index (SPMO) earned 17.9% a year over the same decade; the backtest gives 18.0% before costs (correlation 0.986).

One data limitation matters more than the others: Yahoo Finance no longer carries companies that were acquired or went bankrupt, and its share counts start in October 2015, so between 2% and 23% of the index's companies cannot be ranked. A comparison with SPY puts the resulting overstatement of stock returns at roughly 0.3 percentage points a year.

## Run it

**Google Colab.** [Open the notebook in Colab](https://colab.research.google.com/github/benediktproebstl/quantile-alpha/blob/main/Financial_Modeling_Quantile_Alpha.ipynb), then *Runtime → Run all*. No key, no data file and no installation are needed. A full run takes about five to fifteen minutes, most of it Yahoo downloads (the run with fresh downloads on 2026-11-25 took 7.5 minutes).

**Your own computer.**

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

```bash
jupyter notebook Financial_Modeling_Quantile_Alpha.ipynb
```

`requirements.txt` lists what the engine and the app need (it is what Streamlit installs); `requirements-dev.txt` adds what the notebook, the tests and the prospectus build need.

Downloads are cached in `~/.cache/quantile_alpha` and reused until the end of the day (UTC). Set the environment variable `QA_USE_CACHE=0` to download again at once.

A FRED API key is optional. With `FRED_API_KEY` set (environment variable or Colab secret) the official FRED API is used; without it, FRED's official key-less CSV endpoint. The notebook prints which route it took.

## The investor prospectus

`investor_prospectus.pdf` is built from what the notebook writes: the figures in `outputs/prospectus/` and the table `outputs/tables/tab_prospectus_key_figures.csv`, which holds every number the prospectus quotes (223 of them, each with the notebook section it comes from). The build script calculates nothing. It stops if a sentence of the text no longer fits the numbers, or if a page overflows.

```bash
python prospectus/build_prospectus.py
```

**Student numbers.** This repository is public, so the notebook and the prospectus in it name the group members without their student numbers. The numbers are in `prospectus/details.local.toml`, which git ignores. `python tools/make_submission.py` writes the two files for Moodle, with the numbers, into `submission/` (ignored as well).

The script needs Google Chrome, Chromium or Microsoft Edge to print the PDF. The group's name, its members, the submission date, the link of the deployed app and the members' own checks of the AI's work are entered in `prospectus/details.toml`; while one of them is missing, the cover and the page footers say "Draft".

## The tracker app

`tracker_app.py` is a Streamlit app around the same strategy. The user chooses the benchmark (the S&P 500 fund SPY, the cap-weighted universe or the momentum fund SPMO) and changes an assumption: the trading cost, the weighting, the weight limit per stock, the number of stocks held, the rebalancing months or the buffer rule. Every change runs `run_backtest` from `quantile_alpha/engine.py` again, the code exported from the notebook, so the app's figures are the notebook's: with the prospectus settings it shows 17.8% a year against 14.9% for SPY.

```bash
pip install -r requirements.txt
```

```bash
streamlit run tracker_app.py
```

**Data.** The app starts from the snapshot in `app_data/` (3.1 MB, written by `python tools/make_app_snapshot.py` from the downloads of 2026-11-25 02:14 UTC): monthly returns, momentum scores and index weights of the S&P 500 stocks, which is what a backtest reads. Daily prices and share counts are not stored. Without that folder the app retrieves everything from Yahoo Finance, FRED and Wikipedia through the engine, which takes five to fifteen minutes at the first start.

**Deploying it (needs the Streamlit account of a group member).**

1. Sign in at <https://share.streamlit.io> with the GitHub account that owns this repository.
2. *Create app* → repository `benediktproebstl/quantile-alpha`, branch `main`, main file `tracker_app.py`. Under *Advanced settings* choose Python 3.12. A FRED key is not needed; if you have one, add `FRED_API_KEY = "..."` under *Secrets*.
3. Open the link Streamlit gives you and check that the page shows the figures above.
4. Enter the link as `app_url` in `prospectus/details.toml` and at the top of the notebook, then rebuild the prospectus.

More in `docs/tracker_app.md`.

## What is in the repository

| Path | Content |
|---|---|
| `Financial_Modeling_Quantile_Alpha.ipynb` | The deliverable: the notebook with all outputs. **The single source of truth for the code.** |
| `quantile_alpha/engine.py` | The calculation engine, exported from the notebook cells marked `# [engine]`. Used by the tests and by the app. Do not edit by hand. |
| `investor_prospectus.pdf` | The second deliverable: the prospectus, a cover and seven pages. |
| `prospectus/` | Text and layout of the prospectus (`template.html`, `style.css`), the group's details (`details.toml`) and the build script. |
| `tracker_app.py`, `.streamlit/config.toml` | The Streamlit app and its theme. |
| `quantile_alpha/app_data.py`, `tools/make_app_snapshot.py`, `app_data/` | The app's data: download through the engine, the part a backtest reads, and the stored snapshot. |
| `static/` | The typeface Inter (SIL Open Font License), used by the prospectus, its figures and the app. |
| `tests/test_engine.py` | 46 tests on synthetic data, exported from the notebook cell marked `# [tests]`. |
| `tests/test_app_data.py`, `tests/test_tracker_app.py` | Tests of the app: its data files give the same backtest as the full data, its first page shows the engine's figures, and every control runs. |
| `tools/export_engine.py` | Re-exports the engine and its tests after the notebook was changed. |
| `tools/make_submission.py` | Writes the two files for Moodle, with the student numbers, into `submission/` (not in the repository). |
| `outputs/figures`, `outputs/tables` | Every figure (PNG, 200 dpi) and table (CSV, full precision) of the notebook. |
| `outputs/prospectus` | The five figures of the prospectus, as the notebook draws them (SVG and PNG). |
| `docs/methodology.md` | The rules and conventions on one page. |
| `docs/decision_log.md` | Who decided what and why, including the open points for the group. |
| `docs/data_feasibility.md` | What Yahoo, FRED and Wikipedia can and cannot deliver; ticker mapping; share counts; coverage; bias estimate. |
| `docs/assignment_compliance.md` | Requirement by requirement: where it is met, what is still open. |
| `docs/validation_report.md` | What was tested, in which environment, and what was not tested. |
| `docs/ai_usage_log.md` | AI disclosure: tools, purpose, checks. The members' own checks still have to be filled in. |
| `docs/tracker_app.md` | How the app works, how it is tested and deployed, and what it cannot do. |

## Changing the notebook

Edit the notebook, run it from top to bottom, then

```bash
python tools/export_engine.py
```

```bash
pytest
```

`python tools/export_engine.py --check` tells you whether the exported files still match the notebook.

## Data sources

* **Yahoo Finance** through the open-source `yfinance` package: daily prices and the history of shares outstanding of index members (for renamed companies also under their former ticker symbols); prices of SPY, SPMO and the S&P 500 total-return index. Returns use the adjusted close.
* **FRED** (Federal Reserve Bank of St. Louis): `DGS3MO`, the 3-month Treasury yield used as the risk-free proxy, and `USREC`, the NBER recession indicator used in the Monte Carlo section.
* **Wikipedia**, through its API at two pinned page revisions: the dates on which companies entered and left the S&P 500. Ticker lists only; no prices. Text licensed CC BY-SA 4.0.
* **Index rules**: *S&P Momentum Indices Methodology*, S&P Dow Jones Indices, edition of November 2026. Rules only, no data. This project is not sponsored or endorsed by S&P Dow Jones Indices or by Invesco.

The only market data stored in this repository are in `app_data/`: monthly returns, momentum scores and index weights derived from the downloads, for the app. The notebook does not read them; it retrieves everything through the APIs.

## Before submission: open points for the group

Reported by Benedikt Proebstl for the group on 25 November 2026: the decisions S1 to S5 are confirmed; the notebook ran from start to finish in Google Colab; the members did their own checks of the AI-written code and results; the fund fees quoted were checked. The group is BC, with 6 members.

- [ ] Enter the submission date in `prospectus/details.toml`.
- [ ] If the Colab run was made before the notebook of 25 November 2026 was pushed, repeat it once from the link at the top: section 12.6 is new.
- [ ] Read the prospectus and make it yours: every member should be able to explain each page.
- [ ] Deploy the app on Streamlit (steps above), check the link, and enter it in the notebook and in `prospectus/details.toml`. Without a working link the app earns no marks.
- [ ] Rebuild the prospectus (`python prospectus/build_prospectus.py`) and check that the word "Draft" is gone.
- [ ] Run `python tools/make_submission.py` and submit the two files it writes into `submission/` on Moodle: `investor_prospectus.pdf` and `Financial_Modeling_Quantile_Alpha.ipynb`.

## Use of AI

The code, tests and text in this repository were written with Claude Code (Anthropic) from the group's strategy specification and instructions. What the tool did, how its output was checked and what could not be checked is recorded in `docs/ai_usage_log.md`. The group remains responsible for understanding the code and for the conclusions.
