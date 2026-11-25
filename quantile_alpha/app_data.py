"""Data for the tracker app.

The app runs the notebook's engine (quantile_alpha.engine.run_backtest). A backtest reads three things from the
engine's data bundle: the monthly returns, the formation tables (score, market value, rank and tradability of every
eligible stock at every month-end) and the risk-free rate. This module

* downloads the data through the engine, exactly as the notebook does (`download_data`),
* keeps the part a backtest reads and drops the rest: daily prices and share counts (`compact_bundle`),
* stores that part as Parquet files and loads it again (`save_bundle`, `load_bundle`).

Nothing here calculates a result; every number shown by the app comes out of quantile_alpha.engine. This file is
written by hand and is not exported from the notebook.
"""
import datetime as dt
import hashlib
import json
import os
from dataclasses import asdict, fields
from pathlib import Path

import pandas as pd

from . import engine
from .engine import CFG, Config, P, get_fred_api_key, prepare_data, run_backtest

FORM_COLUMNS = ["ticker", "name", "score", "mcap", "uw", "rank", "group", "drift", "tradable", "carried_back"]
SUMMARY_FIELDS = ["ann_return", "ann_vol", "sharpe", "alpha", "beta", "info_ratio", "max_drawdown"]
FILES = ("returns.parquet", "forms.parquet", "monthly.parquet", "meta.json")


def engine_fingerprint():
    """Short hash of engine.py, stored with a snapshot so that the app can tell when the engine has changed since."""
    return hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()[:16]


def download_data(cfg=CFG, cache_dir=None, stamp=None, say=print):
    """Everything the engine needs, through the same APIs as the notebook (FRED, Wikipedia, Yahoo Finance).

    Downloads are kept in `cache_dir` under the notebook's file names, so a download made by the notebook on the same
    day (UTC) is reused and vice versa. Returns (data bundle, earliest retrieval time of the downloads used).
    """
    cache_dir = Path(cache_dir or os.environ.get("QA_CACHE_DIR") or Path.home() / ".cache" / "quantile_alpha")
    stamp = stamp or os.environ.get("QA_CACHE_STAMP") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    cache_dir.mkdir(parents=True, exist_ok=True)
    used = []

    def fetch(name, builder):
        path = cache_dir / f"{name}_{stamp}.pkl"
        if path.exists():
            try:
                obj, log = pd.read_pickle(path)
                used.extend(log)
                say(f"{name}: reused the download of {log[0]['retrieved_utc'] if log else 'earlier'} UTC")
                return obj
            except Exception:                 # unreadable (written by another pandas version): download again
                pass
        say(f"{name}: downloading")
        n_before = len(engine.DATA_LOG)
        obj = builder()
        log = engine.DATA_LOG[n_before:]
        pd.to_pickle((obj, log), path)
        used.extend(log)
        return obj

    data = prepare_data(cfg, get_fred_api_key(), fetch=fetch)
    times = [str(r["retrieved_utc"]) for r in used if "retrieved_utc" in r]
    return data, (min(times) if times else None)


def compact_bundle(data):
    """The part of the engine's data bundle that run_backtest reads.

    Market values are stored as shares of the eligible universe (column `uw`): the engine uses only their proportions,
    so weights and returns are the same. With this bundle the calendar, the costs, the buffer, the weighting, the
    weight limits and the number of holdings can be changed; settings of the momentum score cannot (they need the
    daily prices, see engine.reconfigure).
    """
    cfg = data["cfg"]
    months = pd.period_range(P(cfg.first_holding_month) - 1, P(cfg.last_holding_month), freq="M")
    forms = {}
    for m, table in data["forms"].items():
        f = table[FORM_COLUMNS].copy()
        f["mcap"] = f["uw"]
        forms[m] = f
    symbols = sorted(set().union(*[set(f.index) for f in forms.values()]) | {cfg.benchmark, cfg.momentum_fund})
    panel = data["panel"]
    return {"cfg": cfg,
            "panel": {"ret": panel["ret"].reindex(index=months, columns=symbols),
                      "last_month": panel["last_month"].reindex(symbols),
                      "sessions": panel["sessions"].reindex(months)},
            "rf": data["rf"].reindex(months), "forms": forms}


def base_case_summary(bt):
    """The headline measures of a backtest, used to check a stored snapshot against the engine."""
    m = bt["metrics"]
    cfg = bt["cfg"]
    value = lambda x: None if pd.isna(x) else float(x)            # the benchmark has no information ratio against itself
    return {key: {field: value(m.loc[key, field]) for field in SUMMARY_FIELDS} for key in ("Strategy", cfg.benchmark)}


def save_bundle(bundle, folder, retrieved_utc=None, note=""):
    """Write the compact bundle to `folder` as three Parquet files and a JSON file with its provenance."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    panel, cfg = bundle["panel"], bundle["cfg"]
    ret = panel["ret"].copy()
    ret.index = ret.index.astype(str)
    ret.to_parquet(folder / "returns.parquet", compression="zstd")
    forms = pd.concat({str(m): f for m, f in bundle["forms"].items()}, names=["month", "symbol"]).reset_index()
    forms.to_parquet(folder / "forms.parquet", compression="zstd", index=False)
    monthly = pd.DataFrame({"rf": bundle["rf"], "session": panel["sessions"]})
    monthly.index = monthly.index.astype(str)
    monthly.to_parquet(folder / "monthly.parquet", compression="zstd")
    last = panel["last_month"].dropna()
    meta = {"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "data_retrieved_utc": retrieved_utc, "note": note, "engine": engine_fingerprint(),
            "config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(cfg).items()},
            "last_month": {str(k): str(v) for k, v in last.items()},
            "base_case": base_case_summary(run_backtest(bundle, cfg)),
            "sources": "Yahoo Finance (prices and share counts, via yfinance), FRED (DGS3MO), "
                       "Wikipedia (S&P 500 membership changes, CC BY-SA 4.0)"}
    (folder / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def has_bundle(folder):
    return all((Path(folder) / name).exists() for name in FILES)


def load_bundle(folder):
    """Read a bundle written by save_bundle. Returns (bundle, meta)."""
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    cfg = Config(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in meta["config"].items() if k in known})
    ret = pd.read_parquet(folder / "returns.parquet")
    ret.index = pd.PeriodIndex(ret.index, freq="M")
    monthly = pd.read_parquet(folder / "monthly.parquet")
    monthly.index = pd.PeriodIndex(monthly.index, freq="M")
    long = pd.read_parquet(folder / "forms.parquet")
    forms = {P(month): table.drop(columns="month").set_index("symbol").rename_axis(None)
             for month, table in long.groupby("month", sort=True)}
    last = pd.Series(pd.NaT, index=ret.columns, dtype="period[M]")
    for symbol, month in meta["last_month"].items():
        last[symbol] = P(month)
    bundle = {"cfg": cfg, "panel": {"ret": ret, "last_month": last, "sessions": monthly["session"]},
              "rf": monthly["rf"], "forms": forms}
    return bundle, meta
