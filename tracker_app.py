"""Quantile Alpha: investment tracker.

    streamlit run tracker_app.py

The app reruns the backtest of the notebook with the notebook's own engine (quantile_alpha/engine.py, exported from
Financial_Modeling_Quantile_Alpha.ipynb) every time an assumption is changed. It calculates no performance figure
itself: returns, weights, costs and all measures come from engine.run_backtest and engine.performance_stats.

Data: the app starts from the snapshot in app_data/ when that folder exists (see tools/make_app_snapshot.py). Without
it, the data are retrieved from Yahoo Finance, FRED and Wikipedia through the engine, as in the notebook.
"""
import html
import os
from dataclasses import replace
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quantile_alpha import app_data
from quantile_alpha.engine import CFG, drawdown_series, performance_stats, run_backtest

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("QA_APP_DATA", ROOT / "app_data"))
REPOSITORY = "https://github.com/benediktproebstl/quantile-alpha"
PROSPECTUS = REPOSITORY + "/blob/main/investor_prospectus.pdf"

INK, GREY, LIGHT, TILE, RULE, GREEN, ORANGE = "#000000", "#71717A", "#A1A1AA", "#F5F5F7", "#E4E4E7", "#00C805", "#F16034"
MINUS = "−"

STRATEGY = "Strategy"
NAME = {"Strategy": "Quantile Alpha", "SPY": "S&P 500 (SPY)", "Universe": "Cap-weighted universe", "SPMO": "Momentum fund (SPMO)"}
BENCHMARK_NOTE = {"SPY": "the S&P 500 index fund a retail investor would hold instead",
                  "Universe": "every index member that can be ranked, by market value, with the same calendar and costs",
                  "SPMO": "a real fund that tracks the S&P 500 Momentum index"}
WEIGHTING = {"cap_score": "Size × score", "cap": "Size only", "equal": "Equal"}
CALENDAR = {"Twice a year": (3, 9), "Quarterly": (3, 6, 9, 12), "Yearly": (3,)}
NO_LIMIT = 1.0
LIMITS = [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.15, 0.20, NO_LIMIT]
COUNTS = [0, 25, 50, 75, 100, 125, 150]
RANGES = {"1Y": 12, "3Y": 36, "5Y": 60, "Max": None}
BASE = {"bench": "SPY", "amount": 10_000, "cost": int(round(CFG.cost_rate * 1e4)), "limit": CFG.max_weight, "count": CFG.target_count,
        "weighting": CFG.weighting, "calendar": "Twice a year", "buffer": CFG.buffer > 0, "range": "Max"}
ASSUMPTIONS = ("cost", "limit", "count", "weighting", "calendar", "buffer")      # what changes the backtest itself

st.set_page_config(page_title="Quantile Alpha · Investment tracker", layout="centered")

