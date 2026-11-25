"""Quantile Alpha calculation engine.

AUTO-GENERATED from Financial_Modeling_Quantile_Alpha.ipynb by tools/export_engine.py.
Do not edit by hand: change the notebook cell marked "# [engine]" and re-export.
"""


# [engine] exported to the repo by tools/export_engine.py - see the README
import os, io, re, math, time, logging, warnings, datetime as dt
from dataclasses import dataclass, replace, asdict

import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.CRITICAL)   # failed (delisted) tickers are logged by us instead

USER_AGENT = "quantile-alpha-student-notebook/1.0 (python-requests)"   # sent to Wikipedia only
DATA_LOG = []   # one provenance record per data request: provider, query, returned range, retrieval time


@dataclass(frozen=True)
class Config:
    """Every assumption of the strategy and the backtest in one place."""
    # --- sample: holding months, inclusive. Hard-coded. Yahoo's share counts start in October 2015
    first_holding_month: str = "2016-01"           # Jan 2016 - Dec 2025 (120 months)
    last_holding_month: str = "2025-12"
    # --- raw daily data window. NOTE: yfinance treats `end` as exclusive
    data_start: str = "2014-06-01"                 # the first signal needs prices from October 2014
    data_end_exclusive: str = "2026-01-01"
    # --- signal (S&P Momentum Indices Methodology, Appendix A and B)
    lookback: int = 12                             # momentum value: price change over 12 months ...
    fallback_lookback: int = 9                     # ... or over 9 months for a stock without a price 12 months back
    skip: int = 1                                  # ... ending one month before the reference date
    min_trading_days: int = 150                    # traded on at least 150 days of the measurement period
    risk_adjust: bool = True                       # momentum value divided by the volatility of daily price changes
    winsor_z: float = 3.0                          # z-scores are capped at +/- 3
    # --- selection and weights
    n_groups: int = 5                              # quintiles; the strategy holds the highest one
    target_count: int = 0                          # number of stocks held; 0 = one fifth of the eligible stocks
    target_shift: int = 0                          # added to that fifth (-1 or +1: how much does the last place matter?)
    buffer: float = 0.20                           # 20% buffer rule that favours stocks already held
    weighting: str = "cap_score"                   # market capitalisation x momentum score
    max_weight: float = 0.09                       # on the reference date a stock's weight is at most 9% ...
    max_cap_multiple: float = 3.0                  # ... and at most 3 times its market-cap weight among the holdings
    cap_reference: str = "holdings"                # "holdings" (base case) or "universe": see section 4.3
    reference_lag: int = 1                         # reference date = month-end before the trade date
    rebalance_months: tuple = (3, 9)               # trade at the last close of March and September
    cost_rate: float = 0.0010                      # 10 basis points per dollar bought or sold
    # --- market capitalisation: Yahoo's share counts
    share_confirm: float = 0.25                    # a count more than 25% away from the last one needs a second count (None = off)
    share_gap_days: int = 180                      # a silence of more than 180 days counts as a gap in a stock's share counts
    share_skip_before_outage: bool = True          # leave out the count directly before Yahoo's general outage of 2017-18
    share_carry_back_days: int = 120               # a stock's first count may be carried back at most this far (flagged)
    share_ticker_history: bool = True              # read counts under the ticker of the time (False: today's symbol only)
    # --- benchmarks and risk-free proxy
    benchmark: str = "SPY"                         # investable S&P 500 total-return proxy
    momentum_fund: str = "SPMO"                    # real fund on the S&P 500 Momentum index: check of the replication
    market_index: str = "^SP500TR"                 # long history for the Monte Carlo regime estimates
    rf_series: str = "DGS3MO"                      # 3-month Treasury constant-maturity yield (FRED)
    recession_series: str = "USREC"                # NBER recession indicator (FRED)
    # --- historical index membership: pinned Wikipedia revisions (identical tables on every run)
    wiki_constituents_revid: int = 1384572480      # "List of S&P 500 companies", revision of 2026-11-08
    wiki_changes_revid: int = 1387311792           # "Historical components of the S&P 500", revision of 2026-11-23
    # --- data-quality gates
    gate_min_names: int = 400
    gate_min_coverage: float = 0.95
    gate_min_tracking: float = 0.99                # correlation of the cap-weighted universe with SPY
    # --- statistics and simulation
    seed: int = 2270
    bootstrap_reps: int = 2000
    bootstrap_block: int = 6
    random_portfolios: int = 1000
    mc_paths: int = 10000
    mc_years: int = 10
    mc_regime_start: str = "1947-01"               # post-war business cycles for the transition matrix
    mc_market_start: str = "1988-01"               # first full month of the S&P 500 total-return index on Yahoo


CFG = Config()


def P(month):
    """Month label -> pandas monthly Period."""
    return pd.Period(month, freq="M")


# [engine] exported to the repo by tools/export_engine.py - see the README
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"


def http_get(url, params=None, headers=None, timeout=30, retries=4, pause=2.0):
    """GET with a timeout and bounded retries. The error message never contains query parameters (no key leaks)."""
    last = "no response"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=headers)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (400, 401, 403, 404):      # a retry cannot fix these
                break
        except requests.RequestException as exc:
            last = type(exc).__name__
        time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"Request to {url} failed ({last}). This is an access/network problem, not missing data.")


def get_fred_api_key():
    """FRED key from the environment or from Colab Secrets; None if there is none. The key is never printed."""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        try:
            from google.colab import userdata          # only exists inside Colab
            key = userdata.get("FRED_API_KEY")
        except Exception:
            key = None
    return key.strip() if key else None


def fred_series(series_id, start, end, api_key=None):
    """One FRED series as a float Series indexed by date (NaN where FRED reports no value, e.g. holidays)."""
    if api_key:
        r = http_get(FRED_API_URL, {"series_id": series_id, "api_key": api_key, "file_type": "json",
                                    "observation_start": start, "observation_end": end})
        obs = r.json()["observations"]
        raw = pd.Series([o["value"] for o in obs], index=[o["date"] for o in obs], dtype="object")
        route = "official FRED API (api.stlouisfed.org), key from environment / Colab secret"
    else:
        r = http_get(FRED_CSV_URL, {"id": series_id, "cosd": start, "coed": end})
        table = pd.read_csv(io.StringIO(r.text))
        raw = pd.Series(table.iloc[:, 1].values, index=table.iloc[:, 0].values, dtype="object")
        route = "official FRED CSV endpoint (fred.stlouisfed.org/graph/fredgraph.csv), no key"
    s = pd.to_numeric(raw, errors="coerce")
    s.index = pd.to_datetime(s.index)
    s = s.sort_index().rename(series_id)
    if s.notna().sum() == 0:
        raise RuntimeError(f"FRED returned no observations for {series_id}")
    DATA_LOG.append({"provider": "FRED", "query": series_id, "route": route, "requested": f"{start} to {end}",
                     "returned": f"{s.dropna().index[0].date()} to {s.dropna().index[-1].date()}", "rows": int(s.notna().sum()),
                     "retrieved_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")})
    return s


def monthly_rf(yield_pct, sessions):
    """Monthly risk-free return for every holding month.

    yield_pct : daily DGS3MO, an annualised yield in percent.
    sessions  : Series, month (Period) -> last trading session of that month.
    The return for holding month m uses the last yield published strictly BEFORE the trade date
    (the final session of month m-1), so it was known when the month began:
        RF(m) = (1 + y / 100) ** (1 / 12) - 1
    A yield older than ten days is not used (the result is NaN): if the yield series stops before the price data
    do, the last value must not be carried forward silently.
    """
    y = yield_pct.dropna()
    out = {}
    for m in sessions.index[1:]:
        trade_date = sessions[m - 1]
        known = y.loc[: trade_date - pd.Timedelta(days=1)]
        fresh = len(known) > 0 and (trade_date - known.index[-1]).days <= 10
        out[m] = (1.0 + known.iloc[-1] / 100.0) ** (1.0 / 12.0) - 1.0 if fresh else np.nan
    return pd.Series(out, name="rf")


NO_DATA = "no data on Yahoo (delisted or unknown symbol)"
YAHOO_FIELDS = ["Close", "Adj Close", "Volume", "Dividends", "Stock Splits"]
RETRYABLE_MARKERS = ("rate limit", "too many requests", "timed out", "timeout", "connection", "temporarily", "429", "502", "503")


def _yahoo_messages():
    """Per-symbol error messages of the last yfinance download, where the installed version exposes them."""
    try:
        import yfinance.shared as shared
        return {k: str(v) for k, v in dict(getattr(shared, "_ERRORS", {})).items()}
    except Exception:
        return {}


def _yahoo_batch(symbols, start, end_exclusive):
    """One yfinance request. Returns ({symbol: frame with prices, volume, dividends, split factors}, {symbol: message})."""
    raw = yf.download(symbols, start=start, end=end_exclusive, auto_adjust=False, actions=True,
                      group_by="ticker", threads=True, progress=False, timeout=30)
    frames = {}
    for t in symbols:
        try:
            sub = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = sub.reindex(columns=YAHOO_FIELDS)
            df = df[df[["Close", "Adj Close"]].notna().any(axis=1)]
        except (KeyError, TypeError):
            continue
        if len(df):
            df.index = pd.to_datetime(df.index).tz_localize(None)
            frames[t] = df
    return frames, _yahoo_messages()


def yahoo_daily(tickers, start, end_exclusive, batch=100, retries=3, pause=1.0, canary="SPY"):
    """Daily Close, Adj Close, Volume, dividends and split factors for many tickers from Yahoo Finance.

    Returns a dict of tables (close, adj, volume, dividends, splits) and `status`, which records the outcome
    for EVERY requested ticker.
    A symbol Yahoo no longer carries must not be confused with a failed request, so every batch also asks for a
    reference symbol that certainly exists (`canary`): if not even that comes back, the request failed and the
    batch is retried; if it persists, the run stops instead of silently treating everything as missing. Symbols
    that return nothing are asked for a second time before they are finally recorded as having no data.
    """
    frames, status = {}, {}
    todo = list(dict.fromkeys(tickers))
    for attempt in range(retries + 1):
        failed = []
        for i in range(0, len(todo), batch):
            chunk = todo[i:i + batch]
            try:
                got, messages = _yahoo_batch(chunk if canary in chunk else chunk + [canary], start, end_exclusive)
            except Exception as exc:
                got, messages = {}, {t: type(exc).__name__ for t in chunk}
            if canary not in got:                       # nothing usable came back: a failed request, not missing data
                for t in chunk:
                    status[t] = "request failed"
                failed += chunk
                continue
            for t in chunk:
                message = messages.get(t, "")
                if t in got:
                    frames[t], status[t] = got[t], "ok"
                elif any(marker in message.lower() for marker in RETRYABLE_MARKERS):
                    status[t] = "request failed: " + message[:90]
                    failed.append(t)
                else:
                    status[t] = NO_DATA
            time.sleep(pause)
        todo = failed
        if not todo:
            break
        if attempt < retries:
            time.sleep(15 * (attempt + 1))
    if todo:
        raise RuntimeError(f"Yahoo requests kept failing for {len(todo)} tickers (e.g. {todo[:5]}): network or rate "
                           "limit problem, not missing data. Wait a few minutes and run the cell again.")
    missing = [t for t, outcome in status.items() if outcome == NO_DATA]
    for i in range(0, len(missing), batch):             # second look: a transient glitch must not pass as missing data
        chunk = missing[i:i + batch]
        try:
            got, _ = _yahoo_batch(chunk + [canary], start, end_exclusive)
        except Exception:
            got = {}
        for t in chunk:
            if t in got:
                frames[t], status[t] = got[t], "ok"
        time.sleep(pause)
    table = lambda field: pd.DataFrame({t: f[field] for t, f in frames.items()}).sort_index()
    close, adj, volume = table("Close"), table("Adj Close"), table("Volume")
    dividends, splits = table("Dividends").fillna(0.0), table("Stock Splits").fillna(0.0)
    DATA_LOG.append({"provider": "Yahoo Finance (yfinance " + yf.__version__ + ")",
                     "query": f"{len(status)} tickers, daily, auto_adjust=False, actions=True", "route": "yfinance.download",
                     "requested": f"{start} to {end_exclusive} (end exclusive)",
                     "returned": f"{adj.index[0].date()} to {adj.index[-1].date()}" if len(adj) else "nothing",
                     "rows": int(adj.notna().sum().sum()),
                     "retrieved_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")})
    return {"close": close, "adj": adj, "volume": volume, "dividends": dividends, "splits": splits,
            "status": pd.Series(status, name="status")}


