# Decision log

Who decided what, when, and why. "Group" means a decision recorded in the group's strategy specification. "Session" means a decision taken on 24 November 2026 by the group member working with the AI assistant; these still need the other members' confirmation. "AI" means an implementation choice made by the AI assistant that the group should review.

## Decisions by the group

| # | Decision | Source |
|---|---|---|
| G1 | Universe: historical S&P 500 constituents, individual U.S. stocks, USD | Strategy specification |
| G2 | A price-momentum strategy; long-only; no leverage, derivatives, short selling or defensive overlay | Strategy specification |
| G3 | Costs: 10 bp per dollar bought or sold, including the initial purchase | Strategy specification |
| G4 | Data: Yahoo Finance (yfinance) and FRED | Strategy specification; instruction of 24 Nov 2026 |
| G5 | Primary benchmark: SPY | Strategy specification |
| G6 | Sample ends December 2025 | Strategy specification |
| G7 | Target client: U.S. retail investor, USD, horizon of at least ten years, high risk tolerance | Strategy specification |
| G8 | App and prospectus are built after the notebook (both were built on 25 November 2026) | Strategy specification; instructions of 24 and 25 Nov 2026 |

## Decisions taken in the session of 24 and 25 November 2026

S1 to S5 were confirmed on 25 November 2026 (reported by Benedikt Proebstl). S6 and S7 were decided by the same member on 25 November 2026.