st.html(f"""
<style>
  /* one centred column, no Streamlit chrome */
  [data-testid="stMainBlockContainer"] {{ max-width: 900px; padding: 2.6rem 1.25rem 4rem; }}
  header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
  #MainMenu, footer, .stDeployButton, [class*="viewerBadge"] {{ display: none !important; }}
  html, body, [data-testid="stAppViewContainer"] {{ background: #FFFFFF; }}

  /* tiles: light grey, hairline border, no shadow */
  .qa-card, .st-key-assumptions {{ background: {TILE}; border: 1px solid {RULE}; border-radius: 12px; box-shadow: none; }}
  .qa-card {{ padding: 16px 18px; }}
  .st-key-assumptions {{ padding: 18px 20px 14px; }}
  .qa-num, .qa-card, .qa-table td, .qa-hero, .qa-holding {{ font-variant-numeric: tabular-nums; }}

  .qa-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 26px; }}
  .qa-brand {{ display: flex; align-items: center; gap: 9px; font-weight: 600; font-size: 15px; letter-spacing: -0.01em; }}
  .qa-brand i {{ width: 11px; height: 11px; border-radius: 50%; background: {GREEN}; display: block; }}
  .qa-brand span {{ color: {GREY}; font-weight: 400; }}
  .qa-links a {{ color: {INK}; text-decoration: none; font-size: 13px; font-weight: 500; margin-left: 18px;
                border-bottom: 1px solid {RULE}; padding-bottom: 1px; }}

  .qa-label {{ color: {GREY}; font-size: 13px; line-height: 1.35; }}
  .qa-hero .qa-value {{ font-size: 54px; line-height: 1.05; font-weight: 700; letter-spacing: -0.035em; margin: 6px 0 8px; }}
  .qa-change {{ font-size: 16px; font-weight: 600; }}
  .qa-change.up, .qa-up {{ color: {GREEN} !important; }}
  .qa-change.down, .qa-down {{ color: {ORANGE} !important; }}
  .qa-sub {{ color: {GREY}; font-size: 13px; margin-top: 6px; line-height: 1.45; }}
  .qa-sub b {{ color: {INK}; font-weight: 600; }}

  .qa-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
  .qa-card .qa-kpi {{ font-size: 27px; line-height: 1.15; font-weight: 700; letter-spacing: -0.03em; margin: 7px 0 5px; }}
  .qa-card .qa-foot {{ color: {GREY}; font-size: 12px; line-height: 1.35; }}
  @media (max-width: 720px) {{ .qa-grid {{ grid-template-columns: repeat(2, 1fr); }} .qa-hero .qa-value {{ font-size: 42px; }} }}

  .qa-h {{ font-size: 17px; font-weight: 600; letter-spacing: -0.015em; margin: 6px 0 2px; }}
  .qa-note {{ color: {GREY}; font-size: 12.5px; line-height: 1.5; }}
  .qa-note b {{ color: {INK}; font-weight: 600; }}
  .qa-chip {{ display: inline-block; border: 1px solid {RULE}; background: #FFFFFF; border-radius: 999px; padding: 3px 11px;
              font-size: 12px; font-weight: 500; margin: 0 6px 6px 0; }}

  table.qa-table {{ width: 100%; border-collapse: collapse; font-size: 14px; border: 0; }}
  .qa-table th {{ color: {GREY}; font-size: 12px; font-weight: 500; text-align: right; padding: 0 0 9px 12px; border: 0;
                 border-bottom: 1px solid {RULE}; background: transparent; }}
  .qa-table td {{ text-align: right; padding: 10px 0 10px 12px; border: 0; border-bottom: 1px solid {RULE}; background: transparent; }}
  .qa-table th:first-child, .qa-table td:first-child {{ text-align: left; padding-left: 0; }}
  .qa-table tr:last-child td {{ border-bottom: 0; }}
  .qa-table td.s {{ font-weight: 600; }}
  .qa-table .m {{ color: {GREY}; }}

  .qa-holding {{ padding: 9px 0; border-bottom: 1px solid {RULE}; font-size: 14px; }}
  .qa-holding:last-child {{ border-bottom: 0; }}
  .qa-holding .l {{ display: flex; justify-content: space-between; margin-bottom: 7px; }}
  .qa-holding .r {{ display: inline-block; width: 26px; color: {GREY}; }}
  .qa-holding .t {{ color: {GREY}; font-size: 12px; margin-left: 8px; }}
  .qa-holding .w {{ font-weight: 600; }}
  .qa-bar {{ height: 4px; border-radius: 2px; background: {RULE}; overflow: hidden; }}
  .qa-bar i {{ display: block; height: 100%; border-radius: 2px; background: {GREEN}; }}

  /* Streamlit widgets, quietened; the chosen option is black, as in a broker app */
  [data-testid="stButtonGroup"] button[aria-checked="true"] {{ background: {INK} !important; border-color: {INK} !important; color: #FFFFFF !important; }}
  [data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: #FFFFFF !important; }}
  [data-testid="stButtonGroup"] button {{ background: #FFFFFF; }}
  [data-testid="stWidgetLabel"] p {{ font-size: 12.5px; color: {GREY}; }}
  .stSlider [data-testid="stThumbValue"], .stSlider [data-testid="stTickBarMin"], .stSlider [data-testid="stTickBarMax"] {{ font-variant-numeric: tabular-nums; }}
  [data-testid="stExpander"] details {{ border: 1px solid {RULE}; border-radius: 12px; background: #FFFFFF; }}
  hr {{ border-color: {RULE}; }}
</style>
""")


# ------------------------------------------------------------------ data

@st.cache_resource(show_spinner=False)
def _snapshot(folder):
    bundle, meta = app_data.load_bundle(folder)
    return bundle, meta


@st.cache_resource(show_spinner=False)
def _live():
    data, retrieved = app_data.download_data(CFG, say=lambda text: None)
    bundle = app_data.compact_bundle(data)
    return bundle, {"data_retrieved_utc": retrieved, "base_case": None, "engine": app_data.engine_fingerprint()}


