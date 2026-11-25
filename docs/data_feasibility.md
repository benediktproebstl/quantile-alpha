# Data feasibility and quality report

What Yahoo Finance, FRED and Wikipedia can and cannot deliver for this project, what was found, and what follows from it. All figures below come from the notebook run of 2026-11-25 03:16 UTC (sections 2, 3, 5.2 and 11.4).

## 1. Access tests

| Source | Result | Notes |
|---|---|---|
| Yahoo Finance prices via `yfinance` | Works without credentials | Tested with yfinance 0.2.66 (Google Colab's version) and 1.8.0. `end` is exclusive: `end="2026-01-01"` returns 31 December 2025 as the last row. `auto_adjust=False` is set explicitly so that both `Close` and `Adj Close` are returned. |
| Yahoo Finance shares outstanding via `yfinance` (`get_shares_full`) | Works without credentials | One request per symbol. Counts are filed under the ticker of the time, and former symbols can still be asked. The history starts in October 2015 for most companies and has a general gap from August 2017 to mid-November 2018. |
| FRED, official CSV endpoint (`fredgraph.csv`) | Works without credentials | The endpoint resets connections that send certain custom `User-Agent` strings, so requests are sent with the default client identification. |
| FRED, official API (`api.stlouisfed.org`) | Requires a key | Without a key the API answers HTTP 400. No key was available, so this route is implemented but **not tested live**. |
| Wikipedia, MediaWiki API | Works without credentials | Tables are read at pinned revisions: "List of S&P 500 companies" revision 1384572480 (8 Nov 2026) and "Historical components of the S&P 500" revision 1387311792 (23 Nov 2026). |

The index rules come from S&P Dow Jones Indices' *S&P Momentum Indices Methodology* (edition of November 2026), which the publisher offers as a PDF download. It supplies rules, no data.

## 2. What Yahoo Finance cannot provide

1. **No historical index membership.** Neither Yahoo nor FRED says which companies were in the S&P 500 on a past date.
2. **No delisted companies.** Of 709 symbols requested (index members since November 2015, plus SPY and SPMO), Yahoo returns prices for 596 and nothing for 113. In practice a company either has its full history on Yahoo or none at all.
3. **Recycled symbols.** Yahoo assigns the symbols of vanished companies to new securities. See section 4.
4. **No free float.** The index weights by float-adjusted market value; Yahoo reports total shares outstanding.
5. **No share counts before October 2015**, almost none from August 2017 to mid-November 2018, and none under some former ticker symbols. See section 5.

Consequence: a survivorship-free backtest of S&P 500 stocks is not possible with Yahoo as the only source of prices. Membership can be made point-in-time; prices cannot.

## 3. Membership reconstruction

Method: start from today's constituents and replay the change log backwards (notebook section 3.1).

Checks:

* 0 unmatched change-log entries after 14 documented ticker-change links (`ADD_ALIASES` in the notebook).
* The reconstructed index has 503-505 tickers at every reference date, which matches the known size of the index since second share classes were admitted in 2015.
* The constituents table has its own "Date added" column. It agrees with the change log for 99.2% of today's members; the disagreements are listed in the notebook, section 3.4.

Not done: a cross-check against an independent third-party membership dataset (it would have been a further data source; see `decision_log.md`, N2).

## 4. Symbol mapping

### 4.1 Ticker changes mapped by hand (same listed security, new symbol)

The engine holds these mappings in `YAHOO_ALIASES` and `YAHOO_ALIASES_BY_SPELL`. Some concern companies that left the index before the sample starts; they are kept so that the list stays complete if the sample is extended.

| Change-log ticker | Yahoo symbol | Company | Evidence |
|---|---|---|---|
| WLTW | WTW | Willis Towers Watson | Change log states the ticker change (10 Jan 2022) |
| DWDP | DD | DowDuPont, renamed DuPont de Nemours | Change log states the rename (3 Jun 2019) |
| KFT | MDLZ | Kraft Foods, renamed Mondelez | Change log; Yahoo shows the Kraft Foods Group spin-off as a 14.17 distribution on 2 Oct 2012 |
| ARNC | HWM | Arconic, renamed Howmet Aerospace | Change log; Yahoo's HWM series starts 1 Nov 2016, the day Arconic began |
| Q (Aug–Nov 2017) | IQV | QuintilesIMS, renamed IQVIA | Change log states the ticker change |
| GPS | GAP | Gap Inc. | Ticker change in 2024; Yahoo history under GAP from 2009 |
| FBHS | FBIN | Fortune Brands Home & Security | Ticker change in 2022; Yahoo history under FBIN from the 2011 listing |
| HFC | DINO | HollyFrontier, now HF Sinclair | Yahoo history under DINO from 2009, continuous through March 2022 |
| ADS | BFH | Alliance Data Systems, now Bread Financial | Yahoo history under BFH from 2009 |
| WYN | TNL | Wyndham Worldwide, now Travel + Leisure | Yahoo shows the Wyndham Hotels spin-off as a split factor on 1 Jun 2018 |
| SAI | LDOS | SAIC, renamed Leidos | Yahoo shows the 2013 separation as a split factor on 30 Sep 2013 |
| JDSU | VIAV | JDS Uniphase, renamed Viavi | Yahoo history under VIAV from 2009 |
| FII | FHI | Federated Investors, now Federated Hermes | Yahoo history under FHI from 2009 |
| BHI | BKR | Baker Hughes | Yahoo shows the 17.50 special dividend of 5 Jul 2017 in the BKR series |
| CCE | CCEP | Coca-Cola Enterprises, now Coca-Cola Europacific Partners | Yahoo shows the 14.50 cash payment of 31 May 2016 in the CCEP series |
| CSC | DXC | Computer Sciences Corporation, now DXC Technology | Yahoo history under DXC from 2009 |
| DPS | KDP | Dr Pepper Snapple, now Keurig Dr Pepper | Yahoo shows the 103.75 special dividend of 10 Jul 2018 in the KDP series |
| DOW (until Sep 2017) | DD | Dow Chemical before the DowDuPont merger | Yahoo's DD closes before September 2017, rescaled by Yahoo's later adjustment factors, match Dow Chemical's prices (about 66.7 on 31 Aug 2017), not DuPont's (about 84) |

### 4.2 Former members blocked because the symbol now belongs to another security

In the sample, two rules block 12 former members:

* Automatic rule (11 tickers): the Yahoo series starts only after the company's index membership began, so it cannot be the same security. ADT, CAM, EMC, INFO, PCL, POM, SBNY, SE, SNDK, STI, TE.
* Explicit list (1 in the sample; the engine's list `REUSED_TICKERS` has six entries): the Yahoo series overlaps the membership period but belongs to a different issuer. DD: Yahoo's `DD` history before September 2017 is Dow Chemical's, not that of the old E.I. du Pont de Nemours, whose own history Yahoo no longer carries.

One member that is still in the index is blocked for part of the sample (`FOREIGN_PRICES_BEFORE`): Johnson Controls before 6 September 2016. Tyco International took over Johnson Controls' name and ticker in their merger, and the history Yahoo shows under `JCI` before that day is Tyco's (a split factor of 0.955 on the merger day, and Tyco's dividends).

Without these rules the backtest would have used another company's prices under the old name without any error message. Every blocked member is listed, per rebalance, in `outputs/tables/log_exclusions.csv`.

### 4.3 One share class per issuer

Excluded as second classes: CMCSK, DISCK, FOX, GOOG, NWS, TFCF, UA. Yahoo's share counts are per company, so the primary class carries the company's whole market value.

## 5. Share counts and market capitalisation

Yahoo reports shares outstanding as a series of dated counts (326,084 counts for 594 of 594 securities; first count before 2016 for 535, later for 59). They are the weakest data of the project. Six rules turn them into market values (notebook, section 2; the evidence for each rule is in section 3.2):

1. **The right company.** Yahoo files a count under the ticker the company had at the time, while the price history moves to the current symbol. Under its current symbol a renamed company therefore has no counts before the change, or it has the counts of whoever used that ticker before (Bank of New York Mellon, for example, under `BNY`, which was a closed-end fund's ticker). The engine's table `TICKER_HISTORY` lists 46 renamed companies; 50 former symbols are asked from Yahoo in addition and joined into one series per company. Of the 51 changes of ticker inside the data window, the last count under the old symbol and the first under the new one agree within 3% at 33; the others coincide with a merger or a reverse split, lie on either side of Yahoo's gap, or have no count under the old symbol. Yahoo has nothing under these former symbols: BHI, CBG, CCE, COH, CSC, DPS, HCN, KORS, LUK, MHFI, WYN. The table was written by hand, from the change log where it states the change and otherwise from general knowledge of the companies; `outputs/tables/tab_ticker_changes.csv` shows every entry against Yahoo's data.
2. **Split units.** Yahoo's closing prices are restated for every later split, so each count is multiplied by the split factors after its date, including those after the sample: CMCSA 1.067 (2026-01-05), AMCR 0.2 (2026-01-15), BDX 1.272 (2026-02-10), BKNG 25 (2026-04-06), CVNA 5 (2026-05-08), FDX 1.241 (2026-06-01), KLAC 10 (2026-06-12), POM 0.0555556 (2026-06-22), DD 0.333333 (2026-06-24), HON 0.9535 (2026-06-29), SPGI 1.057 (2026-07-01), CRWD 4 (2026-07-02), MNST 2 (2026-08-11), APH 2 (2026-09-03), CTVA 6.665 (2026-10-01). Of the 211 "split factors" in the price data, 113 are real stock splits; the others are spin-offs and similar events, which change the price but not the share count and are undone on the price side. Market value is therefore the share count times the price actually quoted that day.
3. **Unit errors near splits.** Near a real split some counts are already post-split before the split date and others still pre-split after it. A count within 120 days of a split is read in the unit closest to the stock's other counts, earlier and later ones. 50 counts were read in the other unit.
4. **Yahoo's gap (2017-08-04 to 2018-11-13).** In this period Yahoo has almost no counts for any company. Of the 548 counts that stand directly before it, 70 are identical to the first count after it. 8 stocks split inside the gap, which makes the date of the earlier count testable: for 6 of them it is already in post-split units, so it was entered later than the date it carries. These counts are left out and the count before them is used, so the count in use is about four months old at the reference date of August 2017 and ten and sixteen months old at those of February and August 2018.
5. **A change needs a second count.** A count more than a factor of 1.25 away from the last accepted one (25% above or 20% below) is used only when the next count agrees with it. 278 counts were not accepted. This removes one-off wrong values and share classes reported in turn; a wrong value that Yahoo repeats is accepted.
6. **Latest accepted count; first count carried back at most 120 days**, flagged.

Later information enters in three stated places: the unit near a split (rule 3), the removal of the count before the gap (rule 4, which takes information away) and the carried-back first count (rule 6). The notebook rebuilds every other share count used from the counts dated on or before the reference date (section 11.2). A date, however, is what Yahoo says it is. Its very first counts, from late 2015, show the same sign of later entry as the counts before the gap: 5 stocks split within 150 days after their first count, and for 4 of them that count is already in post-split units. The first purchase rests on a first count for every stock.

One price restatement for which Yahoo lists no factor is entered by hand: HWM 1.304 (2020-04-01) (the separation of Arconic Corp. from what is now Howmet; Yahoo's earlier prices and dividends are divided by that factor).

Plausibility, largest market values in USD billion:

* end of November 2015: AAPL 660, GOOGL 525, MSFT 434, XOM 340, BRK-B 331, AMZN 312, META 295, GE 283
* end of August 2020: AAPL 2,207, AMZN 1,729, MSFT 1,707, GOOGL 1,110, META 835, BRK-B 520, V 465, TSLA 464
* end of August 2025: NVDA 4,280, MSFT 3,766, AAPL 3,556, GOOGL 2,579, AMZN 2,442, META 1,856, AVGO 1,399, BRK-B 1,085

The stricter test is the comparison of the cap-weighted universe with SPY in section 8.

**How much the rules matter.** 5 variants in the notebook (section 8.1) change them one at a time, including one that ignores the table of former tickers; the strategy's return moves by at most 0.11 percentage points a year.

**Members that cannot be ranked for lack of a share count.** At the first purchase 11 index members have no share count within reach: BHI, CBRE, CCE, CPRI, CSC, DPS, JEF, SPGI, TPR, WELL, WYN. These are companies whose ticker changed and for whose former symbol Yahoo has no counts. The number falls to 0 by the last rebalance.

**Known weaknesses that remain.**

* Yahoo's counts are total shares, not free float, and for firms whose listed class is only part of the firm (Interactive Brokers, Blackstone) they cover the whole firm.
* A wrong level that Yahoo reports repeatedly passes rule 5. Found in the reviews: Host Hotels at twice its share count from August to November 2024; UDR about 70% too high from February 2022 into 2023 (held in March 2022 at 0.4%); Charter about 30% above Yahoo's own earlier and later counts in 2017-18 (held in September 2017 at 2.2%). The second reviewer put the effect of correcting these and the other cases it found at under 0.02 percentage points a year.
* A change reported shortly before Yahoo's gap is recognised only after it, because the count that would confirm it is the one rule 4 leaves out (TechnipFMC after its merger of January 2017).
* Rule 3 can choose the wrong unit when a count near a split is wrong for another reason (Under Armour in 2016).
* A ticker that changed hands without a visible trace in the counts would go unnoticed, and Yahoo may restate prices without a factor in more cases than the one found.
* During Yahoo's gap the counts in use are up to sixteen months old.

## 6. Coverage by rebalance

Share of index issuers that can be ranked at the reference date (the first purchase and every March rebalance; all dates are in `outputs/tables/tab_coverage.csv`):

| Trade month | Reference date | Issuers | Eligible | No Yahoo history | Ticker reused | Too little history | No share count | Share count carried back | Median age of the share count (days) | Coverage |
|---|---|---|---|---|---|---|---|---|---|---|
| 2015-12 | 2015-11-30 | 500 | 385 | 89 | 11 | 4 | 11 | 38 | 28 | 77.0% |
| 2016-03 | 2016-02-29 | 500 | 390 | 87 | 10 | 4 | 9 | 1 | 17 | 78.0% |
| 2017-03 | 2017-02-28 | 500 | 410 | 77 | 2 | 3 | 8 | 0 | 14 | 82.0% |
| 2018-03 | 2018-02-28 | 500 | 425 | 64 | 2 | 2 | 7 | 0 | 296 | 85.0% |
| 2019-03 | 2019-02-28 | 500 | 444 | 53 | 2 | 1 | 0 | 0 | 0 | 88.8% |
| 2020-03 | 2020-02-28 | 500 | 452 | 44 | 1 | 3 | 0 | 0 | 11 | 90.4% |
| 2021-03 | 2021-02-26 | 500 | 460 | 37 | 1 | 2 | 0 | 0 | 11 | 92.0% |
| 2022-03 | 2022-02-28 | 500 | 465 | 30 | 2 | 3 | 0 | 0 | 11 | 93.0% |
| 2023-03 | 2023-02-28 | 500 | 474 | 23 | 1 | 2 | 0 | 0 | 11 | 94.8% |
| 2024-03 | 2024-02-29 | 500 | 479 | 19 | 0 | 2 | 0 | 0 | 1 | 95.8% |
| 2025-03 | 2025-02-28 | 500 | 485 | 14 | 0 | 1 | 0 | 0 | 1 | 97.0% |
| 2025-09 | 2025-08-29 | 500 | 491 | 9 | 0 | 0 | 0 | 0 | 0 | 98.2% |

## 7. Quality gates

| Gate | Requirement | Result |
|---|---|---|
| Membership replay | 0 unmatched change-log entries | PASS (0 unmatched) |
| Reconstructed index size | 500-505 tickers at every reference date | PASS (503-505) |
| Membership agrees with a second table | >= 95% of today's members | PASS (99.2%) |
| Eligible securities | >= 400 at every rebalance | **FAIL** (minimum 385) |
| Coverage: index issuers that can be ranked | >= 95% at every rebalance | **FAIL** (minimum 77.0%) |
| Share count dated on or before the reference date, first purchase | >= 95% of eligible stocks | **FAIL** (90.1%) |
| Share count dated on or before the reference date, later rebalances | >= 95% of eligible stocks | PASS (minimum 98.9%) |
| Stale valuations of eligible stocks while held | 0 | PASS (0) |
| Prices positive, dates sorted and unique, December 2025 included | all true | PASS (all true) |

The failing gates and the decision to continue are recorded in `decision_log.md` (S2).

## 8. How large is the resulting bias?

The cap-weighted universe built from the available stocks is compared with SPY, which held every index member in real time:

| | Cap-weighted universe, before costs | SPY | Difference | Tracking error | Correlation |
|---|---|---|---|---|---|
| 2016–2025 | 15.30% p.a. | 14.94% p.a. | +0.36 pp (t = 2.18) | 0.52% | 0.9994 |

SPY charges 0.09% per year. Roughly 0.3 percentage points per year remain as an estimate of the survivorship advantage of the stock universe in this project. SPY and SPMO are not affected. The strategy's lead over SPY is therefore probably somewhat smaller than reported.

The second check is against the real fund on the index the strategy follows:

| | Strategy, before costs | SPMO | Difference | Tracking error | Correlation |
|---|---|---|---|---|---|
| 2016–2025 | 18.02% p.a. | 17.87% p.a. | +0.15 pp (t = 0.17) | 2.70% | 0.9862 |

Single calendar years differ by -4.7 pp to +4.0 pp. The fund's figure is after its fee and its own trading costs.

## 9. Errors in Yahoo's adjusted prices around spin-offs

**What goes wrong.** Yahoo records some spin-offs twice: as a split factor, which is already built into its closing prices, and as a dividend. Its adjusted close then applies both, so the distribution is counted twice and the adjusted series shows a jump that never happened.

**The rule in the notebook** (`repair_double_adjustments`). On every day on which a security has both a split factor and a dividend, the adjusted-close return is compared with the plain close return. If they differ by more than 2 percentage points and the close return is the one nearer to the market's return that day, the close return is used. Nothing else in Yahoo's adjustments is changed.

All 4 such days in the data, June 2014 to December 2025 (2 repaired):

| Security | Day | Split factor | Dividend | Adjusted-close return | Close return | Market | Decision |
|---|---|---|---|---|---|---|---|
| DHR | 2016-07-05 | 1.319 | 24.560 | +61.2% | +3.6% | -0.7% | **close return used** |
| DXC | 2015-11-30 | 1.7412 | 9.083 | +8.4% | -20.5% | -0.4% | adjusted return kept |
| IRM | 2014-09-26 | 1.082 | 0.669 | -0.0% | -2.1% | +0.8% | adjusted return kept |
| XRX | 2017-01-03 | 1.518 | 2.980 | +37.6% | +19.8% | +0.8% | **close return used** |

Spin-offs that Yahoo values wrongly without recording them twice cannot be detected by this rule.

**A convention, not an error.** On days with a very large ordinary distribution Yahoo's adjusted return assumes the payment is reinvested before that day's price move. This convention is kept. The momentum signal uses the close, which is not adjusted for dividends, as the index rules prescribe; a large special cash dividend therefore shows up as a price drop in the signal.

## 10. Other data facts worth knowing

* **Extreme returns** are shown in the notebook (section 11.2) and are neither altered nor removed.
* **Sector labels**: today's classification only (constituents table for current members, Yahoo's company profile for former members).
* **Reproducibility over time**: Yahoo revises adjusted prices and share counts and removes delisted symbols. Two downloads a few minutes apart already differ in the sixth decimal of some prices; results at the precision reported are unaffected. A run several months later will lose the companies delisted in between and can differ visibly. The notebook prints a summary of the data each run used (section 11.4).
* **Licensing**: Yahoo data are for personal use; no raw price data are stored in the repository (the cache is excluded by `.gitignore`). FRED series DGS3MO and USREC are public; Wikipedia text is CC BY-SA 4.0 and is read live, not redistributed. S&P's methodology is quoted in the notebook only in short passages.