def repair_double_adjustments(adj, close, dividends, splits, calendar_ticker, min_gap=0.02):
    """Undo spin-offs that Yahoo adjusts twice.

    Yahoo records some spin-offs both as a split factor (already built into Close) and as a dividend, and its
    adjusted close then applies both: the distribution is counted twice and the adjusted series shows a jump that
    never happened (Danaher, 5 July 2016: +61% instead of +4%). Rule, applied on every day on which a security has
    a split factor AND a dividend: if the adjusted-close return and the close return differ by more than `min_gap`
    and the close return is the one nearer to the market's return that day, the adjusted prices before that day
    are rescaled so that the day shows the close return. Days on which the adjusted return is the nearer one (a
    real split and a real distribution on the same day) are left alone.

    Returns (adjusted prices to use, table of every split-and-dividend day with what was done).
    """
    market = adj[calendar_ticker].dropna()
    r_market = market / market.shift(1) - 1.0
    both = (splits.reindex(index=adj.index, columns=adj.columns).fillna(0.0) > 0) & \
           (dividends.reindex(index=adj.index, columns=adj.columns).fillna(0.0) > 0)
    fixed, rows = adj.copy(), []
    for t in adj.columns[both.any().to_numpy()]:
        for day in both.index[both[t].to_numpy()]:
            a, c = adj[t].loc[:day].dropna(), close[t].loc[:day].dropna()
            if len(a) < 2 or len(c) < 2 or a.index[-1] != day or c.index[-1] != day or day not in r_market.index:
                continue
            r_adj, r_close, r_mkt = a.iloc[-1] / a.iloc[-2] - 1.0, c.iloc[-1] / c.iloc[-2] - 1.0, r_market[day]
            use_close = bool(abs(r_adj - r_close) > min_gap and abs(r_close - r_mkt) < abs(r_adj - r_mkt))
            if use_close:
                fixed.loc[fixed.index < day, t] *= (1.0 + r_adj) / (1.0 + r_close)
            decision = "close return used" if use_close else "adjusted return kept"
            if min(abs(r_adj - r_mkt), abs(r_close - r_mkt)) > 0.20:
                decision += " (unresolved: neither return is near the market)"
            rows.append({"security": t, "day": day.date(), "split_factor": float(splits.at[day, t]),
                         "dividend": float(dividends.at[day, t]), "adj_close_return": r_adj, "close_return": r_close,
                         "market_return": r_mkt, "decision": decision})
    table = pd.DataFrame(rows, columns=["security", "day", "split_factor", "dividend", "adj_close_return", "close_return",
                                        "market_return", "decision"])
    return fixed, table


def later_split_factor(splits, date):
    """Product of all split factors after `date`, per security. Yahoo restates Close for later splits, so the price
    that was actually quoted on `date` is Close times this factor."""
    after = splits.loc[splits.index > pd.Timestamp(date)]
    return after.where(after > 0, 1.0).prod()


def is_share_split(factor, max_denominator=4):
    """True for a real stock split (2-for-1, 3-for-2, 1-for-8 ...). Yahoo also lists spin-offs as "split factors",
    with odd ratios such as 1.319; those change the price but not the number of shares."""
    f = float(factor)
    for den in range(1, max_denominator + 1):
        up = round(f * den)                               # forward split: f = up / den
        if up >= 1 and abs(f - up / den) <= 2e-4 * f:
            return True
        down = round(den / f)                             # reverse split: f = den / down (Yahoo rounds to 4 decimals)
        if down >= 1 and abs(f - den / down) <= 6e-5:
            return True
    return False


def _yahoo_share_history(symbol, start, end_exclusive):
    """One symbol's reported shares outstanding (yfinance get_shares_full); None if Yahoo has none."""
    s = yf.Ticker(symbol).get_shares_full(start=start, end=end_exclusive)
    if s is None or len(s) == 0:
        return None
    s = pd.Series(np.asarray(s, dtype=float), index=pd.DatetimeIndex(s.index).tz_localize(None).normalize())
    s = s[s > 0]
    return s[~s.index.duplicated(keep="last")].sort_index() if len(s) else None


def yahoo_shares(symbols, start, end_exclusive, workers=8, retries=3, pause=1.5, canary="AAPL"):
    """Reported shares outstanding through time for many symbols -> {"shares": {symbol: Series}, "status": Series}.

    Yahoo answers one symbol per request. A symbol without share data must not be confused with a failed request:
    the reference symbol `canary` is asked first and must return data, and a symbol that returns nothing or raises
    an error is asked again up to `retries` times before it is recorded as having no share counts.
    """
    from concurrent.futures import ThreadPoolExecutor

    def one(symbol):
        outcome = "no share counts on Yahoo"
        for attempt in range(retries + 1):
            try:
                s = _yahoo_share_history(symbol, start, end_exclusive)
                if s is not None:
                    return symbol, s, "ok"
                outcome = "no share counts on Yahoo"
            except Exception as exc:
                outcome = "request failed: " + type(exc).__name__
            time.sleep(pause * (attempt + 1))
        return symbol, None, outcome

    if one(canary)[1] is None:
        raise RuntimeError(f"Yahoo returned no share counts for {canary}: network or rate limit problem, not missing "
                           "data. Wait a few minutes and run the cell again.")
    todo = list(dict.fromkeys(symbols))
    shares, status = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for symbol, s, outcome in pool.map(one, todo):
            status[symbol] = outcome
            if s is not None:
                shares[symbol] = s
    failed = [t for t, o in status.items() if o.startswith("request failed")]
    if len(failed) > 0.05 * len(todo):
        raise RuntimeError(f"Yahoo share-count requests failed for {len(failed)} symbols (e.g. {failed[:5]}): network or "
                           "rate limit problem. Wait a few minutes and run the cell again.")
    first = min(s.index[0] for s in shares.values()); last = max(s.index[-1] for s in shares.values())
    DATA_LOG.append({"provider": "Yahoo Finance (yfinance " + yf.__version__ + ")",
                     "query": f"shares outstanding, {len(todo)} tickers", "route": "yfinance Ticker.get_shares_full",
                     "requested": f"{start} to {end_exclusive} (end exclusive)",
                     "returned": f"{first.date()} to {last.date()}", "rows": int(sum(len(s) for s in shares.values())),
                     "retrieved_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")})
    return {"shares": shares, "status": pd.Series(status, name="status")}


def splice_ticker_history(counts, history):
    """One share-count series per CURRENT Yahoo symbol (see TICKER_HISTORY).

    counts  : {symbol: Series of reported counts}, former symbols included
    history : {current symbol: [(symbol, day), ...]} in time order: the counts filed under `symbol` are the
              company's until `day` (exclusive); from the last `day` on, the counts under the current symbol are.
    Counts that a company took from a former symbol are removed from that symbol's own series, so that today's user
    of the ticker does not inherit them.
    Returns ({symbol: Series}, table with one row per change of ticker: the last count before it and the first
    count after it, which agree when nothing but the ticker changed).
    """
    out = {k: v for k, v in counts.items() if k not in history}
    rows, nothing = [], pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    for sym, hist in history.items():
        chain = [(s, pd.Timestamp(d)) for s, d in hist] + [(sym, None)]
        parts, lower = [], None
        for src, until in chain:
            seg = counts.get(src)
            seg = nothing if seg is None else seg
            if lower is not None:
                seg = seg[seg.index >= lower]
            if until is not None:
                seg = seg[seg.index < until]
            parts.append(seg)
            if src != sym and src in out and len(seg):      # these counts belong to `sym`, not to today's user of `src`
                out[src] = out[src].drop(seg.index)
            lower = until
        for k in range(len(chain) - 1):
            before, after = parts[k], parts[k + 1]
            rows.append({"company (Yahoo symbol)": sym, "counts filed under": chain[k][0], "until": chain[k][1].date(),
                         "last count before": float(before.iloc[-1]) if len(before) else np.nan,
                         "dated": before.index[-1].date() if len(before) else None,
                         "then under": chain[k + 1][0],
                         "first count after": float(after.iloc[0]) if len(after) else np.nan,
                         "dated ": after.index[0].date() if len(after) else None})
        joined = pd.concat([p for p in parts if len(p)]) if any(len(p) for p in parts) else nothing
        if len(joined):
            out[sym] = joined[~joined.index.duplicated(keep="last")].sort_index()
    table = pd.DataFrame(rows)
    if len(table):
        table["ratio"] = table["first count after"] / table["last count before"]
    return out, table


def clean_share_counts(counts, splits, window_days=120, span_days=730):
    """Yahoo's reported shares outstanding -> shares in today's split units, one Series per symbol.

    Each count is multiplied by the REAL stock-split factors that came after its date (is_share_split). Yahoo's Close
    is restated for those splits and also for spin-offs; a spin-off changes the price but not the number of shares,
    so spin-off factors are applied on the price side when market value is computed (price_only_factors).
    Near a real split Yahoo's counts are unreliable about the unit: some are already post-split before the split
    date, others still pre-split after it. A count within `window_days` of a real split is therefore read in
    whichever unit (as dated, times the factor, or divided by it) is closest to the stock's counts further away from
    any split (their median within `span_days`, before AND after it). This is the one place where a stock's later
    counts help to read an earlier one: they decide the unit only, the reported number is never changed.
    Returns ({symbol: Series}, number of counts whose unit was changed).
    """
    out, changed = {}, 0
    for sym, s in counts.items():
        if sym not in splits.columns:
            continue
        s = s[s > 0]
        s = s[~s.index.duplicated(keep="last")].sort_index()
        if not len(s):
            continue
        ev = splits[sym]
        ev = ev[ev > 0]
        real = ev[[is_share_split(f) for f in ev.to_numpy()]] if len(ev) else ev
        base = s.to_numpy(dtype=float)
        if len(real):
            suffix = np.append(np.cumprod(real.to_numpy(dtype=float)[::-1])[::-1], 1.0)   # product of the factors from j on
            base = base * suffix[np.searchsorted(real.index.values, s.index.values, side="right")]
            gap = np.abs((s.index.values[:, None] - real.index.values[None, :]) / np.timedelta64(1, "D"))
            near = gap.min(axis=1) <= window_days
            fixed = base.copy()
            for i in np.flatnonzero(near):
                calm = (~near) & (np.abs((s.index - s.index[i]).days) <= span_days)
                if not calm.any():
                    calm = ~near
                if not calm.any():
                    continue                              # no count away from a split: nothing to compare with
                level = np.median(base[calm])
                best, best_gap = base[i], abs(math.log(base[i] / level))
                for f in real[gap[i] <= window_days].to_numpy(dtype=float):
                    for candidate in (base[i] * f, base[i] / f):
                        g = abs(math.log(candidate / level))
                        if g < best_gap - 1e-9:
                            best, best_gap = candidate, g
                changed += int(best != base[i])
                fixed[i] = best
            base = fixed
        out[sym] = pd.Series(base, index=s.index)
    return out, changed


def price_only_factors(splits, sessions):
    """For each month-end session and symbol: the product of Yahoo's LATER "split factors" that are not real stock
    splits (spin-offs and similar events). Yahoo divides earlier Close prices by them although the number of shares
    did not change, so shares (in today's split units) x Close x this factor is the market value on that day."""
    arr = splits.to_numpy(dtype=float)
    g = np.ones_like(arr)
    for i, j in zip(*np.nonzero(arr > 0)):
        if not is_share_split(arr[i, j]):
            g[i, j] = arr[i, j]
    after = np.ones_like(g)
    after[:-1] = np.cumprod(g[::-1], axis=0)[::-1][1:]                # product of the factors AFTER each day
    out = pd.DataFrame(after, index=splits.index, columns=splits.columns).reindex(sessions.to_numpy())
    if out.isna().any().any():
        raise ValueError("a month-end session is missing from the table of split factors")
    out.index = sessions.index
    return out


def reporting_outage(counts, gap_days=180, majority=0.5):
    """Yahoo's general outage in reported share counts: the longest period during which more than `majority` of the
    symbols are inside a gap of more than `gap_days` between two of their own counts. Returns (first day, last day)
    or None if there is no such period."""
    marks, n = {}, 0
    for s in counts.values():
        if len(s) < 2:
            continue
        n += 1
        d = s.index.values
        for i in np.flatnonzero((d[1:] - d[:-1]) > np.timedelta64(int(gap_days), "D")):
            marks[d[i]] = marks.get(d[i], 0) + 1
            marks[d[i + 1]] = marks.get(d[i + 1], 0) - 1
    best, start, inside = None, None, 0
    for day in sorted(marks):
        inside += marks[day]
        if inside > majority * n and start is None:
            start = day
        elif inside <= majority * n and start is not None:
            if best is None or day - start > best[1] - best[0]:
                best = (start, day)
            start = None
    return None if best is None else (pd.Timestamp(best[0]), pd.Timestamp(best[1]))


def skip_before_outage(s, outage, gap_days=180):
    """Drop a count that is directly followed by a gap of more than `gap_days` of which more than `gap_days` lie in
    Yahoo's outage. Such a count cannot be trusted: where a stock split during the outage, the data show that most
    of these counts are already in post-split units or equal the first count after the outage."""
    if outage is None or len(s) < 2:
        return s
    d = s.index
    lo = np.maximum(d[:-1].values, np.datetime64(outage[0]))
    hi = np.minimum(d[1:].values, np.datetime64(outage[1]))
    long_gap = (d[1:].values - d[:-1].values) > np.timedelta64(int(gap_days), "D")
    drop = long_gap & ((hi - lo) > np.timedelta64(int(gap_days), "D"))
    return s[np.append(~drop, True)]