@st.cache_resource(show_spinner=False)
def _state():
    return {"live_ready": False}


def use_snapshot():
    return app_data.has_bundle(DATA_DIR) and os.environ.get("QA_APP_LIVE", "0") != "1"


def current_bundle():
    """The data, without drawing anything on the page (cached functions call this)."""
    return (_snapshot(str(DATA_DIR)) if use_snapshot() else _live())[0]


def load_data():
    """(bundle, meta, route). The snapshot when there is one, otherwise a download through the engine."""
    if use_snapshot():
        return (*_snapshot(str(DATA_DIR)), "snapshot")
    state = _state()
    if not state["live_ready"]:
        try:
            key = st.secrets.get("FRED_API_KEY")      # optional; without a key the engine uses FRED's key-less endpoint
            if key:
                os.environ.setdefault("FRED_API_KEY", str(key))
        except Exception:
            pass
        with st.status("Retrieving the data from Yahoo Finance, FRED and Wikipedia. The first start takes five to fifteen "
                       "minutes; after that the app answers at once.", expanded=False):
            _live()
        state["live_ready"] = True
        st.rerun()                                    # draw the page without the progress box
    return (*_live(), "live")


@st.cache_data(show_spinner=False, max_entries=128)
def backtest(cost_bp, limit, count, weighting, months, buffer):
    """One run of the engine for one set of assumptions. Everything shown on the page is read from its result."""
    bundle = current_bundle()
    cfg = replace(bundle["cfg"], cost_rate=cost_bp / 1e4, weighting=weighting, rebalance_months=tuple(months),
                  buffer=CFG.buffer if buffer else 0.0, target_count=int(count),
                  max_weight=float(limit),                                  # NO_LIMIT switches both weight limits off
                  max_cap_multiple=1e9 if limit >= NO_LIMIT else CFG.max_cap_multiple)
    bt = run_backtest(bundle, cfg)
    return {"returns": bt["returns"], "rf": bt["rf"], "metrics": bt["metrics"], "trading": bt["trading"],
            "selection": bt["selection"], "targets": bt["runs"][STRATEGY]["targets"], "warnings": bt["warnings"]}


def run(settings):
    return backtest(settings["cost"], settings["limit"], settings["count"], settings["weighting"],
                    CALENDAR[settings["calendar"]], settings["buffer"])


# ------------------------------------------------------------------ formatting (display only)

def neg(text):
    return text.replace("-", MINUS)


def pct(x, digits=1, sign=False):
    return "–" if pd.isna(x) else neg(f"{x * 100:{'+' if sign else ''}.{digits}f}%")


def num(x, digits=2):
    return "–" if pd.isna(x) else neg(f"{x:.{digits}f}")


def usd(x, sign=False):
    return neg(f"{'+' if sign and x >= 0 else ''}{'-' if x < 0 else ''}${abs(x):,.0f}")


def points(x, digits=1):
    if pd.isna(x):
        return "–"
    v = round(x * 100, digits)
    return f"{0:.{digits}f}" if v == 0 else neg(f"{v:+.{digits}f}")


def tone(x):
    return "qa-up" if x >= 0 else "qa-down"


def limit_text(v):
    return "No limit" if v >= NO_LIMIT else f"{v:.0%}"


def count_text(v):
    return "Best fifth" if v == 0 else f"{v} stocks"


# ------------------------------------------------------------------ state

for key, value in BASE.items():
    st.session_state.setdefault(key, value)


def reset():
    for key, value in BASE.items():
        if key not in ("bench", "amount", "range"):
            st.session_state[key] = value


bundle, meta, route = load_data()
sessions = bundle["panel"]["sessions"]

# ------------------------------------------------------------------ header and controls

st.html(f"""
<div class="qa-top">
  <div class="qa-brand"><i></i>Quantile Alpha <span>Investment tracker</span></div>
  <div class="qa-links"><a href="{PROSPECTUS}" target="_blank">Prospectus</a><a href="{REPOSITORY}" target="_blank">Source code</a></div>
</div>""")

hero = st.container()