| # | Decision | Why | Alternatives that were offered |
|---|---|---|---|
| S1 | Index membership dates are read from Wikipedia (two pinned page revisions, through the MediaWiki API). Prices, share counts and rates still come only from Yahoo Finance and FRED. | Neither Yahoo nor FRED provides historical index membership. Using today's members would be the survivorship flaw Lecture 4 warns about. Decided when only data coverage had been measured. | (a) switch to an ETF universe with Yahoo/FRED only; (b) hard-code today's S&P 500 list |
| S2 | Continue although the 95% coverage gate fails (77.0% of the index's issuers can be ranked at the first purchase, 98.2% at the last rebalance; 385 stocks at the first date against a gate of 400). | Yahoo deletes delisted companies, so no sample passes with Yahoo as the only source. The gap is measured (comparison with SPY) and disclosed. | Stop and report a blocker |
| S3 | The strategy applies the published construction rules of the S&P 500 Momentum index, the index tracked by the SPMO fund: risk-adjusted 12-month momentum without the most recent month; the best fifth, with the 20% buffer rule; weights = market value × momentum score, at most 9% per stock and three times the market-value weight; rebalanced at the end of March and September. | The member's choice, made knowing that the fund on this index had done better than the S&P 500 over the sample period. The notebook therefore treats the result as in-sample (section 8). | (a) a simpler rule: plain momentum with weights by market value only; (b) holding the SPMO fund itself |
| S4 | Sample: January 2016 to December 2025. | Yahoo's share counts, which the weights need, start in October 2015. | – |
| S5 | The GitHub repository is public (`benediktproebstl/quantile-alpha`). | The member's choice; no reason was recorded. Consequences: anyone, including other groups, can see the work before the deadline; the notebook opens in Colab directly from its link; the app submission requires a public repository in any case. | Private repository with invited collaborators |
| S6 | The investor prospectus and the tracker app share one design: a white page, light-grey tiles with a hairline border and rounded corners, the typeface Inter with tabular figures, green for gains, highlights and progress bars, and orange for risk notices and losses only. The app is one centred column of at most 900 pixels without Streamlit's menu. | The member's instruction of 25 November 2026: a clean neobank look for both deliverables. It replaces the navy and teal design of the strategy specification. | The design of the strategy specification |
| S7 | The public repository holds a data snapshot for the app (`app_data/`): monthly returns, momentum scores and index weights of S&P 500 stocks derived from the Yahoo Finance downloads. Daily prices and share counts are not stored. | The member's choice of 25 November 2026, made after being told that Yahoo's terms restrict redistributing its data and that without the snapshot the app has to download for five to fifteen minutes after every restart of the server, which a grader would have to sit through. | The app downloads everything at each start; no market data in the repository |

## Implementation choices made by the AI assistant (please review)

| # | Choice | Reason |
|---|---|---|
| A1 | FRED is read through the official API when `FRED_API_KEY` is set and otherwise through FRED's official key-less CSV endpoint. The notebook prints which route was used. | Graders will not have a key; the notebook must run without one. The key route could not be tested live (no key was available). |
| A2 | Risk-free return of month *m* = (1 + y/100)^(1/12) − 1 with *y* the last DGS3MO value published strictly before the trade date; a yield older than ten days is not used. | Uses only published information; converts an annual percentage yield to a monthly return. |
| A3 | Trades are executed at the closing price of the **last** session of March and September, not after the third Friday as in the index. Scores, market values and weights are those of the reference date one month earlier. | The engine works with month-end prices. The trade is one to two weeks later than the index's; no input is newer than the reference date. |
| A4 | First purchase at the close of 31 December 2015 with 30 November 2015 as reference date; afterwards the March and September calendar. | Gives ten full calendar years; Yahoo's share counts do not reach back to the index's own September 2015 rebalance. |
| A5 | Eligibility at the reference date: index member, Yahoo carries the history, a price on that date, a momentum value (twelve months, or nine if there is no price thirteen months back), at least 150 days traded in the measurement period, a share count. A stock's price history starts on its first day of regular trading (the first day from which Yahoo reports volume on each of the next sixty trading days). | The index's own conditions, plus what the data require. All observable on the reference date. For two members (Smurfit Westrock, Amcor) Yahoo shows prices from before the US listing, from a foreign line that trades rarely or not at all; they are not the listed stock's. |
| A6 | Ranking by the capped z-score; ties by the uncapped risk-adjusted value, then alphabetically. Quintiles for the analysis have equal counts, extra stocks to the highest groups. The strategy holds one fifth of the **eligible** stocks (the index: one fifth of its whole universe, 100 stocks), z-scores are computed across the eligible stocks, and the buffer rule favours the stocks actually held. | The methodology does not say how ties are broken; this makes the result deterministic. With part of the index missing, a fifth of what can be ranked keeps the selection as strict as the index's; the variant with 100 stocks is in section 8.1. |
| A7 | The second weight limit, "three times the security's market capitalization weight in the index", is read as three times the stock's market-value weight among the selected stocks. The other reading (weight in the S&P 500) is reported as a variant; there the multiple is raised step by step whenever the limits would leave no room for 100%. | Under the first reading the limits could be met at every rebalance. Under the second they could not at most rebalances, and the methodology gives no rule for that case. |
| A8 | Market capitalisation = Yahoo's share count × closing price, per company; one share class per issuer (GOOG, FOX, NWS and other second classes are excluded). | Yahoo has no history of free float, which the index uses, and reports share counts per company. |
| A9 | Six rules for the share counts: (1) counts are read under the ticker the company had at the time, using a hand-written table of 46 renamed companies (`TICKER_HISTORY`); (2) conversion to today's split units, including splits after the sample, with spin-off factors undone on the price side; (3) near a real stock split the unit closest to the stock's other counts is used; (4) the last count before Yahoo's general gap of August 2017 to November 2018 is left out; (5) a count more than a factor of 1.25 away from the last accepted one needs a second count that agrees; (6) the latest accepted count is used, and a stock's first count is carried back at most 120 days. | Yahoo files counts under the ticker of the time, is unreliable about the unit near splits, has a general gap in 2017-18 before which many counts were entered later, and contains one-off wrong values; its history starts in October 2015. A count carried back across a merger can be several times too large, hence the limit. The thresholds (120 days, 180 days, 25%) are judgements; section 8.1 of the notebook shows that the result does not depend on them. See `data_feasibility.md`, section 5. |
| A10 | A stock that leaves the S&P 500 is held until the next rebalance; a selected stock that has left the index or has no price by the trade date is not bought. | The index removes deleted stocks at once; holding them avoids extra trades in a monthly engine. Few cases. |
| A11 | Benchmarks and checks: SPY (primary); the cap-weighted portfolio of all eligible stocks on the same calendar and costs; the SPMO fund as a check of the backtest, not as a benchmark. | The universe portfolio separates the rules from the data; the fund shows whether the backtest reproduces the index. |
| A12 | Eighteen former tickers are mapped by hand to the Yahoo symbol that carries the history today; former members whose Yahoo symbol now belongs to another security are blocked, and so is Johnson Controls before its merger with Tyco in September 2016, because Yahoo shows Tyco's history under `JCI` for that time. One price restatement for which Yahoo lists no factor (Howmet, April 2020) is entered by hand. | See `data_feasibility.md`, sections 4 and 5, for the lists and the evidence. |
| A13 | A held stock that stops trading is valued at its last quote; the proceeds are held as cash earning the risk-free proxy until the next rebalance. | Did not occur in the sample, because Yahoo removes delisted companies entirely. |
| A14 | Net asset value is recorded before trading; the cost of a trade lowers the following month's return. Gross returns come from a separately simulated zero-cost run. Turnover, cost and orders per year = average per scheduled rebalance × rebalances per year. | Exact, self-financing accounting; the first purchase is shown separately. |
| A15 | Information ratio = active return over tracking error (against SPY). The regression-based version (alpha over residual volatility) is reported as the appraisal ratio. | Lecture 3 shows both definitions; the brief asks to pick one and say which. |
| A16 | Alpha and beta standard errors: Newey–West with ⌊4 (N/100)^(2/9)⌋ lags, small-sample correction, t-distribution. | Monthly returns show mild autocorrelation and changing volatility. |
| A17 | Block bootstrap: circular, block length 6 months, 2,000 resamples, seed 2270, percentile intervals; block lengths 3 and 12 as sensitivity. | Keeps short-lived autocorrelation; all series are resampled with the same months. |
| A18 | Random-portfolio baseline: 1,000 portfolios with the strategy's calendar, number of holdings and weight limits; stocks drawn at random and weighted by market value; compared with the strategy before costs. | Shows what luck alone produces under these rules (Backtesting notes, lesson 6). A random portfolio replaces far more of its holdings at each rebalance, so a comparison after costs would favour the strategy for a reason unrelated to the score. |
| A19 | Stock-level tests use every month: the scores known for a trade at that month-end against the next month's return. | 120 cross-sections instead of 21 rebalance dates. |
| A20 | Monte Carlo design: two-state Markov chain for expansion/recession (transition matrix from 1947 to 2025), market excess returns resampled within state from the S&P 500 total-return index (1988 to 2025), strategy linked by the market model from the backtest, two alpha scenarios, 10,000 paths, 120 months. The independent coin-flip design is run alongside. | Lecture 5 and the meeting notes: the simulation design must be stated and justified, and a constant growth rate is not an acceptable model. |
| A21 | Where Yahoo records a spin-off both as a split factor and as a dividend, the adjusted-close return of that day is replaced by the close return if the close return is nearer to the market's return. | Yahoo counts these distributions twice, which creates false returns (Danaher, 5 July 2016: +61% instead of +4%). See `data_feasibility.md`, section 9. |
| A22 | Share prices in the retail example are the prices quoted on the trade date: splits since then are undone. | Yahoo restates past prices for later splits, which makes expensive shares look cheap. |
| A23 | Sector analysis uses today's sector labels and is descriptive only. No sector-neutral variant. | No historical sector classifications are available from the data sources. |
| A24 | Repository layout: the notebook is the single source of truth; `quantile_alpha/engine.py` and `tests/test_engine.py` are exported from it. | The notebook must be self-contained for Colab, and the app must run the same code. |
| A25 | Chart colours: white background, navy text, blue and teal accents, with orange as the third series colour. The series colours and the quintile ramp were checked for colour-blind separation. | Three series cannot be told apart reliably with blue and teal alone. |
| A26 | Two references that could not be verified by DOI were not used (see `validation_report.md`). | "Do not invent citations." |

## What was deliberately not done

| # | Not done | Why |
|---|---|---|
| N1 | No variant of section 8.1 was made the base case, although 5 of them did better in the sample (One fifth of the index (100 stocks), No risk adjustment, No weight limits, Share counts before Yahoo's outage kept, Share counts under today's ticker only). | The base case is the published rule set. Adopting the best variant would be data snooping. All 22 variants are reported. |
| N2 | No independent third-party membership dataset was downloaded to cross-check Wikipedia. | It would have been a further data source. The reconstruction is checked internally instead (index size, second Wikipedia table). |
| N3 | No free-float adjustment, no daily (third-Friday) trading, no removal of stocks between rebalances. | Not possible with the data sources, or outside a monthly engine. Listed in the notebook, section 4.5, and measured against the real fund in section 5.2. |
| N4 | No tax model, no sector-neutral strategy, no factor model beyond the market model, no machine learning. | Out of scope. |
| N5 | The app does not let the user change the settings of the momentum score (look-back, risk adjustment, share of the index held). | They need the daily prices, which the app's data do not hold. The notebook covers them in section 8.1. |
| N6 | The app was not deployed by the AI assistant. | Deployment needs a group member's Streamlit account. |

## Open points for the group

1. Enter the submission date in `prospectus/details.toml`.
2. If the Colab run was made before the notebook of 25 November 2026 was pushed, repeat it once from the link at the top: section 12.6 is new.
3. Read the prospectus and make it yours: every member should be able to explain each page.
4. Deploy the app on Streamlit (steps above), check the link, and enter it in the notebook and in `prospectus/details.toml`. Without a working link the app earns no marks.
5. Rebuild the prospectus (`python prospectus/build_prospectus.py`) and check that the word "Draft" is gone.
6. Run `python tools/make_submission.py` and submit the two files it writes into `submission/` on Moodle: `investor_prospectus.pdf` and `Financial_Modeling_Quantile_Alpha.ipynb`.
7. Optional: obtain a FRED API key and run once with it, to exercise the official API route.

The prospectus presents the result together with its reservations (not statistically significant, 93% of the final lead earned in 2024 and 2025, dependent on a few very large companies, in-sample): they are on pages 1, 4, 5 and 7. Whether that balance is right is for the group to judge when reading it.