def confirmed_counts(s, tolerance=0.25):
    """Keep a count if it is within a factor of 1 + `tolerance` of the last kept count (with 0.25: at most 25% above
    or 20% below it), or if it agrees in that sense with the count before it: a change of level is believed once two
    consecutive counts show it. One-off wrong values, and share classes
    reported in turn, are thereby left out; a real change (a merger) takes effect with the second count after it.
    Each decision uses only the counts up to that date. Returns the kept counts."""
    if tolerance is None or not len(s):
        return s
    band = math.log1p(tolerance)
    keep, level, pending = [], None, None
    for i, c in enumerate(s.to_numpy(dtype=float)):
        if level is None or abs(math.log(c / level)) <= band or (pending is not None and abs(math.log(c / pending)) <= band):
            keep.append(i)
            level, pending = c, None
        else:
            pending = c
    return s.iloc[keep]


def month_end_shares(kept, sessions, columns, carry_back_days=120):
    """Share count known at each month-end: the latest kept count on or before it. Up to `carry_back_days` before a
    stock's first count, that first count is carried BACK and flagged; further back there is no share count.
    Returns (shares, carried_back, age_days): month x symbol tables; age_days is the age of the count used."""
    months = list(sessions.index)
    dates = sessions.to_numpy().astype("datetime64[ns]")
    reach = np.timedelta64(int(carry_back_days), "D")
    day = np.timedelta64(1, "D")
    shares, back, age = {}, {}, {}
    for sym in columns:
        s = kept.get(sym)
        col, flag, old = np.full(len(months), np.nan), np.zeros(len(months), dtype=bool), np.full(len(months), np.nan)
        if s is not None and len(s):
            idx, val = s.index.values.astype("datetime64[ns]"), s.to_numpy(dtype=float)
            hi = np.searchsorted(idx, dates, side="right")
            seen = hi > 0
            col[seen], old[seen] = val[hi[seen] - 1], (dates[seen] - idx[hi[seen] - 1]) / day
            early = ~seen & (idx[0] - dates <= reach)
            col[early], flag[early], old[early] = val[0], True, (dates[early] - idx[0]) / day
        shares[sym], back[sym], age[sym] = col, flag, old
    return (pd.DataFrame(shares, index=months), pd.DataFrame(back, index=months), pd.DataFrame(age, index=months))


def wiki_tables(revid):
    """All HTML tables of one pinned Wikipedia revision, through the MediaWiki API."""
    r = http_get(WIKI_API_URL, {"action": "parse", "oldid": int(revid), "prop": "text", "format": "json", "formatversion": 2},
                 headers={"User-Agent": USER_AGENT})       # Wikipedia asks API clients to identify themselves
    parsed = r.json()["parse"]
    tables = pd.read_html(io.StringIO(parsed["text"]))
    DATA_LOG.append({"provider": "Wikipedia (MediaWiki API)", "query": parsed["title"], "route": f"action=parse, oldid={revid}",
                     "requested": f"revision {revid}", "returned": f"{len(tables)} tables", "rows": int(len(tables[0])),
                     "retrieved_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")})
    return tables


def month_end_sessions(trading_days):
    """Last trading session of every month in a DatetimeIndex -> Series indexed by monthly Period.
    A final month whose data stop more than three days before the end of the month is dropped as incomplete."""
    days = pd.DatetimeIndex(trading_days).sort_values()
    s = pd.Series(days, index=days.to_period("M")).groupby(level=0).max()
    if len(s) and s.iloc[-1].day < s.iloc[-1].days_in_month - 3:
        s = s.iloc[:-1]                    # the data stop inside the last month: that day is not a month-end
    return s


def first_regular_trading_day(close, volume, window=60):
    """For each security, the first day from which Yahoo reports trading volume on every one of the next `window`
    days that have a price. For nearly all securities this is the first day of the data, or a few days later. For a
    few, Yahoo shows an earlier price history from a foreign line with little or no trading; it ends where regular
    trading begins. NaT if the security never trades regularly."""
    out = {}
    for sym in close.columns:
        c = close[sym].dropna()
        day = pd.NaT
        if len(c):
            v = (volume[sym].reindex(c.index).fillna(0.0) > 0).to_numpy(dtype=float)
            ahead = np.convolve(v[::-1], np.ones(window), mode="full")[:len(v)][::-1]      # days with volume among this day and the next window - 1
            ok = np.flatnonzero(ahead >= np.minimum(window, np.arange(len(v), 0, -1)) - 1e-9)
            day = c.index[ok[0]] if len(ok) else pd.NaT
        out[sym] = day
    return pd.Series(out, dtype="datetime64[ns]")


def build_monthly_panel(adj, close, volume, calendar_ticker):
    """Turn daily Yahoo data into the monthly tables the backtest uses.

    px        : adjusted price on the exact final scheduled session of each month. No forward fill, so a
                stale earlier price never counts as a month-end observation (used for eligibility).
    px_close  : Yahoo's Close (adjusted for splits, not for dividends) on the same sessions: the price that turns
                share counts into market capitalisation.
    px_signal : the same Close from the security's first regular trading day on (first_regular_trading_day): the
                prices the momentum signal compares. For a few symbols Yahoo shows a price history from before the
                US listing, taken from a foreign line that trades rarely or not at all; those prices are not the
                listed stock's and do not count.
    daily_close: the daily Close on the market's trading days from the first regular trading day on, for the
                volatility of daily price changes and the number of days traded.
    ret       : monthly simple total return used to value positions. Inside a security's life a position is
                valued at its last traded price; after the last quote ever, the return is NaN (handled as
                delisting proceeds by the accounting engine, never as zero).
    stale     : True where `ret` relied on a stale price (gap month or final partial month): logged, not hidden.
    last_month: month of the last quote for series that end before the data window does, else NaT.
    """
    calendar = adj[calendar_ticker].dropna().index            # the market's trading days
    sessions = month_end_sessions(calendar)
    px = adj.reindex(sessions.values); px.index = sessions.index
    px_close = close.reindex(sessions.values); px_close.index = sessions.index
    listed_from = first_regular_trading_day(close, volume)
    traded = close.where(close.index.values[:, None] >= listed_from.reindex(close.columns).values[None, :])
    px_signal = traded.reindex(sessions.values); px_signal.index = sessions.index
    first_date = adj.apply(lambda s: s.first_valid_index())
    last_date = adj.apply(lambda s: s.last_valid_index())
    val = adj.reindex(calendar).ffill().reindex(sessions.values); val.index = sessions.index
    ended = last_date < calendar[-1]                           # series stops before the data window ends
    for t in adj.columns[ended.values]:
        val.loc[val.index > pd.Period(last_date[t], freq="M"), t] = np.nan
    ret = val / val.shift(1) - 1.0
    stale = val.notna() & px.isna()
    last_month = pd.Series([pd.Period(d, freq="M") if e else pd.NaT for d, e in zip(last_date.values, ended.values)],
                           index=adj.columns)
    dollar_volume = (close * volume).reindex(calendar)
    adv = dollar_volume.groupby(calendar.to_period("M")).median()   # median daily dollar volume per month
    return {"sessions": sessions, "px": px, "px_close": px_close, "px_signal": px_signal, "ret": ret, "stale": stale,
            "first_date": first_date, "last_date": last_date, "last_month": last_month, "adv": adv,
            "daily_close": traded.reindex(calendar), "listed_from": listed_from}


def add_market_caps(panel, share_units, cfg, outage=None):
    """Add month-end share counts and market capitalisation to the panel (in place).

    share_units : {symbol: Series} from clean_share_counts; outage : from reporting_outage. The rules are applied in
    this order: counts directly before Yahoo's outage are left out (cfg.share_skip_before_outage), a change of level
    must be confirmed by a second count (cfg.share_confirm), the latest remaining count on or before each month-end
    is used, and a stock's first count is carried back by at most cfg.share_carry_back_days.
    Adds shares, shares_carried_back, shares_age_days and mcap = shares x Close x price-only factor.
    """
    kept = {}
    for sym, s in share_units.items():
        if cfg.share_skip_before_outage:
            s = skip_before_outage(s, outage, cfg.share_gap_days)
        kept[sym] = confirmed_counts(s, cfg.share_confirm)
    shares, back, age = month_end_shares(kept, panel["sessions"], list(panel["px_close"].columns), cfg.share_carry_back_days)
    panel["shares"], panel["shares_carried_back"], panel["shares_age_days"] = shares, back, age
    panel["mcap"] = shares * panel["px_close"] * panel["price_only_factor"]
    return panel


def yahoo_splits_after(symbols, after, canary="SPY"):
    """Split factors that Yahoo records after the end of the price window, up to today (dates x symbols).

    Yahoo restates every earlier Close for all later splits, including those after the sample. Share counts must
    be converted with the same factors, otherwise a company that split after the sample looks too small.
    """
    symbols = list(dict.fromkeys(symbols))
    tomorrow = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).strftime("%Y-%m-%d")
    if pd.Timestamp(after) > pd.Timestamp(tomorrow) - pd.Timedelta(days=7):
        return pd.DataFrame(columns=symbols, dtype=float)
    recent = yahoo_daily(symbols + [canary], str(pd.Timestamp(after).date()), tomorrow, canary=canary)
    return recent["splits"].reindex(columns=symbols).fillna(0.0)

def yahoo_market_data(symbols, cfg):
    """Daily prices (yahoo_daily) plus, under "later_splits", the split factors Yahoo records after the price
    window. Both are taken in one go, so that they describe the same state of Yahoo's data: every Close is restated
    for exactly the splits in the two tables."""
    out = yahoo_daily(symbols, cfg.data_start, cfg.data_end_exclusive)
    stocks = [c for c in out["close"].columns if c not in (cfg.benchmark, cfg.momentum_fund)]
    out["later_splits"] = yahoo_splits_after(stocks, cfg.data_end_exclusive)
    return out


# Restatements of past prices for which Yahoo lists no factor: (symbol, day) -> factor by which Yahoo divides the
# earlier Close prices. Found through Yahoo's own dividend history, which is restated in the same way.
UNLISTED_PRICE_FACTORS = {
    ("HWM", "2020-04-01"): 1.304,     # separation of Arconic Corp.: a dividend of $0.09 paid in 2016 appears as $0.069018
}


def all_split_factors(raw):
    """Yahoo's split factors inside the price window and after it, in one table (dates x symbols), completed by the
    price restatements for which Yahoo lists no factor (UNLISTED_PRICE_FACTORS)."""
    splits, later = raw["splits"], raw.get("later_splits")
    if later is not None and len(later):
        splits = pd.concat([splits, later.reindex(columns=splits.columns).fillna(0.0)]).sort_index()
    else:
        splits = splits.copy()
    for (sym, day), factor in UNLISTED_PRICE_FACTORS.items():
        day = pd.Timestamp(day)
        if sym in splits.columns and day in splits.index and splits.at[day, sym] == 0:
            splits.at[day, sym] = factor
    return splits


# [engine] exported to the repo by tools/export_engine.py - see the README
# (effective date, ticker in the change log) -> ticker under which the same security appears later in the tables
ADD_ALIASES = {
    ("2026-03-23", "SATS"): "ECHO",    # EchoStar changed its ticker
    ("2021-09-20", "CDAY"): "DAY",     # Ceridian -> Dayforce
    ("2018-06-20", "FLT"): "CPAY",     # FleetCor -> Corpay
    ("2017-06-19", "RE"): "EG",        # Everest Re -> Everest Group
    ("2016-04-08", "UA.C"): "UA",      # Under Armour class C, later ticker UA
    ("2015-09-18", "FOX"): "TFCF",     # 21st Century Fox class B, later ticker TFCF
    ("2014-05-01", "UA"): "UAA",       # Under Armour class A, later ticker UAA
    ("2014-04-03", "GOOGL"): "GOOG",   # the security added that day was the new class C (today GOOG)
    ("2013-12-23", "FB"): "META",      # Facebook -> Meta Platforms
    ("2013-11-13", "KORS"): "CPRI",    # Michael Kors -> Capri Holdings
    ("2012-12-21", "DLPH"): "APTV",    # Delphi Automotive -> Aptiv
    ("2011-02-25", "JOYG"): "JOY",     # Joy Global changed its ticker
    ("2010-11-17", "IR"): "TT",        # Ingersoll-Rand -> Trane Technologies
    ("2009-11-03", "PCLN"): "BKNG",    # Priceline -> Booking Holdings
}