with st.container(border=True, key="assumptions"):
    st.html('<div class="qa-h">Assumptions</div><div class="qa-note">Change one and the backtest is run again with the '
            'notebook&rsquo;s engine. The prospectus uses the settings shown at the start.</div>')
    a, b = st.columns([2.2, 1], gap="medium")
    a.segmented_control("Compare with", list(NAME)[1:], format_func=NAME.get, key="bench", required=True)
    b.number_input("Amount invested (USD)", min_value=100, max_value=10_000_000, step=1_000, key="amount")
    a, b = st.columns([1, 1.2], gap="medium")
    a.segmented_control("Weights follow", list(WEIGHTING), format_func=WEIGHTING.get, key="weighting", required=True)
    b.segmented_control("Rebalanced", list(CALENDAR), key="calendar", required=True)
    a, b, c = st.columns(3, gap="medium")
    a.slider("Trading cost (basis points per dollar)", 0, 100, step=5, key="cost")
    b.select_slider("Largest weight per stock", LIMITS, format_func=limit_text, key="limit")
    c.select_slider("Stocks held", COUNTS, format_func=count_text, key="count")
    st.toggle("Buffer rule: a stock already held stays until it falls clearly behind", key="buffer")

settings = {key: st.session_state[key] for key in BASE}
is_base = all(settings[key] == BASE[key] for key in ASSUMPTIONS)

try:
    bt = run(settings)
except ValueError as problem:                       # for example 25 stocks with a 3% limit: the weights cannot add up
    st.html(f'<div class="qa-card"><b>These assumptions cannot be combined.</b> <span class="qa-note">{html.escape(str(problem).capitalize())}. '
            'Raise the weight limit or hold more stocks.</span></div>')
    st.button("Back to the prospectus settings", on_click=reset)
    st.stop()
base = bt if is_base else run({**settings, **{key: BASE[key] for key in ASSUMPTIONS}})

if not is_base:
    label = {"cost": f"Trading cost {settings['cost']} bp", "limit": f"Weight limit {limit_text(settings['limit']).lower()}",
             "count": count_text(settings["count"]), "weighting": f"Weights: {WEIGHTING[settings['weighting']].lower()}",
             "calendar": f"Rebalanced {settings['calendar'].lower()}", "buffer": "Buffer on" if settings["buffer"] else "No buffer"}
    chips = "".join(f'<span class="qa-chip">{html.escape(label[key])}</span>' for key in ASSUMPTIONS if settings[key] != BASE[key])
    now, then = bt["metrics"].loc[STRATEGY, "ann_return"], base["metrics"].loc[STRATEGY, "ann_return"]
    left, right = st.columns([3.4, 1], vertical_alignment="center")
    left.html(f'<div>{chips}</div><div class="qa-note">Average return a year <b>{pct(now)}</b> instead of {pct(then)} with the '
              f'prospectus settings: <b class="{tone(now - then)}">{points(now - then)} points</b>.</div>')
    right.button("Reset", on_click=reset, width="stretch")

# ------------------------------------------------------------------ the selected window

bench = settings["bench"]
months = RANGES[settings["range"]]
R_all = bt["returns"][[STRATEGY, bench]].dropna()
R = R_all if months is None else R_all.iloc[-months:]
rf = bt["rf"].reindex(R.index)
start_month = R.index[0] - 1
value = pd.concat([pd.DataFrame(1.0, index=[start_month], columns=R.columns), (1.0 + R).cumprod()]) * settings["amount"]
dates = [sessions[m] for m in value.index]
stats = {STRATEGY: performance_stats(R[STRATEGY], rf, R[bench]), bench: performance_stats(R[bench], rf, R[bench], is_benchmark=True)}
s, q = stats[STRATEGY], stats[bench]
end_s, end_b = float(value[STRATEGY].iloc[-1]), float(value[bench].iloc[-1])
gain = end_s - settings["amount"]
since = f"{sessions[start_month]:%B %Y}"

with hero:
    st.html(f"""
<div class="qa-hero">
  <div class="qa-label">Value of {usd(settings['amount'])} invested at the end of {since}</div>
  <div class="qa-value">{usd(end_s)}</div>
  <div class="qa-change {'up' if gain >= 0 else 'down'}">{'▲' if gain >= 0 else '▼'} {usd(gain, sign=True)} &nbsp;·&nbsp; {pct(end_s / settings['amount'] - 1, sign=True)}</div>
  <div class="qa-sub">{html.escape(NAME[bench])}: <b>{usd(end_b)}</b> &nbsp;·&nbsp; {pct(end_b / settings['amount'] - 1, sign=True)}
    &nbsp;&nbsp; Difference: <b class="{tone(end_s - end_b)}">{usd(end_s - end_b, sign=True)}</b></div>
</div>""")

