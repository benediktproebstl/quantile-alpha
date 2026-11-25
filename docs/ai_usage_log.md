# AI usage log

The assignment requires disclosing all generative-AI use: the tools, their purpose and how the outputs were checked. This log is the working record; the short version for the prospectus is in section 12.5 of the notebook.

**Nothing in this log claims a check that was not carried out.** Rows marked *to be completed* are for the group members and must be filled in truthfully before submission.

## 1. Tools

| Tool | Version | Used by | When |
|---|---|---|---|
| Claude Code (Anthropic) | model Claude Fable 5.2 | one group member | 24 and 25 November 2026 |
| *Other tools used by the group (for example to draft the strategy specification)* | *to be completed* | *to be completed* | *to be completed* |

## 2. What the AI assistant did

| Task | Output |
|---|---|
| Read the assignment brief, the group's strategy specification, the backtesting notes and Lectures 3 to 5 | Requirement list; conventions for returns, Sharpe ratio, alpha, beta and information ratio taken from Lecture 3; timing convention from Lecture 4; Monte Carlo design from Lecture 5 |
| Read S&P's methodology for the momentum indices | The construction rules in the notebook, section 4, and the list of departures in section 4.5 |
| Tested data access and measured data coverage | `docs/data_feasibility.md` |
| Asked the group member for decisions | `docs/decision_log.md`, S1 to S5 |
| Wrote the calculation engine (data retrieval, membership reconstruction, share counts and market values, momentum score, selection, weights, cost-exact accounting, performance measures, statistical tests, robustness analyses, Monte Carlo) | Notebook cells marked `# [engine]`, exported to `quantile_alpha/engine.py` (about 1,800 lines) |
| Wrote the automated tests | Notebook cell marked `# [tests]`, exported to `tests/test_engine.py` (46 tests) |
| Wrote the notebook's explanatory text, tables and figures | `Financial_Modeling_Quantile_Alpha.ipynb` |
| Looked up and verified the references | Section 12.4 of the notebook |
| Wrote the repository documentation | `README.md`, `docs/` |

## 3. Assumptions the AI introduced

Every implementation choice that was left open is listed in `docs/decision_log.md` (A1 to A26) with its reason. The ones with the most influence on results:

* the six rules that turn Yahoo's share counts into market values, including the hand-written table of former ticker symbols, the 25% threshold for a second count and how far a count may be carried back;
* the reading of the second weight limit;
* trading at month-end instead of the third Friday, and the first purchase in December 2015;
* the mapping of old tickers to current Yahoo symbols and the blocking of reused symbols;
* the rule that replaces Yahoo's adjusted return on days where a spin-off is counted twice;
* the treatment of the risk-free rate (lagged 3-month yield, monthly compounding);
* the Monte Carlo design (two-state Markov chain, post-war transition matrix, market model for the strategy).

## 4. How the AI's output was checked by the AI itself

| Check | What it shows | Result |
|---|---|---|
| 46 automated tests on synthetic data with hand-computable answers | Dates, momentum value, score, buffer rule, weight limits, share counts, membership dates, exact costs, weight drift, delisting cash, risk-free lag, metric formulas, bootstrap, Markov chain, market-model simulation, price-adjustment repair | 46 passed (pytest; also executed inside the notebook, section 11.1) |
| Look-ahead test | All prices and share counts after a cut-off date are rewritten; every score, share count, weight and portfolio value up to the cut-off stays identical | Passed |
| Share counts | Every count used rebuilt from the counts reported by the reference date; each change of ticker compared with Yahoo's own counts on both sides; market values screened against trading volume | Rebuild identical; 33 of 51 changes of ticker agree within 3%, the others are explained in the notebook (section 3.2) |
| Independent recalculations | The first purchase (momentum values, volatilities, selection, weights) rebuilt from the raw downloads with plain pandas; the gross returns of the strategy and of the universe recomputed from cumulative products of the stocks held | Largest differences below 1e-12 |
| Accounting, rule and timing checks on the real backtest | NAV starts at 1, returns compound to the final NAV, costs equal 10 bp times dollars traded, trades only on scheduled dates, weight limits respected, every input dated before the trade, members only | 23 of 23 passed (section 11.2) |
| Check against a real index fund | The reconstructed cap-weighted universe against SPY | Correlation 0.9994; the +0.36 pp gap is reported as survivorship bias |
| Check against the fund on the same index | The strategy before costs against SPMO | Correlation 0.986; difference +0.15 pp a year |
| Reused-ticker check | Yahoo's company name compared with the index member's name for former members with Yahoo data | Wrong-company series found and blocked; see `data_feasibility.md`, section 4 |
| Reference check | Authors, title, journal, volume, pages and DOI of every journal reference compared with Crossref | 19 of 19 confirmed; two candidates without a DOI record were not used |
| App entry point | `prepare_data` + `run_backtest` reproduce the notebook's returns and the six required measures exactly | Passed (section 11.3) |
| Full run, environment 1 | Fresh environment with Google Colab's package versions (pandas 2.2.3, yfinance 0.2.66, numpy 2.4.6), live downloads | Completed without error in 7.8 minutes |
| Full run, environment 2 | Newest package versions, on a separate live download made with them | PASS: 92 cells, 0 errors; 46 of 46 tests; the six required measures of the strategy, SPY and the universe differ from the committed run by at most 1.0e-05 |
| Independent review by a second AI instance | Engine, tests and executed notebook examined for errors; findings and actions in `validation_report.md`, section 9 | Errors in the share-count data and several unstated assumptions found and corrected; not a review by a person |