# change-log ticker -> Yahoo symbol that carries this security's price history today (same listed security, renamed)
YAHOO_ALIASES = {
    "WLTW": "WTW",   # Willis Towers Watson, ticker change 2022 (stated in the change log)
    "DWDP": "DD",    # DowDuPont renamed DuPont de Nemours, 2019 (stated in the change log)
    "KFT": "MDLZ",   # Kraft Foods renamed Mondelez, 2012 (stated in the change log)
    "ARNC": "HWM",   # Arconic renamed Howmet Aerospace, 2020 (stated in the change log)
    "GPS": "GAP",    # Gap Inc. ticker change, 2024
    "FBHS": "FBIN",  # Fortune Brands Home & Security -> Fortune Brands Innovations, 2022
    "HFC": "DINO",   # HollyFrontier -> HF Sinclair, 2022
    "ADS": "BFH",    # Alliance Data Systems -> Bread Financial, 2022
    "WYN": "TNL",    # Wyndham Worldwide -> Wyndham Destinations -> Travel + Leisure
    "SAI": "LDOS",   # SAIC renamed Leidos, 2013
    "JDSU": "VIAV",  # JDS Uniphase renamed Viavi Solutions, 2015
    "FII": "FHI",    # Federated Investors -> Federated Hermes, 2020
    "BHI": "BKR",    # Baker Hughes Inc. -> Baker Hughes Co.; Yahoo carries the old history under BKR
    "CCE": "CCEP",   # Coca-Cola Enterprises -> Coca-Cola Europacific Partners
    "CSC": "DXC",    # Computer Sciences Corp. -> DXC Technology; Yahoo carries the old history under DXC
    "DPS": "KDP",    # Dr Pepper Snapple -> Keurig Dr Pepper; Yahoo carries the old history under KDP
}
# (change-log ticker, "start" or "end", that date of the membership spell) -> Yahoo symbol, where the ticker alone is
# ambiguous because two different companies used it
YAHOO_ALIASES_BY_SPELL = {
    ("Q", "start", "2017-08-29"): "IQV",   # QuintilesIMS traded as Q for three months before becoming IQV
    ("DOW", "end", "2017-09-01"): "DD",    # Dow Chemical until the DowDuPont merger: Yahoo keeps its history under DD
}

# the second share class of an issuer that is already in the index with its primary class
SECONDARY_SHARE_CLASSES = {"GOOG": "GOOGL", "FOX": "FOXA", "NWS": "NWSA", "DISCK": "DISCA", "UA": "UAA",
                           "CMCSK": "CMCSA", "TFCF": "TFCFA"}

# former members whose ticker Yahoo now assigns to a different security even though that series overlaps the
# membership period (found by comparing Yahoo's company name with the index member's name)
REUSED_TICKERS = {
    "EP": "El Paso Corp. (acquired 2012); Yahoo symbol now Empire Petroleum",
    "GR": "Goodrich Corp. (acquired 2012); Yahoo symbol now an unrelated fund series",
    "GENZ": "Genzyme (acquired 2011); Yahoo symbol now an exchange-traded fund",
    "KG": "King Pharmaceuticals (acquired 2010); Yahoo symbol now Kestrel Group",
    "CPWR": "Compuware (taken private 2014); Yahoo symbol now Ocean Thermal Energy",
    "DD": "E.I. du Pont de Nemours (merged into DowDuPont 2017); Yahoo's DD history before September 2017 is Dow Chemical's",
}

# index members that are still in the index but whose Yahoo price history BEFORE the day given is another company's:
# the member cannot be ranked before that day
FOREIGN_PRICES_BEFORE = {
    "JCI": "2016-09-06",     # Johnson Controls Inc. merged into Tyco International that day and Tyco took its name and ticker;
                             # Yahoo's JCI history before it is Tyco's (split factor 0.955 on that day; Tyco's dividends)
}

# Share counts. Yahoo files a reported share count under the ticker the company had AT THE TIME, while the price
# history moves to the current symbol. Under its current symbol a renamed company therefore has no counts before the
# change of ticker, or it has the counts of whoever used that ticker before. For each such company the table gives the
# earlier symbols in time order, each with the day from which the NEXT symbol's counts are the company's (the day of
# that symbol's first own count on Yahoo). Section 3.2 checks every entry against Yahoo's data: where nothing but the
# ticker changed, the last count under the old symbol and the first under the new one agree.
TICKER_HISTORY = {
    "META": [("FB", "2022-06-09")],                             # Facebook -> Meta Platforms
    "BNY":  [("BK", "2026-05-22")],                             # Bank of New York Mellon; BNY was a closed-end fund before
    "COR":  [("ABC", "2023-09-01")],                            # AmerisourceBergen -> Cencora; COR was CoreSite Realty before
    "GEN":  [("SYMC", "2019-11-11"), ("NLOK", "2022-11-09")],   # Symantec -> NortonLifeLock -> Gen Digital
    "DOC":  [("HCP", "2019-11-12"), ("PEAK", "2024-03-20")],    # HCP -> Healthpeak, which took Physicians Realty's ticker in 2024
    "WTW":  [("WLTW", "2022-01-11")],                           # Willis Towers Watson; WTW was Weight Watchers before
    "DD":   [("DOW", "2017-09-01"), ("DWDP", "2019-06-10")],    # Dow Chemical -> DowDuPont -> DuPont de Nemours
    "DINO": [("HFC", "2022-03-17")],                            # HollyFrontier -> HF Sinclair
    "MRSH": [("MMC", "2026-01-15")],                            # Marsh McLennan
    "SKYD": [("CBS", "2019-12-05"), ("VIAC", "2022-02-18"), ("PARA", "2025-08-08"), ("PSKY", "2026-10-06")],   # CBS -> ... -> Skydance
    "VMRK": [("EQR", "2026-08-25")],                            # Equity Residential -> Vivmark Residential
    "RVTY": [("PKI", "2023-05-18")],                            # PerkinElmer -> Revvity
    "ELV":  [("ANTM", "2022-06-29")],                           # Anthem -> Elevance Health
    "GAP":  [("GPS", "2024-08-22")],                            # Gap Inc.
    "BALL": [("BLL", "2022-05-10")],                            # Ball Corporation
    "BBWI": [("LB", "2021-08-04")],                             # L Brands -> Bath & Body Works
    "VTRS": [("MYL", "2020-11-17")],                            # Mylan -> Viatris
    "BFH":  [("ADS", "2022-04-05")],                            # Alliance Data Systems -> Bread Financial
    "LUMN": [("CTL", "2020-09-22")],                            # CenturyLink -> Lumen Technologies
    "RTX":  [("UTX", "2020-04-14")],                            # United Technologies -> Raytheon Technologies
    "TT":   [("IR", "2020-03-03")],                             # Ingersoll-Rand plc -> Trane Technologies
    "J":    [("JEC", "2019-12-16")],                            # Jacobs Engineering
    "TFC":  [("BBT", "2019-12-16")],                            # BB&T -> Truist Financial
    "BKR":  [("BHI", "2017-07-05"), ("BHGE", "2019-10-24")],    # Baker Hughes Inc. -> Baker Hughes, a GE company -> Baker Hughes Co.
    "GL":   [("TMK", "2019-08-16")],                            # Torchmark -> Globe Life
    "LHX":  [("HRS", "2019-07-13")],                            # Harris -> L3Harris
    "LIN":  [("PX", "2018-11-04")],                             # Praxair -> Linde plc
    "TNL":  [("WYN", "2018-06-01"), ("WYND", "2021-02-18")],    # Wyndham Worldwide -> Wyndham Destinations -> Travel + Leisure
    "APTV": [("DLPH", "2017-12-14")],                           # Delphi Automotive -> Aptiv; DLPH then went to Delphi Technologies
    "BKNG": [("PCLN", "2018-11-14")],                           # Priceline Group -> Booking Holdings
    "UAA":  [("UA", "2016-11-08")],                             # Under Armour class A traded as UA until December 2016
    "FBIN": [("FBHS", "2022-12-16")],                           # Fortune Brands Home & Security -> Fortune Brands Innovations
    "EG":   [("RE", "2023-07-12")],                             # Everest Re -> Everest Group
    "HWM":  [("ARNC", "2020-04-02")],                           # Arconic Inc. -> Howmet Aerospace; ARNC then went to Arconic Corp.
    "CPAY": [("FLT", "2024-03-27")],                            # FleetCor -> Corpay
    "IQV":  [("Q", "2018-11-14")],                              # QuintilesIMS -> IQVIA
    "FISV": [("FISV", "2023-06-13"), ("FI", "2025-11-11")],     # Fiserv traded as FI from June 2023 to November 2025
    # former symbols under which Yahoo has no counts at present: the company cannot be ranked before the date given
    "CPRI": [("KORS", "2019-01-07")],                           # Michael Kors -> Capri Holdings
    "CBRE": [("CBG", "2018-11-14")],                            # CBRE Group
    "JEF":  [("LUK", "2018-11-14")],                            # Leucadia National -> Jefferies Financial Group
    "TPR":  [("COH", "2018-11-14")],                            # Coach -> Tapestry
    "WELL": [("HCN", "2018-11-13")],                            # Welltower
    "KDP":  [("DPS", "2018-07-16")],                            # Dr Pepper Snapple -> Keurig Dr Pepper
    "CCEP": [("CCE", "2018-11-12")],                            # Coca-Cola Enterprises -> Coca-Cola Europacific Partners
    "DXC":  [("CSC", "2017-04-06")],                            # Computer Sciences Corp. -> DXC Technology
    "SPGI": [("MHFI", "2016-04-27")],                           # McGraw Hill Financial -> S&P Global
}


def clean_ticker(x):
    """Change-log tickers contain stray characters ('ALLE |'); keep letters, digits and the class dot."""
    return re.sub(r"[^A-Z0-9.]", "", x.upper()) if isinstance(x, str) else None


def build_spells(constituents, changes, cutoff="2009-06-01"):
    """Replay the change log backwards from today's constituents.

    Returns (spells, issues). `spells` has one row per continuous stay of a security in the index:
    ticker, name, start (NaT = already a member at `cutoff`), end (NaT = still a member), reasons.
    `issues` lists log entries that could not be matched; it should be empty.
    """
    cons = constituents.copy()
    cons.columns = [str(c).strip() for c in cons.columns]
    chg = changes.copy()
    chg.columns = ["date", "add_ticker", "add_name", "rem_ticker", "rem_name", "reason", "refs"][: chg.shape[1]]
    chg["date"] = pd.to_datetime(chg["date"], errors="coerce")
    if chg["date"].isna().any():
        raise ValueError("unparseable dates in the change log")
    chg["add_ticker"] = chg["add_ticker"].map(clean_ticker)
    chg["rem_ticker"] = chg["rem_ticker"].map(clean_ticker)
    chg = chg.sort_values("date", ascending=False, kind="stable").reset_index(drop=True)

    spells, open_spells, issues = [], {}, []
    for _, row in cons.iterrows():
        tk = clean_ticker(row["Symbol"])
        spells.append({"ticker": tk, "name": row["Security"], "start": pd.NaT, "end": pd.NaT,
                       "reason_in": "", "reason_out": "", "sector": row.get("GICS Sector", None)})
        open_spells.setdefault(tk, []).append(len(spells) - 1)
    for _, row in chg.iterrows():
        if row["date"] < pd.Timestamp(cutoff):
            break
        added = row["add_ticker"] if isinstance(row["add_ticker"], str) and row["add_ticker"] else None
        removed = row["rem_ticker"] if isinstance(row["rem_ticker"], str) and row["rem_ticker"] else None
        if added:                                       # undo an addition: the spell started on this date
            key = ADD_ALIASES.get((str(row["date"].date()), added), added)
            if open_spells.get(key):
                k = open_spells[key].pop()
                spells[k]["start"], spells[k]["reason_in"] = row["date"], str(row["reason"])
            else:
                issues.append({"date": row["date"].date(), "ticker": added, "problem": "addition without a matching member"})
        if removed:                                     # undo a removal: an earlier spell ended on this date
            spells.append({"ticker": removed, "name": row["rem_name"], "start": pd.NaT, "end": row["date"],
                           "reason_in": "", "reason_out": str(row["reason"]), "sector": None})
            open_spells.setdefault(removed, []).append(len(spells) - 1)
    out = pd.DataFrame(spells)
    out["start"] = pd.to_datetime(out["start"]); out["end"] = pd.to_datetime(out["end"])
    return out, pd.DataFrame(issues, columns=["date", "ticker", "problem"])


def yahoo_symbol(ticker, start=None, end=None):
    """Yahoo symbol for a membership spell (class shares use '-' on Yahoo: BRK.B -> BRK-B)."""
    for which, date in (("start", start), ("end", end)):
        if date is not None and pd.notna(date):
            key = (ticker, which, str(pd.Timestamp(date).date()))
            if key in YAHOO_ALIASES_BY_SPELL:
                return YAHOO_ALIASES_BY_SPELL[key]
    return YAHOO_ALIASES.get(ticker, ticker).replace(".", "-")


def members_on(spells, date):
    """Membership spells active at the close of `date` (changes effective on or before that day are included)."""
    date = pd.Timestamp(date)
    active = (spells["start"].isna() | (spells["start"] <= date)) & (spells["end"].isna() | (spells["end"] > date))
    return spells[active]