# ------------------------------------------------------------------ value over time

FONT = dict(family="Inter, sans-serif", size=12, color=GREY)


def style(fig, height):
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=8, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=FONT, hovermode="x unified", showlegend=True,
                      hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=RULE, font=dict(family="Inter, sans-serif", size=12, color=INK)),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=12, color=INK),
                                  bgcolor="rgba(0,0,0,0)", traceorder="reversed"))
    fig.update_xaxes(showgrid=False, showline=False, zeroline=False, ticks="", tickfont=FONT, hoverformat="%B %Y", automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=RULE, gridwidth=1, zeroline=False, showline=False, ticks="", tickfont=FONT, side="right",
                     automargin=True)
    return fig


PLOT = {"displayModeBar": False, "scrollZoom": False}

st.html('<div style="height: 6px"></div>')
left, right = st.columns([2, 1], vertical_alignment="center")
left.html(f'<div class="qa-h">Value over time</div><div class="qa-note">After trading costs, dividends reinvested; '
          f'both lines start at {usd(settings["amount"])}.</div>')
with right:
    st.segmented_control("Period", list(RANGES), key="range", required=True, label_visibility="collapsed", width="stretch")

fig = go.Figure()
fig.add_trace(go.Scatter(x=dates, y=value[bench], name=NAME[bench], mode="lines", line=dict(color=LIGHT, width=1.6),
                         hovertemplate="%{y:$,.0f}"))
fig.add_trace(go.Scatter(x=dates, y=value[STRATEGY], name=NAME[STRATEGY], mode="lines", line=dict(color=INK, width=2.4),
                         hovertemplate="%{y:$,.0f}"))
fig.update_yaxes(tickprefix="$", tickformat=",.0f")
st.plotly_chart(style(fig, 380), theme=None, config=PLOT, key="value_chart")

# ------------------------------------------------------------------ measures

lead = s["ann_return"] - q["ann_return"]
st.html(f"""
<div class="qa-grid">
  <div class="qa-card"><div class="qa-label">Return a year</div><div class="qa-kpi {tone(s['ann_return'])}">{pct(s['ann_return'])}</div>
    <div class="qa-foot">{html.escape(NAME[bench])}: {pct(q['ann_return'])}</div></div>
  <div class="qa-card"><div class="qa-label">Lead over the benchmark</div><div class="qa-kpi {tone(lead)}">{points(lead)}</div>
    <div class="qa-foot">percentage points a year</div></div>
  <div class="qa-card"><div class="qa-label">Sharpe ratio</div><div class="qa-kpi">{num(s['sharpe'])}</div>
    <div class="qa-foot">{html.escape(NAME[bench])}: {num(q['sharpe'])}</div></div>
  <div class="qa-card"><div class="qa-label">Largest loss from a high</div><div class="qa-kpi qa-down">{pct(s['max_drawdown'])}</div>
    <div class="qa-foot">{html.escape(NAME[bench])}: {pct(q['max_drawdown'])}</div></div>
</div>""")

show_base = not is_base
if show_base:
    Rb = base["returns"][[STRATEGY, bench]].dropna().reindex(R.index)
    sb = performance_stats(Rb[STRATEGY], base["rf"].reindex(R.index), Rb[bench])
    end_base = float((1.0 + Rb[STRATEGY]).prod()) * settings["amount"]
rows = [("Average return a year", pct(s["ann_return"]), pct(q["ann_return"]), "ann_return", pct),
        ("Volatility a year", pct(s["ann_vol"]), pct(q["ann_vol"]), "ann_vol", pct),
        ("Sharpe ratio", num(s["sharpe"]), num(q["sharpe"]), "sharpe", num),
        ("Alpha a year against the benchmark", pct(s["alpha"]), "–", "alpha", pct),
        ('Beta against the benchmark <span class="m">(not annualised)</span>', num(s["beta"]), "1.00", "beta", num),
        ("Information ratio", num(s["info_ratio"]), "–", "info_ratio", num),
        ("Largest loss from a high", pct(s["max_drawdown"]), pct(q["max_drawdown"]), "max_drawdown", pct)]
