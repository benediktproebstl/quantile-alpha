# Methodology on one page

A summary of the conventions for writing the prospectus. The notebook (sections 2 to 4 and 10) is the full and authoritative description. The construction rules are those of the S&P 500 Momentum index (*S&P Momentum Indices Methodology*, S&P Dow Jones Indices, edition of November 2026).

## Universe

* S&P 500 members on each reference date, reconstructed by replaying the index change log backwards from today's constituents. One share class per issuer.
* A stock is eligible if it is a member on the reference date and has: a price on that date, a momentum value, at least 150 trading days in the measurement period, and a share count. A stock's price history starts on its first day of regular trading: the first day from which Yahoo reports trading volume on each of the next sixty trading days. Companies whose history Yahoo no longer carries cannot be included (survivorship limitation), and a member whose history on Yahoo is another company's for part of the time (Johnson Controls before September 2016) is not ranked then.

## Momentum score (reference date = last trading day of February and August)

1. Momentum value = P(m−1) / P(m−13) − 1, with *m* the reference month and *P* the month-end closing price without dividends: twelve months, the most recent month left out. Nine months if there is no price thirteen months back.
2. Risk adjustment: momentum value divided by the standard deviation of the stock's daily price changes over the same period.
3. Z-score across all eligible stocks, capped at ±3.
4. Momentum score = 1 + z if z > 0, and 1 / (1 − z) if z < 0.

## Selection

* The best fifth of the eligible stocks by z-score (ties: uncapped risk-adjusted value, then alphabetical). The number held is the number of eligible stocks divided by five, rounded; one eligible stock more or fewer can change it by one.
* 20% buffer rule, with N the number of stocks to hold: the best 0.8 × N are selected; stocks already held that rank within the best 1.2 × N are kept until N is reached; remaining places go to the best stocks not yet selected.
* Quintiles Q1 to Q5 (Q5 = highest scores) are used for analysis only; they have no buffer.

## Weights

* Raw weight ∝ market capitalisation × momentum score, at the reference date.
* Limits, applied on the reference date: at most 9% per stock, and at most three times the stock's market-value weight among the selected stocks. Weight above a limit is passed on to the other stocks in proportion to their raw weights.
* The weights drift with prices from the reference date to the trade date, so a weight can already be above 9% when it is bought.
* Market capitalisation = Yahoo's share count × the price quoted that day. Six rules for the share counts (notebook, section 2):
  1. counts are read under the ticker the company had at the time (`TICKER_HISTORY` lists the former symbols of renamed companies);
  2. counts are converted to today's split units; spin-off factors, which Yahoo also applies to past prices, are undone on the price side;
  3. near a real stock split the unit closest to the stock's other counts is used;
  4. the last count before Yahoo's general gap of August 2017 to November 2018 is left out;
  5. a count more than a factor of 1.25 away from the last accepted one is used only when the next count agrees with it;
  6. the count at a month-end is the latest accepted one; a stock's first count is carried back at most 120 days and flagged.

## Timing

Reference date: last session of February and August. Trade: closing price of the last session of March and September. First return: the month after the trade. First purchase: 31 December 2015, reference date 30 November 2015. A stock that has left the index or has no price by the trade date is not bought. Membership changes count from their effective date.

## Portfolio accounting

* Long-only, fully invested, fractional shares.
* No trading between rebalance dates: dollar holdings drift with prices.
* Cost c = 10 bp per dollar bought or sold, paid from the portfolio: V* = V − c Σ |wᵢ V* − Hᵢ|.
* NAV starts at 1 before the initial cost. The cost of a trade lowers the following month's return.
* Gross returns: a separate run with c = 0.
* Turnover, cost and orders per year: average per scheduled rebalance × scheduled rebalances per year; the initial purchase is shown separately.
* Delisted holdings: last quote, proceeds in cash at the risk-free proxy until the next rebalance.
* Returns: Yahoo's adjusted close. One correction: on a day where Yahoo records a spin-off both as a split factor and as a dividend, the close return is used if it is nearer to the market's return than the adjusted return.

## Where the backtest departs from the index

Trades at month-end instead of the third Friday; total instead of float-adjusted market capitalisation, per company instead of per share class; only companies Yahoo still carries; one fifth of the eligible stocks instead of one fifth of the whole index (100 stocks); z-scores across the eligible stocks; the buffer rule favours the stocks actually held; a stock that leaves the S&P 500 is held until the next rebalance; 10 bp trading costs. The notebook lists these in section 4.5 and measures their effect against a real fund on the index (SPMO) in section 5.2.

## Benchmarks and checks

* SPY, bought once with the 10 bp cost and held (primary; used for alpha, beta, information ratio, tracking error).
* Cap-weighted universe: all eligible stocks by market value, same schedule and costs.
* SPMO (Invesco S&P 500 Momentum ETF): not a benchmark; the real fund against which the backtest is checked.

## Performance measures

Monthly simple net returns in decimals; sample standard deviation.

| Measure | Formula |
|---|---|
| Average return p.a. | 12 × mean(r) |
| Volatility p.a. | √12 × SD(r) |
| Sharpe ratio | √12 × mean(r − RF) / SD(r − RF) |
| Alpha, beta | OLS of r − RF on r_SPY − RF with intercept; alpha × 12; beta not annualised; Newey–West standard errors |
| Information ratio | 12 × mean(r − r_SPY) / (√12 × SD(r − r_SPY)) |
| CAGR | (final NAV / initial NAV)^(12/N) − 1 |
| Maximum drawdown | min of NAV / running peak − 1, peak including the initial value |
| Risk-free rate | RF(m) = (1 + y/100)^(1/12) − 1, y = last DGS3MO value published before the trade date |

## Statistical tests

* Q5 minus Q1: mean of the monthly difference with Newey–West t-statistic.
* Stock level: every month, regression of the next month's return on the standardised risk-adjusted momentum, and the Spearman rank correlation; averaged over months (Fama–MacBeth).
* Block bootstrap: circular, 6-month blocks, 2,000 resamples, seed 2270, percentile intervals; all series resampled with the same months.
* Random portfolios: 1,000 portfolios with the strategy's calendar, number of holdings and weight limits, stocks drawn at random and weighted by market value; compared with the strategy before costs, because random portfolios trade more.

## Monte Carlo

* Two states of the economy (expansion, recession; FRED `USREC`), monthly, as a **Markov chain** with transition probabilities from 1947 to 2025. An independent coin flip with the same recession share is run for comparison.
* Market excess return in each state: resampled from the S&P 500 total-return index's actual months in that state, 1988 to 2025.
* Strategy return = risk-free + alpha + beta × market excess return + resampled regression residual; alpha at its historical estimate and at zero.
* 10,000 paths of 120 months, USD 100,000, seed 2270.