def map_spells_to_yahoo(spells, first_date, data_start):
    """Attach the Yahoo symbol to each spell and decide whether Yahoo's series may be used for it."""
    sp = spells.copy()
    sp["yahoo"] = [yahoo_symbol(t, s, e) for t, s, e in zip(sp["ticker"], sp["start"], sp["end"])]
    sp["yahoo_first"] = pd.to_datetime(sp["yahoo"].map(first_date))
    tolerance = pd.Timedelta(days=10)
    must_exist_by = sp["start"].fillna(pd.Timestamp(data_start)).clip(lower=pd.Timestamp(data_start)) + tolerance
    note = pd.Series("", index=sp.index, dtype="object")
    note[sp["ticker"].isin(list(SECONDARY_SHARE_CLASSES))] = "secondary share class"
    no_data = sp["yahoo_first"].isna() & (note == "")
    note[no_data] = "no Yahoo price history (delisted or unknown symbol)"
    late = sp["end"].notna() & sp["yahoo_first"].notna() & (sp["yahoo_first"] > must_exist_by) & (note == "")
    note[late] = "ticker reused: Yahoo series starts after the membership began"
    listed = sp["end"].notna() & sp["ticker"].isin(list(REUSED_TICKERS)) & (note == "")
    note[listed] = "ticker reused: Yahoo series belongs to another issuer"
    sp["block"] = note
    return sp


def former_symbols(stocks):
    """Former ticker symbols under which Yahoo files earlier share counts of the companies in `stocks`."""
    return sorted({s for sym in stocks for s, _ in TICKER_HISTORY.get(sym, [])} - set(stocks))


def universe_symbols(spells, cfg):
    """Yahoo symbols of every security that was an index member inside the backtest window, plus the two funds."""
    first_reference = (P(cfg.first_holding_month) - 1 - cfg.reference_lag).start_time
    relevant = spells[(spells["end"].isna() | (spells["end"] > first_reference)) &
                      (spells["start"].isna() | (spells["start"] < pd.Timestamp(cfg.data_end_exclusive)))]
    symbols = {yahoo_symbol(t, s, e) for t, s, e in zip(relevant["ticker"], relevant["start"], relevant["end"])}
    return sorted(symbols | {cfg.benchmark, cfg.momentum_fund})


def momentum_inputs(panel, month, cfg):
    """Momentum value and volatility for the reference date = last session of `month` (S&P methodology, Appendix A).

    value  : price change over cfg.lookback months ending cfg.skip month(s) before the reference date, measured on
             month-end closing prices; from cfg.fallback_lookback months if there is no price that far back
    vol    : standard deviation of the daily price changes over the same period
    days   : number of daily price changes in that period; months : 12 or 9, the period actually used
    Only prices of days on which the stock traded count (see build_monthly_panel).
    """
    close, sessions, daily = panel["px_signal"], panel["sessions"], panel["daily_close"]
    end, far, near = month - cfg.skip, month - cfg.skip - cfg.lookback, month - cfg.skip - cfg.fallback_lookback
    p_end, p_far, p_near = close.loc[end], close.loc[far], close.loc[near]
    full = p_far.notna() & p_end.notna()
    value = (p_end / p_far - 1.0).where(full, p_end / p_near - 1.0)
    r_far = daily.loc[sessions[far]:sessions[end]].pct_change(fill_method=None).iloc[1:]
    r_near = daily.loc[sessions[near]:sessions[end]].pct_change(fill_method=None).iloc[1:]
    vol = r_far.std(ddof=1).where(full, r_near.std(ddof=1))
    days = r_far.notna().sum().where(full, r_near.notna().sum())
    return pd.DataFrame({"value": value, "vol": vol, "days": days,
                         "months": np.where(full, cfg.lookback, cfg.fallback_lookback)})


def universe_at(month, spells_mapped, panel, cfg, inputs=None):
    """Classify every index member at the reference date = last session of `month` (a monthly Period).

    A security is eligible when it is an index member on the reference date, Yahoo carries its own history (not
    another company's under the same symbol), it has a price on that date, a momentum value (at least nine months of
    prices before the skipped month), at least cfg.min_trading_days daily price changes in the measurement period,
    and a share count. Everything except the question whether Yahoo still carries the company was known on the
    reference date.
    """
    px, sessions = panel["px"], panel["sessions"]
    mem = members_on(spells_mapped, sessions[month]).copy()
    inputs = momentum_inputs(panel, month, cfg) if inputs is None else inputs
    symbols = mem["yahoo"].to_numpy()

    def look(series):                                 # value of every member's symbol (NaN if there is none)
        return pd.Series(series.reindex(symbols).to_numpy(dtype=float), index=mem.index)

    has_col = mem["yahoo"].isin(list(px.columns))
    price, value, vol, days = look(px.loc[month]), look(inputs["value"]), look(inputs["vol"]), look(inputs["days"])
    cap = look(panel["mcap"].loc[month])
    status = mem["block"].copy()
    not_its_own = [t in FOREIGN_PRICES_BEFORE and sessions[month] < pd.Timestamp(FOREIGN_PRICES_BEFORE[t]) for t in mem["ticker"]]
    status[(status == "") & np.array(not_its_own, dtype=bool)] = "ticker reused: Yahoo series belongs to another issuer"
    status[(status == "") & ~has_col] = "no Yahoo price history (delisted or unknown symbol)"
    status[(status == "") & price.isna()] = "no valid price on the reference date"
    status[(status == "") & (value.isna() | ~(vol > 0))] = "listed too recently for the signal"
    status[(status == "") & (days < cfg.min_trading_days)] = "too few trading days in the measurement period"
    status[(status == "") & cap.isna()] = "no share count on Yahoo"
    status[status == ""] = "eligible"
    mem["status"] = status
    dup = mem[(mem["status"] == "eligible")].duplicated("yahoo", keep="first")
    mem.loc[dup[dup].index, "status"] = "duplicate price series"
    return mem


# [engine] exported to the repo by tools/export_engine.py - see the README
def assign_groups(score, n_groups):
    """Rank ascending by score (ties: by identifier) and cut into n equal-count groups, 1 = lowest.

    When the count is not divisible by n, the extra names go to the HIGHEST groups, so sizes differ by at most one.
    """
    s = score.dropna()
    table = pd.DataFrame({"score": s.to_numpy(dtype=float), "id": [str(i) for i in s.index]}, index=s.index)
    order = table.sort_values(["score", "id"], kind="mergesort").index
    base, extra = divmod(len(order), n_groups)
    sizes = [base + (1 if g > n_groups - extra else 0) for g in range(1, n_groups + 1)]
    labels = np.repeat(np.arange(1, n_groups + 1), sizes)
    return pd.Series(labels, index=order, dtype="float").reindex(score.index)


def momentum_score(value, vol, winsor=3.0, risk_adjust=True):
    """(risk-adjusted value, capped z-score, momentum score) for one cross-section (S&P methodology, Appendix B).

    z = (x - mean) / standard deviation across the stocks, capped at +/- winsor;
    score = 1 + z for z > 0 and 1 / (1 - z) for z < 0, so it is 1 at z = 0 and always positive.
    """
    x = (value / vol) if risk_adjust else value.astype(float)
    sd = x.std(ddof=1)
    z = ((x - x.mean()) / sd).clip(-winsor, winsor) if sd > 0 else x * 0.0
    score = pd.Series(np.where(z > 0, 1.0 + z, 1.0 / (1.0 - np.minimum(z, 0.0))), index=z.index)
    return x, z, score


def select_with_buffer(ranked, current, target, buffer):
    """Selection with the buffer rule of the S&P Momentum indices.

    ranked : identifiers, best first; current : identifiers held now; target : number of stocks to hold.
    1. The best (1 - buffer) x target stocks are selected. 2. Stocks held now that rank within the best
    (1 + buffer) x target are re-selected in rank order until the target is reached. 3. If places are left, the
    best stocks not yet selected fill them. Without holdings or with buffer = 0 this is simply the best `target`.
    """
    ranked = list(ranked)
    if not current or buffer <= 0:
        return ranked[:target]
    sure = int(math.floor(target * (1.0 - buffer) + 0.5))
    reach = int(math.floor(target * (1.0 + buffer) + 0.5))
    chosen = ranked[:sure]
    for name in ranked[sure:reach]:
        if len(chosen) >= target:
            break
        if name in current:
            chosen.append(name)
    taken = set(chosen)
    for name in ranked[sure:]:
        if len(chosen) >= target:
            break
        if name not in taken:
            chosen.append(name)
    return chosen


def capped_weights(raw, limit):
    """Weights proportional to `raw` that sum to 1 with weight_i <= limit_i. Weight above a limit is passed on to
    the other names in proportion to their raw weights, repeated until no limit is exceeded."""
    r, lim = np.asarray(raw, dtype=float), np.asarray(limit, dtype=float)
    if lim.sum() < 1.0 - 1e-12:
        raise ValueError("the weight limits add up to less than 100%")
    w = r / r.sum()
    fixed = np.zeros(len(r), dtype=bool)
    for _ in range(len(r) + 1):
        over = (w > lim + 1e-15) & ~fixed
        if not over.any():
            break
        fixed |= over
        w[fixed] = lim[fixed]
        free = ~fixed
        if not free.any():
            break
        w[free] = r[free] / r[free].sum() * (1.0 - lim[fixed].sum())
    return pd.Series(w, index=raw.index) if isinstance(raw, pd.Series) else w


def weight_limits(cap_weight, cfg):
    """Limit for each stock's weight: the lower of cfg.max_weight and cfg.max_cap_multiple x its market-cap weight.
    If these limits left no room for 100%, the multiple is raised by 1 at a time until they do.
    Returns (limits, multiple used)."""
    cw = np.asarray(cap_weight, dtype=float)
    if not np.isfinite(cw).all() or (cw <= 0).any():
        raise ValueError("market-cap weights must be positive numbers")
    if cfg.max_weight * len(cw) < 1.0 - 1e-12:
        raise ValueError(f"{len(cw)} stocks cannot be held with a limit of {cfg.max_weight:.0%} each")
    multiple = float(cfg.max_cap_multiple)
    while True:
        limit = np.minimum(cfg.max_weight, multiple * cw)
        if limit.sum() >= 1.0 - 1e-12:
            return limit, multiple
        multiple += 1.0


def strategy_weights(table, names, cfg, weighting=None, capped=True):
    """Weights at the reference date for the stocks `names` of one formation table.

    weighting : "cap_score" = market capitalisation x momentum score, "cap" = market capitalisation, "equal" = 1/N
                (default cfg.weighting)
    capped    : each weight is at most cfg.max_weight and at most cfg.max_cap_multiple x the stock's market-cap
                weight (see weight_limits). cfg.cap_reference says in what: "holdings" (among `names`, the base
                case) or "universe" (among all eligible stocks).
    Returns (weights, multiple used).
    """
    s = table.loc[list(names)]
    weighting = weighting or cfg.weighting
    raw = {"cap_score": s["mcap"] * s["score"], "cap": s["mcap"], "equal": pd.Series(1.0, index=s.index)}[weighting]
    if not capped or weighting == "equal":
        return raw / raw.sum(), np.nan
    base = s["mcap"] / s["mcap"].sum() if cfg.cap_reference == "holdings" else s["uw"]
    limit, multiple = weight_limits(base, cfg)
    return capped_weights(raw, pd.Series(limit, index=s.index)), multiple


def formation_table(month, spells_mapped, panel, cfg):
    """Everything known for a rebalance traded at the close of `month`; reference date = end of month - reference_lag.

    Returns (eligible, everyone). `eligible` is indexed by Yahoo symbol and holds, as of the reference date: momentum
    value, volatility, risk-adjusted value (ram), capped z-score, momentum score, market capitalisation (mcap),
    weight in the eligible universe (uw), rank (1 = best) and group (cfg.n_groups = best scores); plus `drift`, the
    price change from the reference date to the trade date, and `tradable`, whether the stock is still an index
    member with a price on the trade date. `everyone` lists all index members at the reference date with the reason
    for each exclusion.
    """
    ref = month - cfg.reference_lag
    inputs = momentum_inputs(panel, ref, cfg)
    everyone = universe_at(ref, spells_mapped, panel, cfg, inputs)
    e = everyone[everyone["status"] == "eligible"].set_index("yahoo")[["ticker", "name"]].copy()
    e = e.join(inputs.reindex(e.index))
    e["ram"], e["z"], e["score"] = momentum_score(e["value"], e["vol"], cfg.winsor_z, cfg.risk_adjust)
    e["mcap"] = panel["mcap"].loc[ref].reindex(e.index)
    e["carried_back"] = panel["shares_carried_back"].loc[ref].reindex(e.index).astype(bool)
    e["uw"] = e["mcap"] / e["mcap"].sum()
    order = e.assign(_id=[str(i) for i in e.index]).sort_values(["z", "ram", "_id"], ascending=[False, False, True],
                                                                 kind="mergesort").index
    e["rank"] = pd.Series(np.arange(1, len(order) + 1), index=order)
    e["group"] = assign_groups(-e["rank"], cfg.n_groups)
    close = panel["px_close"]
    e["drift"] = close.loc[month].reindex(e.index) / close.loc[ref].reindex(e.index)
    still = members_on(spells_mapped, panel["sessions"][month])
    still = set(still.loc[still["block"] == "", "yahoo"])
    e["tradable"] = (e.index.isin(list(still)) & panel["px"].loc[month].reindex(e.index).notna().to_numpy()
                     & e["drift"].notna().to_numpy())
    return e, everyone