body = "".join(f'<tr><td>{name}</td><td class="s">{mine}</td><td>{theirs}</td>'
               + (f'<td class="m">{fmt(sb[field])}</td>' if show_base else "") + "</tr>" for name, mine, theirs, field, fmt in rows)
body += (f'<tr><td>Value of {usd(settings["amount"])} at the end</td><td class="s">{usd(end_s)}</td><td>{usd(end_b)}</td>'
         + (f'<td class="m">{usd(end_base)}</td>' if show_base else "") + "</tr>")
st.html(f"""
<div style="height: 14px"></div>
<div class="qa-h">Performance measures</div>
<div class="qa-note" style="margin-bottom: 12px">{R.index[0].strftime('%B %Y')} to {R.index[-1].strftime('%B %Y')}, {len(R)} monthly returns after trading costs.
  Benchmark: {html.escape(NAME[bench])}, {BENCHMARK_NOTE[bench]}.</div>
<table class="qa-table">
  <thead><tr><th></th><th>Quantile Alpha</th><th>{html.escape(NAME[bench])}</th>{'<th>Quantile Alpha, prospectus settings</th>' if show_base else ''}</tr></thead>
  <tbody>{body}</tbody>
</table>
<div class="qa-note" style="margin-top: 10px">Average return 12 × the mean monthly return; volatility √12 × the standard deviation; Sharpe ratio from
  returns above the 3-month Treasury bill; alpha (× 12) and beta from a regression of excess returns on the benchmark&rsquo;s; information ratio =
  return difference a year divided by the tracking error{f' ({pct(s["tracking_error"])})' if not pd.isna(s['tracking_error']) else ''}.</div>""")

# ------------------------------------------------------------------ years and drawdowns

st.html('<div style="height: 10px"></div>')
left, right = st.columns(2, gap="large")

yearly = (1.0 + R).groupby(R.index.year).prod() - 1.0
gap = (yearly[STRATEGY] - yearly[bench]) * 100
ahead = int((gap > 0).sum())
with left:
    st.html(f'<div class="qa-h">Lead by calendar year</div><div class="qa-note">Quantile Alpha minus {html.escape(NAME[bench])}, '
            f'percentage points. Ahead in <b>{ahead} of {len(gap)}</b> {"years" if len(gap) != 1 else "year"}.</div>')
    fig = go.Figure(go.Bar(x=[str(y) for y in gap.index], y=gap, marker_color=[GREEN if v >= 0 else ORANGE for v in gap],
                           text=[points(v / 100) for v in gap], textposition="outside", cliponaxis=False,
                           textfont=dict(family="Inter, sans-serif", size=12, color=INK),
                           hovertemplate="%{x}: %{y:+.1f} points<extra></extra>"))
    fig = style(fig, 300)
    reach = max(float(gap.abs().max()), 1.0)
    fig.update_layout(showlegend=False, bargap=0.38, hovermode="closest", margin=dict(l=0, r=0, t=22, b=0))
    fig.update_yaxes(visible=False, range=[min(float(gap.min()), 0) - 0.22 * reach, max(float(gap.max()), 0) + 0.22 * reach])
    fig.update_xaxes(type="category")
    fig.add_hline(y=0, line_color=INK, line_width=1)
    st.plotly_chart(fig, theme=None, config=PLOT, key="year_chart")

dd = (value / settings["amount"]).apply(drawdown_series) * 100
with right:
    st.html(f'<div class="qa-h">Loss from the previous high</div><div class="qa-note">Month-end values. Deepest loss: '
            f'<b class="qa-down">{pct(s["max_drawdown"])}</b>, {html.escape(NAME[bench])} {pct(q["max_drawdown"])}.</div>')
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=dd[bench], name=NAME[bench], mode="lines", line=dict(color=LIGHT, width=1.4),
                             hovertemplate="%{y:.1f}%"))
    fig.add_trace(go.Scatter(x=dates, y=dd[STRATEGY], name=NAME[STRATEGY], mode="lines", line=dict(color=ORANGE, width=2),
                             fill="tozeroy", fillcolor="rgba(241, 96, 52, 0.12)", hovertemplate="%{y:.1f}%"))
    fig = style(fig, 300)
    fig.update_layout(showlegend=False, margin=dict(l=0, r=0, t=22, b=0))
    fig.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig, theme=None, config=PLOT, key="drawdown_chart")

# ------------------------------------------------------------------ holdings and trading

