# Validation report

Status of every verification step for the notebook run of 2026-11-25 03:16 UTC. **PASS** means the step was executed and passed, with the evidence named. **NOT TESTED** means it was not executed; nothing is marked as passed on assumption.

## 1. Automated tests (synthetic data)

`pytest` in the repository root, and the same tests inside the notebook (section 11.1).

| Environment | Result |
|---|---|
| Python 3.11.4, pandas 2.2.3, numpy 2.4.6, statsmodels 0.15.0, yfinance 0.2.66 (Google Colab's package versions) | 46 passed |
| Python 3.11.4, pandas 3.1.1, numpy 2.4.6, scipy 1.17.1, yfinance 1.8.0 (newest versions) | 46 passed |

What the tests cover:

| Area | Tests |
|---|---|
| Dates | trade month, reference month and measurement months match the example in S&P's methodology |
| Momentum value and volatility | twelve months without the most recent one; nine months when there is no earlier price; later prices do not enter; volatility from daily price changes |
| Momentum score | z-score, cap at ±3, score formula, the variant without risk adjustment |
| Selection | best fifth; the buffer rule with and without holdings, across three rebalances, favouring only stocks actually held; quintiles with equal counts and alphabetical tie-break |
| Weights | market value × score; the 9% limit and the limit of three times the market-value weight; redistribution of excess weight; the second reading of the limit; drift from the reference date to the trade date; a stock that left the index is not bought |
| Share counts | counts follow the ticker a company had at the time, and another company's counts under the same ticker are dropped; real splits told apart from spin-off factors; conversion to today's units, including a split after the sample; unit errors near a split repaired; market value before and after a spin-off equals shares times the quoted price; the count before Yahoo's gap is left out, a stock's own gap is not; a change needs a second count, and a longer history never alters an earlier decision; latest accepted count, its age, carrying back only within the limit |
| Membership | replay of the change log; no member before its effective date; unmatched entries are reported; two companies that shared a ticker |
| Month-end prices | final scheduled session; no forward fill; stale valuation flagged; an unfinished last month is not a month-end |
| Universe | membership dates, listing history, trading days, share count, no price on the reference date; a member whose earlier Yahoo history is another company's; prices from before regular trading starts do not count for the signal, a single day without volume does |
| Costs | exact self-financing solution; cost equals rate times dollars traded; nothing charged twice; zero when already on target |
| Accounting | NAV starts at 1 before costs; costs hit the following month; weights drift; no trading between scheduled dates; returns compound to NAV; turnover per year |
| Delisting | terminal return from the last quote; proceeds become cash, earn the risk-free rate, are reinvested; an unexplained missing return stops the run |
| Risk-free rate | only yields published before the trade date; annual percent to monthly decimal; a stale yield is not carried forward |
| Price adjustments | a spin-off that Yahoo counts twice is repaired; a real split with a real distribution is left alone; later splits are undone to recover the price actually quoted; a restatement without a listed factor is added by hand |
| Metrics | every formula against a hand calculation; alpha doubles with leverage, Sharpe does not; beta not annualised; undefined ratios are missing, not zero; drawdown measured from the initial value |
| Look-ahead | rewriting all prices and all share counts after a cut-off leaves every earlier score, share count, weight and portfolio value unchanged |
| Backtest function | aligned series, variants, gross run equals a zero-cost run |
| Break-even cost | the reported cost is a root of the net advantage, tested on a case with a crossing and on one without |
| Rank migration, regressions | counts, known relations recovered; the HAC t-statistic against a Newey-West calculation by hand |
| Bootstrap, random portfolios | reproducibility; months stay in order inside a block; random portfolios hold eligible, buyable stocks within the weight limit, as many as the strategy, and their returns are before costs |
| Monte Carlo | transition matrix; Markov chain reproduces recession length, coin flip does not; wealth follows the market model |
| Sector weights, retail example | weights add up; positions smaller than one share |

## 2. Checks on the real backtest (notebook section 11.2)

23 of 23 PASS, including: momentum value and volatility of the first purchase recomputed from the daily closes; selection and weights of the first purchase recomputed without the engine's functions; gross returns of the strategy and of the universe recomputed from the target weights without the accounting engine (largest difference below 1e-12); NAV identities; no weight above either limit on a reference date; cost equal to 10 bp times dollars traded at every rebalance; trades only on scheduled dates; every input dated before the trade; only index members ranked and bought; every share count used rebuilt from the counts reported by the reference date (carried-back first counts are flagged and excluded); no delisting or stale valuation among held positions; the cap-weighted universe and the strategy move with the two real funds.

## 3. Notebook execution

| Run | Result |
|---|---|
| Fresh kernel, empty cache, live downloads, Colab's package versions, 2026-11-25 02:14 UTC | PASS: 96 cells, 0 errors, 7.5 minutes |
| The committed notebook: run again in a fresh kernel at 2026-11-25 03:16 UTC on the downloads of the run above (reused from the cache of the same day), after the group details were entered (1 code cell changed: the requirement checklist) | PASS: 96 cells, 0 errors, 0.6 minutes. Same results as the run above |

| Fresh kernel, newest package versions (pandas 3.1.1, yfinance 1.8.0), 2026-11-25 02:23 UTC, on the separate live download that a complete run with these versions made at 2026-11-24 23:25 UTC | PASS: 96 cells, 0 errors; 46 of 46 tests; the six required measures of the strategy, SPY and the universe differ from the committed run by at most 4.7e-07 |
| Inside Google Colab | **Reported by the group:** a complete run on 25 November 2026 (Benedikt Proebstl). Not recorded: whether that was before or after section 12.6 was added on the same day. The AI assistant has not run the notebook in Colab. To repeat: open <https://colab.research.google.com/github/benediktproebstl/quantile-alpha/blob/main/Financial_Modeling_Quantile_Alpha.ipynb>, choose Runtime → Run all, and compare the table in section 6.2 with the committed version. |

`python tools/export_engine.py --check` confirms that `quantile_alpha/engine.py` and `tests/test_engine.py` are identical to the notebook's engine and test cells.

## 4. App entry point

`prepare_data` followed by `run_backtest` reproduces the notebook's monthly returns and the six required measures exactly (notebook section 11.3): PASS.

## 5. Data quality gates and checks against real funds

See `data_feasibility.md`, sections 7 and 8. 6 gates PASS; 3 FAIL (coverage and share counts at the first purchase) and the deviation is documented. The cap-weighted universe has a correlation of 0.9994 with SPY; the strategy before costs has a correlation of 0.986 with the SPMO fund and differs from it by +0.15 pp a year.

## 6. Index rules

The construction rules were read from S&P Dow Jones Indices' *S&P Momentum Indices Methodology* (edition of November 2026: constituent selection, constituent weightings, rebalancing, appendices A and B, and the list of methodology changes). According to that list the rules for the S&P 500 Momentum index did not change during the sample period: one change took effect in September 2015 (treatment of spin-offs) and one in September 2026 (the 9% limit now applies to the company instead of each share class; the notebook applies it per company throughout). One rule can be read in two ways (the second weight limit); both readings are run (decision log, A7). The funds' fees (SPY 0.09%, SPMO 0.13%) were **not** verified against the providers' current documents.

## 7. References

All 19 journal articles and books in section 12.4 of the notebook were compared with the Crossref database (authors, title, journal, volume, issue, pages, DOI): PASS.

Two references considered during drafting had no Crossref record and were **not** used: Grinblatt, Titman and Wermers (1995, *American Economic Review*) and Politis and Romano (1992, book chapter on the circular bootstrap).

The group should still read any paper it quotes: a DOI check confirms that a paper exists and is cited correctly, not that every sentence about it in the notebook is a fair summary.

## 8. Figures

All 18 figures were rendered and inspected. Series colours (blue, teal, orange) and the five-step blue ramp for the quintiles passed an automated colour-blind separation check; the teal series is below 3:1 contrast on white and is therefore always labelled directly.

## 9. Independent review

On 24 November 2026 the engine, the tests and the executed notebook were given to a second instance of the AI assistant (the same model, started without the author's reasoning) with the task of finding errors rather than confirming the result. **This is not a review by a person**; the group's own checks are still required (`ai_usage_log.md`, section 6).

**Examined and found correct:** the momentum inputs, the classification of the universe and the formation tables (rebuilt as of each date and found identical), the market values of the largest companies, the accounting engine (simulation, rebalance solution, turnover), the performance statistics, the market model, the block bootstrap, the break-even cost, the rank migration, the stock-level tests, the Monte Carlo functions, the risk-free rate and the timing of index membership.

**Findings and what was done about each:**

| Finding of the review | Action |
|---|---|
| For seven companies the share counts under a ticker belonged to an earlier user of that ticker | The cause was found: Yahoo files counts under the ticker of the time. Counts are now read under former tickers (46 renamed companies, 50 former symbols), which also brought back companies that had no share count for years. |
| The last count before Yahoo's gap of 2017-18 carries a later value for many stocks | Left out by rule; the evidence is shown in the notebook, section 3.2. |
| Spin-off factors were applied to share counts older than the spin-off | The factors are now undone on the price side; a test values month-ends before and after a spin-off. |
| Old and one-off wrong counts passed the 180-day median then in use | Replaced by the latest count, with a second count required for a change above 25%; the age of the counts is reported per rebalance. |
| The unit of a count near a split is chosen with the help of later counts, which was not stated | Stated, together with the two other places where later information enters (notebook, section 2). |
| Prices and the list of later splits could come from different days when the cache was reused | Both are taken in one download; the cache is stamped with the day. |
| The random-portfolio comparison was made after costs, although random portfolios trade more | Now made before costs. |
| Departures from the index rules that were not listed: number of holdings, population of the z-scores, counting of trading days, the buffer rule applied to selected instead of held stocks | Listed in the notebook, section 4.5. The buffer rule now uses the stocks held; trading days are counted by volume; a variant with 100 holdings was added. |
| Sentences that said more than the numbers showed | Reworded, or generated from the computed figures. |
| Tests that were too weak: the look-ahead test rewrote prices only; the synthetic market had one share count per stock; little on random portfolios, the bootstrap and the HAC t-statistic | 45 tests instead of 38; the look-ahead test now also rewrites share counts. |

**Effect on the results.** The reviewer measured that the share-count errors it had identified moved the strategy's return by less than 0.01 percentage points a year. Reading counts under former tickers changed more, because companies that had been missing came back: the stocks that can be ranked at the first purchase rose from 364 to 386; the cap-weighted universe followed SPY more closely (tracking error 0.52% a year instead of 0.66%, correlation 0.9994 instead of 0.9990); and the strategy's net return became 17.96% a year instead of 17.73%, its alpha 3.58% (t = 1.39) instead of 3.31% (t = 1.28). The conclusions were unchanged: the lead over SPY is not statistically significant, most of it was earned in 2024 and 2025, and it depends on a few very large companies.

**Second review.** The corrected code was then given to a further instance with the same task. It reproduced the result independently, rebuilt every share count used from the counts dated up to each reference date in code of its own (9,414 stock-dates, no difference), examined every entry of the ticker table and the 150 largest companies at four dates, and ran the tests against 29 copies of the engine, each with one planted bug.

| Finding of the second review | Action |
|---|---|
| Johnson Controls was ranked before September 2016 on prices that are Tyco's: Yahoo shows Tyco's history under `JCI` before the two merged | Not ranked before that date (`FOREIGN_PRICES_BEFORE`). |
| Yahoo restates Howmet's prices before April 2020 without listing a factor; its market value was about 23% too low | The factor is entered by hand, with the evidence from Yahoo's dividend history (`UNLISTED_PRICE_FACTORS`). |
| Counting only days with trading volume excluded Crown Castle at one rebalance because of a single faulty row in Yahoo's data, and still let thinly traded pre-listing prices of Amcor count | Replaced by a first day of regular trading for each stock. |
| A former symbol's own series kept counts that belong to the renamed company | Removed from it. |
| 12 of the 29 planted bugs were not caught by the tests | Tests extended to 46. All 27 planted bugs that still apply to the code are caught now; two concerned code that was replaced. |
| Texts: the 25% band of rule 5 is a factor of 1.25; rule 4 also affects the August 2017 reference date; one change of ticker (Under Armour) was explained wrongly; "the cleaning rules do not drive the result" rested on variants that left out the ticker table | Reworded; a variant without the ticker table was added. |
| The dating of Yahoo's very first counts cannot be verified: four of the five that can be tested are in post-split units | Stated in the notebook, sections 2 and 3.2; the quality gate now says "dated", not "reported". |
| Wrong counts that Yahoo repeats pass the second-count rule (Host Hotels 2024, UDR 2022-23, Charter 2017-18), and the counts for Interactive Brokers and Blackstone cover more than the listed class | Not corrected; stated as limits of the data (`data_feasibility.md`, section 5). The reviewer put the effect of correcting them, together with the Johnson Controls and Howmet cases and the rule interactions it found, at under 0.02 percentage points a year. |

**Effect on the results.** The reviewer measured the three stated uses of later information (notebook, section 2) at 0.07 percentage points a year together. One of its corrections changed the result visibly, and by chance: Amcor can no longer be ranked in March 2020, so one stock fewer is eligible, the strategy holds 90 instead of 91 stocks at that rebalance, and the stock that drops out is Nvidia, which doubled over the following six months. The strategy's net return is therefore 17.80% a year instead of 17.96%, its alpha 3.46% (t = 1.35). The notebook now shows this sensitivity directly: with one stock fewer or one more at every rebalance the return is 17.76% or 17.50% (section 8.1).

**Not reviewed again.** The corrections made after the second review were tested (section 1) and compared with the run before them, table by table, but they were not given to a third review.

## 10. Prospectus and tracker app

**Prospectus.** `python prospectus/build_prospectus.py` was run on the outputs of this notebook run. The script

* prints 223 key figures from `outputs/tables/tab_prospectus_key_figures.csv` and calculates none itself;
* checks 24 statements of the text against those figures (for example "the strategy returned more than the index fund", "alpha is positive but not statistically significant", "equal weights trail the index fund") and stops if one no longer holds;
* asks the browser, page by page, whether the content fits, and stops if a page overflows;
* counts the pages of the PDF: a cover and 7 content pages.

Checked afterwards by the AI assistant: every page looked at as an image; the PDF is A4, its text can be selected, and the typeface Inter is embedded. The PDF is 0.43 MB.

**App.**

| Check | Result |
|---|---|
| A backtest on the app's data files gives the same monthly returns as a backtest on the full data | PASS: largest difference 4.4e-16 (`tools/make_app_snapshot.py`) |
| The same on a synthetic market, including a round trip through the files and every assumption the app changes | PASS (`tests/test_app_data.py`) |
| The first page shows the engine's figures; every control reruns the engine; all three benchmarks and all four periods; an impossible combination is explained; the reset restores the prospectus settings | PASS (`tests/test_tracker_app.py`, run without a browser) |
| With the prospectus settings the app shows the figures of this notebook run | PASS: 17.80% a year stored with the data, 17.80% in the notebook |
| The route without a snapshot (download through the engine) | PASS on this computer, with the downloads of the notebook run |
| `requirements.txt` installed into empty environments with Python 3.11, 3.12 and 3.13 (25 November 2026) | PASS: the app's tests pass in each of the three |
| Looked at in a browser: layout, typeface, colours, charts, every control clicked once | Done by the AI assistant, on this computer |

## 11. Not tested

| Item | Why | How to test |
|---|---|---|
| Official FRED API route (with key) | No key available | Add a `FRED_API_KEY` secret in Colab or the environment and run; the notebook prints the route used |
| Free-float weights | No data source | Compare the strategy's largest weights at one rebalance with the fund's published holdings of that date |
| Yahoo's share counts company by company | Checked in aggregate, for the largest and for the renamed companies only | Compare the market values in `outputs/tables/tab_holdings.csv` for one rebalance with the companies' reported share counts |
| The app on Streamlit's servers | Deployment needs a group member's Streamlit account | Deploy (README), open the link, check that the prospectus settings show the notebook's figures |
| The app's download route on Streamlit's servers | Tested only on this computer; Yahoo may limit requests from shared servers | Delete `app_data/` in a test deployment and watch the first start |
| The prospectus on paper and in other PDF readers | Checked as page images only | Open the PDF in Acrobat and print one page |
| Wikipedia change log against an independent membership source | Would need a further data source | Compare a few past quarter-ends with S&P's own announcements |
| Runs on the group members' own computers | – | `pip install -r requirements-dev.txt`, then `pytest` and run the notebook |