def build_targets(forms, months, cfg, select="top", weighting=None, capped=True):
    """Target weights at the close of each rebalance month in `months`, in order (the buffer rule looks back).

    select : "top" = the best 1/cfg.n_groups of the eligible stocks, plus cfg.target_shift (or cfg.target_count
             stocks, if set), with the buffer rule (the strategy);
             "all" = every eligible stock; an integer g = the stocks of group g, without buffer
    Weights are set at the reference date (strategy_weights), drift with prices to the trade date, and are rescaled
    over the stocks that can still be bought. Returns (targets, log) with one log row per rebalance.
    """
    targets, rows, current = {}, [], set()
    for m in months:
        f = forms[m]
        if isinstance(select, str) and select == "top":
            target = cfg.target_count or int(math.floor(len(f) / cfg.n_groups + 0.5)) + cfg.target_shift
            names = select_with_buffer(list(f.sort_values("rank").index), current, target, cfg.buffer)
        elif isinstance(select, str) and select == "all":
            names = list(f.index)
        else:
            names = list(f.index[f["group"] == select])
        if not names:
            targets[m], current = pd.Series(dtype=float), set()
            continue
        w_ref, multiple = strategy_weights(f, names, cfg, weighting, capped)
        ok = f.loc[names, "tradable"].to_numpy()
        w = (w_ref * f.loc[names, "drift"])[ok]
        w = w / w.sum()
        targets[m] = w
        back = f.loc[w.index, "carried_back"].to_numpy()
        rows.append({"trade month": m, "eligible": len(f), "selected": len(names), "bought": len(w),
                     "already held": len(current & set(names)), "new": len(set(names) - current),
                     "at the weight limit": int((w_ref >= cfg.max_weight - 1e-9).sum()) if capped else 0,
                     "multiple used": multiple, "largest weight": float(w.max()),
                     "ten largest weights": float(w.nlargest(10).sum()),
                     "selected, share of universe value": float(f.loc[names, "uw"].sum()),
                     "weight on carried-back share counts": float(w[back].sum())})
        current = set(w.index)                          # the buffer rule favours what is actually held
    log = pd.DataFrame(rows).set_index("trade month") if rows else pd.DataFrame()
    return targets, log


def schedule(start, end, rebalance_months):
    """Formation months: `start` itself plus every later month in `rebalance_months`, up to the month before `end`."""
    return [m for m in pd.period_range(start, end - 1, freq="M") if m == start or m.month in rebalance_months]


def solve_rebalance(nav, holdings, weights, cost_rate):
    """Self-financing rebalance. Solves V* = V - c * sum|w_i V* - H_i| and returns (V*, trades in dollars, cost)."""
    v = nav
    for _ in range(200):
        v_new = nav - cost_rate * np.abs(weights * v - holdings).sum()
        converged = abs(v_new - v) <= 1e-15 * max(abs(nav), 1.0)
        v = v_new
        if converged:
            break
    trades = weights * v - holdings
    return v, trades, cost_rate * np.abs(trades).sum()


def simulate(ret, rf, targets, cost_rate, start, end, last_month=None):
    """Chronological dollar accounting of a rebalanced, otherwise buy-and-hold portfolio.

    ret        : monthly simple returns, index = monthly Periods, columns = securities
    rf         : monthly risk-free return, earned by idle cash
    targets    : {formation month: Series of target weights}; a trade happens at the close of each key
    start, end : formation month of the first trade and last holding month. NAV is 1 at `start` BEFORE costs
    last_month : security -> month of its last quote when its data ends early (delisting), else NaT
    Returns nav (pre-trade value at each month-end), ret (net monthly return; the cost of a trade at the close
    of month m lowers the return of month m+1), a table of rebalances, monthly holdings statistics and events.
    """
    cols = list(ret.columns)
    pos = {c: i for i, c in enumerate(cols)}
    months = pd.period_range(start, end, freq="M")
    R = ret.reindex(months).to_numpy(dtype=float)
    RF = rf.reindex(months).to_numpy(dtype=float)
    dead_from = np.full(len(cols), np.iinfo(np.int64).max, dtype=np.int64)   # first step at which a position is cash
    if last_month is not None:
        for c, lm in last_month.dropna().items():
            if c in pos:
                dead_from[pos[c]] = max(int((lm - months[0]).n) + 1, 0)
    H = np.zeros(len(cols))
    cash = 1.0
    nav = np.empty(len(months))
    monthly, rebalances, events = [], [], []
    for k, m in enumerate(months):
        if k > 0:
            gone = (H > 0) & (dead_from <= k)             # last quote was in an earlier month: proceeds are cash
            if gone.any():
                for i in np.flatnonzero(gone):
                    events.append({"month": m, "security": cols[i], "event": "delisting proceeds moved to cash",
                                   "value": H[i]})
                cash += H[gone].sum()
                H[gone] = 0.0
            held = H > 0
            if np.isnan(R[k][held]).any():
                bad = [cols[i] for i in np.flatnonzero(held & np.isnan(R[k]))]
                raise ValueError(f"unexplained missing return for held position(s) {bad} in {m}")
            if cash > 0 and np.isnan(RF[k]):
                raise ValueError(f"no risk-free rate for {m}")
            H[held] *= 1.0 + R[k][held]
            cash *= 1.0 + (RF[k] if cash > 0 else 0.0)
        V = H.sum() + cash
        nav[k] = V
        sec_total = H.sum()
        w_sec = H[H > 0] / sec_total if sec_total > 0 else np.array([])
        monthly.append({"month": m, "positions": int((H > 0).sum()), "max_weight": (H.max() / V) if V > 0 else np.nan,
                        "effective_holdings": 1.0 / np.square(w_sec).sum() if len(w_sec) else 0.0,
                        "cash_weight": cash / V if V > 0 else np.nan})
        if m in targets and k < len(months) - 1:
            w = np.zeros(len(cols))
            tgt = targets[m]
            if len(tgt):
                w[[pos[c] for c in tgt.index]] = tgt.to_numpy(dtype=float)
            v_net, trades, cost = solve_rebalance(V, H, w, cost_rate)
            buys, sells = trades[trades > 0].sum(), -trades[trades < 0].sum()
            one_way = 0.5 * (np.abs(w - H / V).sum() + abs((1.0 - w.sum()) - cash / V))
            rebalances.append({"month": m, "holdings": int((w > 0).sum()), "nav_before": V, "cost": cost / V,
                               "traded_notional": (buys + sells) / V, "one_way_turnover": one_way,
                               "bought": buys / V, "sold": sells / V, "cash_before": cash / V,
                               "orders": int((np.abs(trades) > 1e-12 * V).sum())})
            H = w * v_net
            cash = v_net - H.sum()
            if abs(cash) < 1e-12:                         # fully invested: remove floating-point dust
                cash = 0.0
    nav = pd.Series(nav, index=months, name="nav")
    out = {"nav": nav, "ret": (nav / nav.shift(1) - 1.0).iloc[1:].rename("ret"),
           "rebalances": pd.DataFrame(rebalances).set_index("month") if rebalances else pd.DataFrame(),
           "monthly": pd.DataFrame(monthly).set_index("month"), "events": events}
    return out


def run_portfolio(panel, rf, targets, start, end, cost_rate):
    """Net run at `cost_rate` plus a separately simulated zero-cost (gross) run of the same target weights."""
    net = simulate(panel["ret"], rf, targets, cost_rate, start, end, panel["last_month"])
    gross = simulate(panel["ret"], rf, targets, 0.0, start, end, panel["last_month"])
    net["ret_gross"], net["nav_gross"], net["targets"] = gross["ret"], gross["nav"], targets
    return net


# [engine] exported to the repo by tools/export_engine.py - see the README
def hac_lags(n):
    """Newey-West rule of thumb for the number of lags."""
    return int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