st.html('<div style="height: 6px"></div>')
targets = bt["targets"]
trade_months = sorted(targets)
left, right = st.columns([2, 1], vertical_alignment="bottom")
left.html('<div class="qa-h">Holdings</div><div class="qa-note">Target weights at the close of the trade date. '
          'Between two dates nothing is traded and the weights drift with prices.</div>')
chosen = right.selectbox("Trade date", trade_months[::-1], format_func=lambda m: f"{sessions[m]:%d %B %Y}".lstrip("0"),
                         label_visibility="collapsed", key="trade_month")
weights = targets[chosen].sort_values(ascending=False)
names = bundle["forms"][chosen]["name"]
top = float(weights.iloc[0])
items = "".join(
    f'<div class="qa-holding"><div class="l"><span><span class="r">{i}</span>{html.escape(str(names.get(sym, sym)))}'
    f'<span class="t">{html.escape(sym)}</span></span><span class="w">{pct(w)}</span></div>'
    f'<div class="qa-bar"><i style="width: {w / top * 100:.1f}%"></i></div></div>'
    for i, (sym, w) in enumerate(weights.head(10).items(), start=1))
trade = bt["trading"].loc[STRATEGY]
facts = [("Stocks held", f"{len(weights)}"), ("Ten largest together", pct(weights.head(10).sum(), 0)),
         ("Largest position", pct(top)), ("Turnover a year, one way", pct(trade["one_way_turnover_pa"], 0)),
         ("Trading cost a year", pct(trade["cost_pa"], 2)),
         (f"Cost a year on {usd(settings['amount'])}", f"about {usd(trade['cost_pa'] * settings['amount'])}")]
left, right = st.columns([1.55, 1], gap="large")
left.html(f'<div class="qa-card" style="padding: 8px 18px">{items}</div>')
right.html('<table class="qa-table">' + "".join(f"<tr><td>{k}</td><td class='s'>{v}</td></tr>" for k, v in facts) + "</table>")

# ------------------------------------------------------------------ notes

retrieved = meta.get("data_retrieved_utc")
check = ""
if meta.get("base_case"):
    stored = meta["base_case"]["Strategy"]["ann_return"]
    fresh = base["metrics"].loc[STRATEGY, "ann_return"]
    same = abs(stored - fresh) < 1e-9
    check = (f"With the prospectus settings the engine returns {pct(fresh, 2)} a year, "
             + ("the figure stored with the data when the notebook was run." if same
                else f"but {pct(stored, 2)} was stored with the data: the engine has changed since the snapshot was written."))
st.html('<div style="height: 8px"></div>')
with st.expander("How this is calculated, and what it does not show"):
    st.markdown(f"""
**The rule.** Twice a year every S&P 500 member is scored by its price change over twelve months, leaving out the most recent
month, divided by the volatility of its daily price changes. The best fifth is bought and weighted by market value times score,
with a limit of 9% per stock when the weights are set. These are the published construction rules of the S&P 500 Momentum index.

**Same engine as the notebook.** Every change above calls `run_backtest` from `quantile_alpha/engine.py`, the code exported from
the group's notebook; the measures come from its `performance_stats`. {check}

**Data.** Yahoo Finance (prices and share counts), FRED (3-month Treasury yield) and Wikipedia (dates of index changes),
retrieved through their APIs{f' on {retrieved} UTC' if retrieved else ''}. {'The app starts from a stored snapshot of the monthly returns, scores and index weights derived from them.' if route == 'snapshot' else 'The data were retrieved when this app started.'}
Sample: {R_all.index[0].strftime('%B %Y')} to {R_all.index[-1].strftime('%B %Y')}.

**What it does not show.** This is a backtest: the rule set was chosen knowing how momentum had performed in this period. Yahoo
Finance no longer carries most companies that were acquired or went bankrupt, which flatters stock portfolios by roughly 0.3
percentage points a year. Taxes are not modelled. Settings of the momentum score itself cannot be changed here; the notebook
covers them.

**No advice.** A course project, not an offer. Capital is at risk and no return is guaranteed. Past performance is not a
reliable guide to future performance.
""")
st.html(f'<div class="qa-note" style="margin-top: 14px">2270 Financial Modeling · Group assignment · '
        f'<a href="{REPOSITORY}" target="_blank" style="color: inherit">github.com/benediktproebstl/quantile-alpha</a></div>')
