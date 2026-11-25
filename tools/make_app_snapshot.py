"""Write the data snapshot the tracker app starts from (folder app_data/).

    python tools/make_app_snapshot.py

Downloads the data through the engine, as the notebook does (a download made by the notebook on the same day is
reused), keeps the part a backtest reads, and checks that a backtest on the snapshot gives the same monthly returns as
a backtest on the full data. The snapshot holds monthly returns, momentum scores and index weights of S&P 500 stocks
derived from Yahoo Finance data; daily prices and share counts are not stored.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantile_alpha.app_data import compact_bundle, download_data, load_bundle, save_bundle   # noqa: E402
from quantile_alpha.engine import CFG, run_backtest                                              # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "app_data"), help="folder to write (default: app_data)")
    args = ap.parse_args()

    data, retrieved = download_data(CFG)
    full = run_backtest(data, CFG)
    save_bundle(compact_bundle(data), args.out, retrieved_utc=retrieved,
                note="Written by tools/make_app_snapshot.py from the engine's data bundle.")
    bundle, meta = load_bundle(args.out)
    small = run_backtest(bundle, CFG)
    gap = float((small["returns"] - full["returns"]).abs().max().max())
    if not gap < 1e-10:
        raise SystemExit(f"The snapshot does not reproduce the full data: largest difference in a monthly return {gap:.2e}")
    meta["largest_difference_to_full_data"] = gap            # recorded with the snapshot
    (Path(args.out) / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in Path(args.out).iterdir()) / 1e6
    s = meta["base_case"]["Strategy"]
    print(f"snapshot written to {args.out} ({size:.1f} MB), data retrieved {retrieved} UTC")
    print(f"same monthly returns as the full data (largest difference {gap:.1e})")
    print(f"base case: {s['ann_return']:.2%} a year, volatility {s['ann_vol']:.2%}, Sharpe {s['sharpe']:.2f}")


if __name__ == "__main__":
    main()