def market_model(r, bench, rf):
    """OLS of excess strategy return on excess benchmark return with HAC (Newey-West) standard errors.

    Alpha is reported per month and annualised (x12); beta is not annualised.
    """
    y = (r - rf).dropna()
    x = (bench - rf).reindex(y.index)
    lags = hac_lags(len(y))
    fit = sm.OLS(y.to_numpy(dtype=float), sm.add_constant(x.to_numpy(dtype=float))).fit(
        cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": True}, use_t=True)
    ci = np.asarray(fit.conf_int(0.05))
    return {"alpha_monthly": fit.params[0], "alpha": 12.0 * fit.params[0], "beta": fit.params[1],
            "alpha_se": 12.0 * fit.bse[0], "alpha_t": fit.tvalues[0], "alpha_p": fit.pvalues[0],
            "alpha_ci_low": 12.0 * ci[0, 0], "alpha_ci_high": 12.0 * ci[0, 1],
            "beta_se": fit.bse[1], "beta_t_vs_1": (fit.params[1] - 1.0) / fit.bse[1],
            "beta_ci_low": ci[1, 0], "beta_ci_high": ci[1, 1],
            "r_squared": fit.rsquared, "n": int(fit.nobs), "hac_lags": lags,
            "resid_vol": math.sqrt(12.0) * float(np.std(fit.resid, ddof=2)), "resid": pd.Series(fit.resid, index=y.index)}


def drawdown_series(nav):
    """Percentage below the running peak. Pass a NAV series that includes its starting value."""
    return nav / nav.cummax() - 1.0


def performance_stats(r, rf, bench=None, is_benchmark=False):
    """All reported performance measures for one monthly return series (see the table of definitions)."""
    r = r.dropna()
    rf = rf.reindex(r.index)
    n = len(r)
    ex = r - rf
    nav = pd.concat([pd.Series([1.0]), (1.0 + r).cumprod()], ignore_index=True)
    sd_ex = ex.std(ddof=1)
    downside = math.sqrt(float(np.mean(np.minimum(ex.to_numpy(), 0.0) ** 2)))
    out = {"months": n,
           "ann_return": 12.0 * r.mean(),
           "ann_vol": math.sqrt(12.0) * r.std(ddof=1),
           "sharpe": math.sqrt(12.0) * ex.mean() / sd_ex if sd_ex > 0 else np.nan,
           "cagr": nav.iloc[-1] ** (12.0 / n) - 1.0,
           "max_drawdown": drawdown_series(nav).min(),
           "sortino": math.sqrt(12.0) * ex.mean() / downside if downside > 0 else np.nan,
           "worst_month": r.min(), "best_month": r.max(),
           "profit_factor": r[r > 0].sum() / abs(r[r < 0].sum()) if (r < 0).any() else np.nan,
           "alpha": np.nan, "beta": np.nan, "info_ratio": np.nan, "tracking_error": np.nan,
           "active_return": np.nan, "appraisal_ratio": np.nan, "alpha_t": np.nan, "alpha_p": np.nan,
           "r_squared": np.nan, "share_months_ahead": np.nan}
    if is_benchmark:                       # by construction; ratios against itself are undefined, not zero
        out.update({"alpha": 0.0, "beta": 1.0, "active_return": 0.0, "tracking_error": 0.0, "r_squared": 1.0})
    elif bench is not None:
        b = bench.reindex(r.index)
        active = r - b
        te = math.sqrt(12.0) * active.std(ddof=1)
        mm = market_model(r, b, rf)
        out.update({"alpha": mm["alpha"], "beta": mm["beta"], "alpha_t": mm["alpha_t"], "alpha_p": mm["alpha_p"],
                    "r_squared": mm["r_squared"], "active_return": 12.0 * active.mean(), "tracking_error": te,
                    "info_ratio": 12.0 * active.mean() / te if te > 0 else np.nan,
                    "appraisal_ratio": mm["alpha"] / mm["resid_vol"] if mm["resid_vol"] > 0 else np.nan,
                    "share_months_ahead": float((active > 0).mean())})
    return out


def turnover_summary(run):
    """Recurring (post-launch) trading statistics per year, plus the initial investment shown separately.

    Per-year figures = average per scheduled rebalance x number of scheduled rebalances per year. (The first purchase
    is not a rebalance, so dividing the sample's total by its length would misstate them.)
    """
    reb = run["rebalances"]
    later = reb.iloc[1:]
    gaps = [(b - a).n for a, b in zip(reb.index[:-1], reb.index[1:])]
    per_year = 12.0 / float(np.median(gaps)) if gaps else 0.0
    mean = lambda column: float(later[column].mean()) if len(later) else 0.0
    return {"rebalances_per_year": per_year,
            "one_way_turnover_pa": per_year * mean("one_way_turnover"),
            "traded_notional_pa": per_year * mean("traded_notional"),
            "cost_pa": per_year * mean("cost"),
            "orders_pa": per_year * mean("orders"),
            "initial_cost": reb["cost"].iloc[0], "initial_one_way_turnover": reb["one_way_turnover"].iloc[0],
            "avg_holdings": reb["holdings"].mean(),
            "avg_effective_holdings": run["monthly"]["effective_holdings"].iloc[1:].mean(),
            "max_weight": run["monthly"]["max_weight"].iloc[1:].max(),
            "max_cash_weight": run["monthly"]["cash_weight"].iloc[1:].max()}


# [engine] exported to the repo by tools/export_engine.py - see the README
def build_formations(panel, spells_mapped, cfg):
    """Formation tables for every month a trade could happen in (monthly, so every rebalancing calendar is covered)."""
    first = P(cfg.first_holding_month) - 1
    last = P(cfg.last_holding_month) - 1
    forms, members = {}, {}
    for m in pd.period_range(first, last, freq="M"):
        forms[m], members[m] = formation_table(m, spells_mapped, panel, cfg)
    return forms, members


def assemble_data(cfg, yield_pct, constituents, changes, raw, share_counts):
    """Turn the raw downloads into the data bundle used by every calculation. `raw` is the output of
    yahoo_market_data, `share_counts` the reported counts by symbol (former symbols included)."""
    spells_raw, issues = build_spells(constituents, changes, cutoff=cfg.data_start)
    adj, repairs = repair_double_adjustments(raw["adj"], raw["close"], raw["dividends"], raw["splits"], cfg.benchmark)
    panel = build_monthly_panel(adj, raw["close"], raw["volume"], cfg.benchmark)
    splits = all_split_factors(raw)
    panel["price_only_factor"] = price_only_factors(splits, panel["sessions"])
    company_counts, handovers = splice_ticker_history(share_counts, TICKER_HISTORY)
    share_units, units_changed = clean_share_counts(company_counts, splits)
    plain_units, _ = clean_share_counts(share_counts, splits)                  # as filed under today's symbols
    outage = reporting_outage(share_units, cfg.share_gap_days)
    add_market_caps(panel, share_units if cfg.share_ticker_history else plain_units, cfg, outage)
    spells = map_spells_to_yahoo(spells_raw, panel["first_date"], cfg.data_start)
    forms, members = build_formations(panel, spells, cfg)
    return {"cfg": cfg, "panel": panel, "spells": spells, "rf": monthly_rf(yield_pct, panel["sessions"]),
            "forms": forms, "members": members, "status": raw["status"], "replay_issues": issues,
            "adjustment_repairs": repairs, "share_units": share_units, "share_units_todays_symbol": plain_units,
            "share_outage": outage,
            "share_units_changed": units_changed, "ticker_handovers": handovers,
            "splits": splits, "constituents": constituents, "changes": changes, "yield": yield_pct}


def prepare_data(cfg, fred_key=None, fetch=None):
    """Download everything and build the data bundle. `fetch(name, builder)` lets the caller add caching."""
    fetch = fetch or (lambda name, builder: builder())
    fred_end = str(P(cfg.last_holding_month).end_time.date())
    yield_pct = fetch(f"fred_{cfg.rf_series}", lambda: fred_series(cfg.rf_series, "1981-09-01", fred_end, fred_key))
    constituents = fetch(f"wiki_{cfg.wiki_constituents_revid}", lambda: wiki_tables(cfg.wiki_constituents_revid)[0])
    changes = fetch(f"wiki_{cfg.wiki_changes_revid}", lambda: max(wiki_tables(cfg.wiki_changes_revid), key=len))
    symbols = universe_symbols(build_spells(constituents, changes, cutoff=cfg.data_start)[0], cfg)
    raw = fetch(f"yahoo_prices_{cfg.data_start}_{cfg.data_end_exclusive}_{len(symbols)}", lambda: yahoo_market_data(symbols, cfg))
    stocks = sorted(c for c in raw["close"].columns if c not in (cfg.benchmark, cfg.momentum_fund))
    ask = stocks + former_symbols(stocks)
    counts = fetch(f"yahoo_shares_{cfg.data_start}_{cfg.data_end_exclusive}_{len(ask)}",
                   lambda: yahoo_shares(ask, cfg.data_start, cfg.data_end_exclusive))
    return assemble_data(cfg, yield_pct, constituents, changes, raw, counts["shares"])


def reconfigure(data, cfg):
    """Same downloads, different settings of the signal, the groups or the share counts: rebuild market values and
    formation tables. (Costs, calendar, buffer, weighting and limits need no rebuild; run_backtest reads them.)"""
    out = dict(data)
    out["cfg"] = cfg
    units = data["share_units"] if cfg.share_ticker_history else data["share_units_todays_symbol"]
    out["panel"] = add_market_caps(dict(data["panel"]), units, cfg, data["share_outage"])
    out["forms"], out["members"] = build_formations(out["panel"], data["spells"], cfg)
    return out


def run_backtest(data, cfg=None):
    """Simulate the strategy, the score-group portfolios and the benchmarks for one configuration.

    cfg : Config; calendar, costs, buffer, weighting and weight limits are read from it. Settings that change the
          formation tables (signal, number of groups, share counts) must match `data`: use reconfigure first.
    Returns a dict with net/gross monthly returns, NAVs, drawdowns, metrics, trading statistics, the selection log
    of the strategy, the individual runs (targets, rebalances, monthly holdings statistics, events) and warnings.
    Series: "Strategy", the groups (Q1..Q5 for quintiles; highest number = best scores), "Universe" (all eligible
    stocks by market value), cfg.benchmark and cfg.momentum_fund.
    """
    cfg = cfg or data["cfg"]
    n = cfg.n_groups
    panel, rf, forms = data["panel"], data["rf"], data["forms"]
    start = P(cfg.first_holding_month) - 1
    end = P(cfg.last_holding_month)
    months = schedule(start, end, cfg.rebalance_months)
    prefix = {5: "Q", 10: "D"}.get(n, "G")           # quintiles Q1-Q5, deciles D1-D10, otherwise G1-Gn
    targets = {}
    targets["Strategy"], selection = build_targets(forms, months, cfg, "top")
    for g in range(1, n + 1):
        targets[f"{prefix}{g}"], _ = build_targets(forms, months, cfg, g)
    targets["Universe"], _ = build_targets(forms, months, cfg, "all", weighting="cap", capped=False)
    for fund in (cfg.benchmark, cfg.momentum_fund):
        targets[fund] = {start: pd.Series({fund: 1.0})}
    runs = {k: run_portfolio(panel, rf, t, start, end, cfg.cost_rate) for k, t in targets.items()}
    net = pd.DataFrame({k: r["ret"] for k, r in runs.items()})
    gross = pd.DataFrame({k: r["ret_gross"] for k, r in runs.items()})
    nav = pd.DataFrame({k: r["nav"] for k, r in runs.items()})
    rf_s = rf.reindex(net.index)
    bench = net[cfg.benchmark]
    metrics = pd.DataFrame({k: performance_stats(net[k], rf_s, bench, is_benchmark=(k == cfg.benchmark)) for k in net}).T
    metrics_gross = pd.DataFrame({k: performance_stats(gross[k], rf_s, gross[cfg.benchmark],
                                                       is_benchmark=(k == cfg.benchmark)) for k in gross}).T
    trading = pd.DataFrame({k: turnover_summary(r) for k, r in runs.items()}).T
    warn = []
    sizes = pd.Series({m: len(forms[m]) for m in months})
    if sizes.min() < cfg.gate_min_names:
        warn.append(f"eligible universe falls to {int(sizes.min())} names (gate: {cfg.gate_min_names})")
    if rf_s.isna().any():
        warn.append(f"no current risk-free rate for {int(rf_s.isna().sum())} month(s): excess-return measures skip them")
    events = [e for r in runs.values() for e in r["events"]]
    if events:
        warn.append(f"{len(events)} delisting event(s) among held positions were settled in cash")
    return {"cfg": cfg, "start": start, "end": end, "formation_months": months, "strategy": "Strategy", "groups": n,
            "group_names": [f"{prefix}{g}" for g in range(1, n + 1)], "selection": selection,
            "runs": runs, "returns": net, "returns_gross": gross, "nav": nav, "rf": rf_s,
            "drawdowns": nav.apply(drawdown_series), "metrics": metrics, "metrics_gross": metrics_gross,
            "trading": trading, "universe_size": sizes, "warnings": warn}


# [engine] exported to the repo by tools/export_engine.py - see the README
def mean_test(x, scale=12.0):
    """Mean of a monthly series with a simple and a HAC (Newey-West) t-statistic; mean and interval scaled by `scale`."""
    x = pd.Series(x).dropna()
    n = len(x)
    lags = hac_lags(n)
    fit = sm.OLS(x.to_numpy(dtype=float), np.ones((n, 1))).fit(cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": True},
                                                               use_t=True)
    ci = np.asarray(fit.conf_int(0.05))[0]
    sd = x.std(ddof=1)
    return {"mean": scale * x.mean(), "vol": math.sqrt(scale) * sd, "t_simple": x.mean() / (sd / math.sqrt(n)) if sd > 0 else np.nan,
            "t_hac": fit.tvalues[0], "p_hac": fit.pvalues[0], "ci_low": scale * ci[0], "ci_high": scale * ci[1],
            "share_positive": float((x > 0).mean()), "n": n, "hac_lags": lags}


def forward_returns(ret, month, horizon, names):
    """Compounded total return of each name over the `horizon` months after formation `month`.

    A name whose quotes end inside the window keeps its last value for the rest of the window (delisting proceeds
    held without interest), the same convention as in the portfolio accounting.
    """
    window = ret.loc[month + 1: month + horizon, list(names)]
    return (1.0 + window).prod(skipna=True) - 1.0


def cross_sectional_tests(forms, ret, months, horizon=1, score="ram"):
    """For each formation month: slope of the forward return on the standardised score (default: the risk-adjusted
    momentum value), and the Spearman rank correlation between score and forward return. One row per month, to be
    averaged over time (Fama-MacBeth)."""
    rows = []
    for m in months:
        f = forms[m]
        fwd = forward_returns(ret, m, horizon, f.index)
        z = (f[score] - f[score].mean()) / f[score].std(ddof=1)
        ok = z.notna() & fwd.notna()
        fit = sm.OLS(fwd[ok].to_numpy(dtype=float), sm.add_constant(z[ok].to_numpy(dtype=float))).fit()
        rows.append({"formation": m, "stocks": int(ok.sum()), "intercept": fit.params[0], "slope": fit.params[1],
                     "rank_ic": f.loc[ok, score].corr(fwd[ok], method="spearman")})
    return pd.DataFrame(rows).set_index("formation")


# [engine] exported to the repo by tools/export_engine.py - see the README
def break_even_cost(data, cfg, versus, grid=(0.0, 0.0005, 0.001, 0.0025, 0.005, 0.01, 0.02, 0.05)):
    """Cost rate at which the strategy's annualised net return advantage over `versus` becomes zero.

    versus : "Universe" (all eligible stocks by market value, same calendar) or a fund symbol bought once and held.
    The same cost rate is applied to the strategy and to the comparison portfolio, using the full accounting engine.
    Nothing is extrapolated: if the strategy already trails at zero cost, or never crosses inside the grid, that is
    what is reported.
    """
    start = P(cfg.first_holding_month) - 1
    end = P(cfg.last_holding_month)
    months = schedule(start, end, cfg.rebalance_months)
    panel, rf, forms = data["panel"], data["rf"], data["forms"]
    strat_targets, _ = build_targets(forms, months, cfg, "top")
    if versus == "Universe":
        other_targets, _ = build_targets(forms, months, cfg, "all", weighting="cap", capped=False)
    else:
        other_targets = {start: pd.Series({versus: 1.0})}

    def advantage(c):
        a = simulate(panel["ret"], rf, strat_targets, c, start, end, panel["last_month"])["ret"]
        b = simulate(panel["ret"], rf, other_targets, c, start, end, panel["last_month"])["ret"]
        return 12.0 * (a - b).mean()

    values = [advantage(c) for c in grid]
    table = pd.Series(values, index=grid, name=f"advantage over {versus}")
    signs = np.sign(values)
    crossings = [i for i in range(len(grid) - 1) if signs[i] > 0 and signs[i + 1] <= 0]
    upward = [i for i in range(len(grid) - 1) if signs[i] <= 0 and signs[i + 1] > 0]
    if values[0] <= 0:
        status = "no positive break-even cost: the strategy already trails before any trading cost"
        if upward:
            status += " (it moves ahead only at higher cost rates, where the comparison portfolio's own costs weigh more)"
        return {"versus": versus, "break_even": np.nan, "table": table, "status": status}
    if not crossings:
        return {"versus": versus, "break_even": np.nan, "table": table,
                "status": f"no crossing up to {grid[-1] * 1e4:.0f} bp: the strategy stays ahead over the whole tested range"}
    lo, hi = grid[crossings[0]], grid[crossings[0] + 1]
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if advantage(mid) > 0 else (lo, mid)
    note = "" if len(crossings) + len(upward) == 1 else " (more than one sign change in the grid; the first is reported)"
    return {"versus": versus, "break_even": 0.5 * (lo + hi), "table": table, "status": "break-even found" + note}


def transition_analysis(forms, members, months, n_groups=5):
    """Migration between score groups from one rebalance date to the next.

    Rows: group at date t. Columns: group at the next date, or one of two exits: the stock left the index, or it is
    still a member but no longer eligible. Nothing is restricted to survivors. Also returns the entries (stocks
    that were not eligible at t), the share of the top group retained, and the lengths of stays in the top group.
    """
    col = "group"
    groups = list(range(1, n_groups + 1))
    exits = ["left the index", "member but not eligible"]
    counts = pd.DataFrame(0.0, index=groups, columns=groups + exits)
    entries = pd.Series(0.0, index=groups)
    retention = {}
    for a, b in zip(months[:-1], months[1:]):
        fa, fb = forms[a], forms[b]
        still_member = set(members[b]["yahoo"])
        nxt = fb[col].reindex(fa.index)
        for g in groups:
            names = fa.index[fa[col] == g]
            dest = nxt.reindex(names)
            for h in groups:
                counts.loc[g, h] += float((dest == h).sum())
            gone = names[dest.isna().to_numpy()]
            in_index = sum(1 for t in gone if t in still_member)
            counts.loc[g, "member but not eligible"] += in_index
            counts.loc[g, "left the index"] += len(gone) - in_index
        new = fb.index.difference(fa.index)
        for h in groups:
            entries[h] += float((fb.loc[new, col] == h).sum())
        top_a, top_b = set(fa.index[fa[col] == n_groups]), set(fb.index[fb[col] == n_groups])
        retention[b] = len(top_a & top_b) / len(top_a) if top_a else np.nan
    probs = counts.div(counts.sum(axis=1), axis=0)
    # consecutive rebalance dates in the top group; a stay touching the first or last date is censored
    stays = []
    everyone = sorted(set().union(*[set(forms[m].index) for m in months]))
    in_top = pd.DataFrame({m: forms[m][col].reindex(everyone).eq(n_groups) for m in months})
    for name, row in in_top.iterrows():
        run_len, start_i = 0, None
        vals = row.to_numpy()
        for i, flag in enumerate(vals):
            if flag and run_len == 0:
                start_i = i
            run_len = run_len + 1 if flag else 0
            if run_len and (i == len(vals) - 1 or not vals[i + 1]):
                stays.append({"security": name, "periods": run_len, "censored": start_i == 0 or i == len(vals) - 1})
                run_len = 0
    return {"counts": counts, "probabilities": probs, "entries": entries, "retention": pd.Series(retention),
            "stays": pd.DataFrame(stays)}


def rolling_stats(r, bench, rf, short=12, long=36):
    """Trailing-window statistics; every value uses only the months up to and including its own date."""
    ex, bex = r - rf, bench - rf
    comp = lambda x, w: (1.0 + x).rolling(w).apply(np.prod, raw=True) - 1.0
    out = pd.DataFrame(index=r.index)
    out["return_12m"], out["bench_12m"] = comp(r, short), comp(bench, short)
    out["relative_12m"] = out["return_12m"] - out["bench_12m"]                       # difference of compounded returns
    ann = lambda x: (1.0 + comp(x, long)) ** (12.0 / long) - 1.0
    out["relative_36m_pa"] = ann(r) - ann(bench)                                     # difference of annualised returns
    out["sharpe_36m"] = math.sqrt(12.0) * ex.rolling(long).mean() / ex.rolling(long).std(ddof=1)
    out["bench_sharpe_36m"] = math.sqrt(12.0) * bex.rolling(long).mean() / bex.rolling(long).std(ddof=1)
    beta = ex.rolling(long).cov(bex) / bex.rolling(long).var()
    out["beta_36m"] = beta
    out["alpha_36m_pa"] = 12.0 * (ex.rolling(long).mean() - beta * bex.rolling(long).mean())
    return out


def block_bootstrap(frame, statistics, reps, block, seed):
    """Circular block bootstrap of synchronised monthly rows (all series are resampled with the same months).

    statistics : {name: function of a 2-D numpy array with the columns of `frame`}
    Returns the point estimate, a percentile 95% interval and the share of resamples below zero for each statistic.
    """
    rng = np.random.default_rng(seed)
    values = frame.to_numpy(dtype=float)
    n = len(values)
    n_blocks = int(math.ceil(n / block))
    offsets = np.arange(block)
    draws = {k: np.empty(reps) for k in statistics}
    for b in range(reps):
        starts = rng.integers(0, n, size=n_blocks)
        idx = ((starts[:, None] + offsets[None, :]) % n).ravel()[:n]
        sample = values[idx]
        for k, fn in statistics.items():
            draws[k][b] = fn(sample)
    rows = {k: {"estimate": fn(values), "ci_low": float(np.percentile(draws[k], 2.5)),
                "ci_high": float(np.percentile(draws[k], 97.5)), "share_below_zero": float(np.mean(draws[k] < 0))}
            for k, fn in statistics.items()}
    return pd.DataFrame(rows).T


def random_pools(forms, months, sizes):
    """What a random draw needs at each rebalance: the eligible stocks, their market values, drift, whether they can
    still be bought, and the number of stocks to draw (sizes[m])."""
    return {m: (forms[m].index.to_numpy(), forms[m]["mcap"].to_numpy(dtype=float), forms[m]["drift"].to_numpy(dtype=float),
                forms[m]["tradable"].to_numpy(dtype=bool), int(sizes[m])) for m in months}


def random_targets(pools, cfg, rng):
    """Target weights of one random portfolio: at each rebalance the given number of stocks is drawn without
    replacement from the eligible stocks, weighted by market value under the strategy's weight limits and drifted to
    the trade date; stocks that can no longer be bought are dropped."""
    targets = {}
    for m, (names, cap, drift, ok, size) in pools.items():
        pick = rng.choice(len(names), size=size, replace=False)
        c = cap[pick]
        w = capped_weights(c, weight_limits(c / c.sum(), cfg)[0]) * drift[pick]
        w = np.where(ok[pick], w, 0.0)
        targets[m] = pd.Series(w[w > 0] / w.sum(), index=names[pick][w > 0])
    return targets


def random_portfolio_baseline(data, bt, n_sims, seed):
    """The strategy's rules (dates, number of holdings, weight limits, drift) with stocks drawn at random from the
    eligible universe and weighted by market value, instead of chosen and tilted by momentum score. Shows what luck
    alone produces under these rules. Returns are BEFORE costs and are compared with the strategy's return before
    costs: a random portfolio replaces far more of its holdings at each rebalance than the strategy does, so after
    costs the strategy would look better for a reason that has nothing to do with the score."""
    rng = np.random.default_rng(seed)
    panel, rf, cfg = data["panel"], data["rf"], bt["cfg"]
    pools = random_pools(data["forms"], bt["formation_months"], bt["selection"]["selected"])
    rf_s = bt["rf"]
    out = np.empty((n_sims, 3))
    for s in range(n_sims):
        r = simulate(panel["ret"], rf, random_targets(pools, cfg, rng), 0.0, bt["start"], bt["end"], panel["last_month"])["ret"]
        ex = r - rf_s
        out[s] = (12.0 * r.mean(), math.sqrt(12.0) * ex.mean() / ex.std(ddof=1), float((1.0 + r).prod()))
    return pd.DataFrame(out, columns=["ann_return", "sharpe", "final_value"])


# [engine] exported to the repo by tools/export_engine.py - see the README
YAHOO_TO_GICS = {"Technology": "Information Technology", "Financial Services": "Financials", "Healthcare": "Health Care",
                 "Consumer Cyclical": "Consumer Discretionary", "Consumer Defensive": "Consumer Staples",
                 "Basic Materials": "Materials", "Communication Services": "Communication Services", "Energy": "Energy",
                 "Industrials": "Industrials", "Real Estate": "Real Estate", "Utilities": "Utilities"}


def yahoo_sectors(symbols, workers=4, retries=2):
    """Today's Yahoo sector label per symbol, translated to GICS sector names. Best effort: a symbol whose profile
    cannot be read is left out and shows up as 'Unknown' in the tables instead of stopping the run."""
    from concurrent.futures import ThreadPoolExecutor

    def one(symbol):
        for attempt in range(retries + 1):
            try:
                return symbol, YAHOO_TO_GICS.get(yf.Ticker(symbol).info.get("sector"))
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        return symbol, None

    with ThreadPoolExecutor(workers) as pool:
        found = {k: v for k, v in pool.map(one, list(symbols)) if v}
    DATA_LOG.append({"provider": "Yahoo Finance (yfinance " + yf.__version__ + ")", "query": f"sector of {len(symbols)} symbols",
                     "route": "yfinance.Ticker.info", "requested": "current classification", "returned": f"{len(found)} labels",
                     "rows": len(found), "retrieved_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")})
    return found


