# Quantile Alpha

A rules-based U.S. large-cap momentum strategy, built for the group assignment of **2270 Financial Modeling**: the best fifth of the S&P 500 by risk-adjusted momentum, weighted by company size and momentum score, following the published construction rules of the S&P 500 Momentum index. This repository holds the research notebook, the calculation engine exported from it, the tests and the project documentation.

Repository: <https://github.com/benediktproebstl/quantile-alpha> · [Open the notebook in Google Colab](https://colab.research.google.com/github/benediktproebstl/quantile-alpha/blob/main/Financial_Modeling_Quantile_Alpha.ipynb)

**Status (25 November 2026): research phase.** The notebook runs from start to finish and reproduces every number, table and figure. The investor prospectus (PDF) and the optional Streamlit app come next.

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

**Google Colab.** [Open the notebook in Colab](https://colab.research.google.com/github/benediktproebstl/quantile-alpha/blob/main/Financial_Modeling_Quantile_Alpha.ipynb), then *Runtime → Run all*. No key, no data file and no installation are needed. A full run takes about five to fifteen minutes, most of it Yahoo downloads (the committed run took 7.8).

**Your own computer.**

```bash
pip install -r requirements.txt
```

```bash
pytest
```

```bash
jupyter notebook Financial_Modeling_Quantile_Alpha.ipynb
```

Downloads are cached in `~/.cache/quantile_alpha` and reused until the end of the day (UTC). Set the environment variable `QA_USE_CACHE=0` to download again at once.

A FRED API key is optional. With `FRED_API_KEY` set (environment variable or Colab secret) the official FRED API is used; without it, FRED's official key-less CSV endpoint. The notebook prints which route it took.

## What is in the repository

| Path | Content |
|---|---|
| `Financial_Modeling_Quantile_Alpha.ipynb` | The deliverable: the notebook with all outputs. **The single source of truth for the code.** |
| `quantile_alpha/engine.py` | The calculation engine, exported from the notebook cells marked `# [engine]`. Used by the tests and by the future app. Do not edit by hand. |
| `tests/test_engine.py` | 46 tests on synthetic data, exported from the notebook cell marked `# [tests]`. |
| `tools/export_engine.py` | Re-exports the two files above after the notebook was changed. |
| `outputs/figures`, `outputs/tables` | Every figure (PNG, 200 dpi) and table (CSV, full precision) of the notebook, for the prospectus. |
| `docs/methodology.md` | The rules and conventions on one page. |
| `docs/decision_log.md` | Who decided what and why, including the open points for the group. |
| `docs/data_feasibility.md` | What Yahoo, FRED and Wikipedia can and cannot deliver; ticker mapping; share counts; coverage; bias estimate. |
| `docs/assignment_compliance.md` | Requirement by requirement: where it is met, what is still open. |
| `docs/validation_report.md` | What was tested, in which environment, and what was not tested. |
| `docs/ai_usage_log.md` | AI disclosure: tools, purpose, checks. The members' own checks still have to be filled in. |
| `docs/app_handoff.md` | How the Streamlit app should call the engine. |

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

No market data are stored in this repository.

## Before submission: open points for the group

- [ ] Confirm the decisions taken on 24 November 2026 (`docs/decision_log.md`, S1 to S5).
- [ ] Fill in the Moodle group name and all members at the top of the notebook.
- [ ] Run the notebook once in Google Colab and record it in `docs/validation_report.md`.
- [ ] Do and record your own checks of the AI-written code (`docs/ai_usage_log.md`, section 6) and complete the AI disclosure in section 12.5 of the notebook.
- [ ] Check the fund fees quoted in the notebook (0.09% for SPY, 0.13% for SPMO) against the providers' current figures, and read S&P's methodology before quoting it.
- [ ] Decide how the prospectus presents the result together with its reservations (notebook, section 12).
- [ ] Write the prospectus (at most 7 content pages) from `outputs/`.
- [ ] Optional, up to 2 extra marks: build and deploy the Streamlit app (`docs/app_handoff.md`), then add both URLs to the notebook and the prospectus.

## Use of AI

The code, tests and text in this repository were written with Claude Code (Anthropic) from the group's strategy specification and instructions. What the tool did, how its output was checked and what could not be checked is recorded in `docs/ai_usage_log.md`. The group remains responsible for understanding the code and for the conclusions.