Errors the AI made and found during the build, for transparency:

* bar charts on date axes were drawn with zero width and appeared empty; found by looking at the rendered figures;
* a download routine relied on an internal attribute of `yfinance` that newer versions no longer fill, and two statements behaved differently under pandas 3; found by the run in environment 2;
* the membership replay at first did not link companies that changed ticker while in the index; found through unmatched log entries and a reconstructed index of more than 500 tickers;
* Yahoo's adjusted prices count some spin-offs twice (Danaher 2016, Xerox 2017), which first passed unnoticed and created a false one-day return of +61%;
* share prices in the retail example were at first taken as Yahoo restates them for later splits;
* market values were at first computed without the stock splits after the end of the sample, which made Booking Holdings (25-for-1 split in 2026) look 25 times too small; found when its market value did not match its size;
* share counts carried back across a merger made Dr Pepper Snapple appear several times too large; found in the list of largest positions, and the reason for the 120-day limit;
* share counts were at first read only under a company's current ticker. Yahoo files earlier counts under the former ticker, so renamed companies were missing for years (Meta Platforms before June 2022) or were valued with another company's count (Bank of New York Mellon, Cencora, Willis Towers Watson and others); found through the independent review and a screen of market values against trading volume;
* the last share count before Yahoo's gap of 2017-18 was used although many of these counts were entered later, and spin-off factors were applied to share counts older than the spin-off; found by the independent review;
* prices that Yahoo shows from before a company's US listing (Smurfit Westrock, Amcor) counted towards the momentum signal; found through their missing trading volume;
* the random-portfolio comparison was made after costs although random portfolios trade more; found by the independent review;
* Johnson Controls was ranked before its 2016 merger on prices that are Tyco's, and Howmet's market value was too low because Yahoo restates its prices without listing a factor; found by the second review;
* a first version of the volume rule excluded Crown Castle at one rebalance because of one faulty row in Yahoo's data; found by the second review;
* twelve of twenty-nine bugs that the second reviewer planted in copies of the engine were not caught by the tests; the tests were extended until all that still apply are caught;
* Dow Chemical's price history before 2017 was at first labelled DuPont;
* draft texts contained statements that would have been wrong if results had come out differently; interpretive paragraphs are now generated from the computed numbers.

## 5. What the AI could not check

| Item | Status |
|---|---|
| A run inside Google Colab itself | NOT TESTED. The environment was reproduced locally with Colab's package versions. |
| The official FRED API route with a key | NOT TESTED. No key was available; the key-less official endpoint was used. |
| Completeness and correctness of every entry in Wikipedia's change log | Checked only through the index size and the second table. |
| Yahoo's price adjustments and share counts for individual companies | Checked in aggregate (against SPY), for the largest companies and for the renamed companies (notebook, section 3.2). Single wrong counts remain possible; two are named in `data_feasibility.md`, section 5. |
| The free-float factors the index uses | No data source. |
| The funds' fees (SPY 0.09%, SPMO 0.13%) | Not looked up. |
| The Streamlit app | Not built yet. |

## 6. Checks by the group members

*To be completed by the group before submission. The assignment makes the group responsible for understanding the code and for the conclusions.*

| Member | What was checked | How | Date | Result |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |

Suggested checks that do not require reading all the code:

1. Open `outputs/tables/tab_monthly_returns_net.csv` (monthly returns of the strategy, the benchmarks and the risk-free rate) and recompute the six required measures in a spreadsheet.
2. Pick one rebalance and one stock from `outputs/tables/log_exclusions.csv` and confirm on Yahoo Finance that the symbol really has no data.
3. Pick one stock from `outputs/tables/tab_holdings.csv` and recompute its momentum value from Yahoo's closing prices by hand; compare its market value with the company's size at the time.
4. Compare the largest positions of one rebalance in `tab_holdings.csv` with the SPMO fund's published holdings of that time.
5. Run the notebook in Google Colab (Runtime, Run all) and compare the headline table with the committed version.
6. Read the engine cells for the momentum score, the buffer rule and the weight limits, and explain them to another member.

## 7. Unresolved limitations

See section 12.3 of the notebook. The most important ones: the result is in-sample; the portfolio is concentrated in a few very large companies; and Yahoo Finance as a source has survivorship bias and only approximate market values.