def sector_weights(targets, sector_of):
    """Portfolio weight per sector at each formation date. Names without a label are reported as 'Unknown'."""
    rows = {m: w.groupby([sector_of.get(t, "Unknown") for t in w.index]).sum() for m, w in targets.items() if len(w)}
    return pd.DataFrame(rows).T.fillna(0.0).sort_index()


def retail_example(weights, panel, month, capital, cost_rate, split_factor=None):
    """What buying one set of target weights on one trade date looks like for a given amount of capital.

    split_factor : per security, the product of all split factors after the trade date (see later_split_factor).
                   Yahoo restates past closing prices for later splits; multiplying by this factor gives the share
                   price that was actually quoted on the trade date.
    """
    names = list(weights.index)
    w = weights.to_numpy(dtype=float)
    v_net, trades, cost = solve_rebalance(float(capital), np.zeros(len(w)), w, cost_rate)
    price = panel["px_close"].loc[month, names]
    if split_factor is not None:
        price = price * split_factor.reindex(names).fillna(1.0)
    position = pd.Series(w * v_net, index=names)
    whole_shares = np.floor(position / price)
    adv = panel["adv"].loc[month, names]
    return {"holdings": len(names), "largest position": float(position.max()), "median position": float(position.median()),
            "smallest position": float(position.min()), "ten largest positions, share of capital": float(np.sort(w)[-10:].sum()),
            "initial cost": cost, "median share price": float(price.median()), "highest share price": float(price.max()),
            "positions smaller than one share": int((price > position).sum()),
            "uninvested with whole shares only": float(v_net - (whole_shares * price).sum()),
            "median daily dollar volume": float(adv.median()), "lowest daily dollar volume": float(adv.min())}


# [engine] exported to the repo by tools/export_engine.py - see the README
def transition_matrix(states):
    """2x2 matrix of observed month-to-month transition frequencies; state 0 = expansion, 1 = recession."""
    s = np.asarray(states, dtype=int)
    counts = np.zeros((2, 2))
    np.add.at(counts, (s[:-1], s[1:]), 1.0)
    return counts / counts.sum(axis=1, keepdims=True)


def long_run_recession_share(tm):
    """Stationary probability of the recession state of a two-state Markov chain."""
    return tm[0, 1] / (tm[0, 1] + tm[1, 0])


def simulate_states(tm, n_paths, n_steps, rng, markov=True):
    """Simulated state paths. markov=True: next state depends on the current one (recessions clump).
    markov=False: every month is an independent draw with the same long-run recession share (the coin flip)."""
    share = long_run_recession_share(tm)
    s = np.empty((n_paths, n_steps), dtype=np.int8)
    s[:, 0] = rng.random(n_paths) < share
    for t in range(1, n_steps):
        p_recession = tm[s[:, t - 1], 1] if markov else share
        s[:, t] = rng.random(n_paths) < p_recession
    return s


def recession_spells(states):
    """Lengths of the runs of consecutive recession months in a 0/1 sequence."""
    s = np.asarray(states, dtype=int)
    edges = np.diff(np.concatenate([[0], s, [0]]))
    return np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)


def simulate_wealth(states, market_pools, alpha_m, beta, residuals, rf_m, start_value, rng):
    """Wealth paths for the benchmark and the strategy given simulated states.

    market_pools : {0: array, 1: array} of historical monthly market excess returns in each state
    strategy return = rf + alpha + beta * market excess return + resampled regression residual
    """
    market = np.empty(states.shape)
    for state in (0, 1):
        mask = states == state
        market[mask] = rng.choice(market_pools[state], size=int(mask.sum()), replace=True)
    eps = rng.choice(residuals, size=states.shape, replace=True)
    r_bench = rf_m + market
    r_strat = rf_m + alpha_m + beta * market + eps
    return {"benchmark": start_value * np.cumprod(1.0 + r_bench, axis=1),
            "strategy": start_value * np.cumprod(1.0 + r_strat, axis=1)}


def path_statistics(wealth, start_value):
    """Summary of simulated wealth paths (one row per path, one column per month)."""
    w = np.concatenate([np.full((wealth.shape[0], 1), float(start_value)), wealth], axis=1)
    worst = (w / np.maximum.accumulate(w, axis=1) - 1.0).min(axis=1)
    final = w[:, -1]
    years = wealth.shape[1] / 12.0
    out = {"mean final value": final.mean(), "median final value": np.median(final),
           "5th percentile": np.percentile(final, 5), "25th percentile": np.percentile(final, 25),
           "75th percentile": np.percentile(final, 75), "95th percentile": np.percentile(final, 95),
           "median growth rate p.a.": (np.median(final) / start_value) ** (1.0 / years) - 1.0,
           "probability of a loss at the horizon": float((final < start_value).mean()),
           "median worst drawdown": float(np.median(worst)),
           "probability of a drawdown worse than 30%": float((worst <= -0.30).mean()),
           "probability of a drawdown worse than 50%": float((worst <= -0.50).mean())}
    for y in (1, 3):
        if wealth.shape[1] >= 12 * y:
            out[f"probability of a loss after {y} year{'s' if y > 1 else ''}"] = float((w[:, 12 * y] < start_value).mean())
    return out
