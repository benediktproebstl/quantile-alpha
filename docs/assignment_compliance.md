# Compliance matrix

Status meanings: **PASS** = verified, with the evidence named. **CONFIRMED by the group** = reported by the group members; not verified by the AI assistant. **GROUP** = needs a decision, a detail or a check from the group members. **NOT TESTED** = not executed.

## Assignment brief (2270 Financial Modeling, group assignment)

| Requirement | Status | Evidence |
|---|---|---|
| Target clientele: objectives, horizon, attitude to risk | PASS | Notebook section 0 |
| Underlying assets and why they suit those clients | PASS | Section 0; suitability verdict in 12.2 |
| Allocation rule: how capital is divided, how weights are set, when holdings are rebalanced; motivated | PASS | Sections 0, 4.1 to 4.6; worked example 4.7; economic rationale in section 0 |
| Backtest with historical data obtained through an API | PASS | Section 2; nothing is read from files |
| Source, sample period, frequency and data adjustments documented | PASS | Table and rules in section 2; provenance log in 11.4 |
| Portfolio returns calculated from the stated holdings and rule | PASS | Sections 4 and 5; recalculations without the engine in 11.2 |
| Decisions use only information available at the time | PASS, with stated exceptions for share counts | Timing table 4.4; look-ahead test in 11.1; timing checks and the rebuild of every share count in 11.2. Exceptions (section 2): the unit of a count near a stock split is read with the help of the stock's other counts; the count before Yahoo's gap is left out; a stock's first count is carried back up to 120 days (variants in 8.1) |
| Cumulative performance against at least one benchmark, both starting at 1 | PASS | Figure in 6.1 (SPY and the cap-weighted universe) |
| Annualised average return, volatility, Sharpe ratio, alpha, information ratio, and beta (not annualised) | PASS | Table in 6.2; formula tests in 11.1 |
| Calculation assumptions stated | PASS | Section 4.8 |
| Every reported measure interpreted, with meaning for the target client | PASS | Text after each table in sections 6 to 10; 12.2 |
| Implementation: rebalancing and transaction costs | PASS | Sections 4.6, 6.4, 8.1, 8.2, 9.2 |
| Risks and limitations: concentration, look-ahead bias, survivorship bias | PASS | Sections 3.3, 5.2, 6.4, 8.3, 9.1, 9.3, 12.3 |
| Start and end dates set explicitly in the code | PASS | `Config` in section 1 |
| Notebook reproduces every number, table and figure | PASS | All tables and figures are written to `outputs/` by the notebook (18 figures, 45 tables) |
| Notebook runs start to finish in a fresh Google Colab session | CONFIRMED by the group | The group reports a complete run in Google Colab on 25 November 2026. Runs start to finish in a clean environment with Colab's package versions; see `validation_report.md` |
| Setup instructions; data through an API; no separate data files | PASS | Section 1 |
| Generative-AI use disclosed: tools, purpose, how outputs were checked | PASS | Section 12.5 of the notebook, page 7 of the prospectus and `ai_usage_log.md` state the AI's part and the checks the group reports. The group states that it used no other AI tool |
| Moodle group name and all members named | PASS | Group BC and its 6 members: top of the notebook and cover of the prospectus. Student numbers appear only in the copies for Moodle (`tools/make_submission.py`), not in this public repository |
| Prospectus: PDF, at most 7 content pages plus optional cover, references and app evidence inside | PASS for the page count; GROUP for the details | `investor_prospectus.pdf`: a cover and 7 content pages (the build script counts them and stops if a page overflows); references, AI disclosure and the app's screenshot and links are on page 7. All details are entered |
| Prospectus: every number, table and figure reproduced by the notebook | PASS | Notebook section 12.6 writes the five figures and `tab_prospectus_key_figures.csv` (223 numbers with their source sections); `prospectus/build_prospectus.py` prints them and calculates nothing. The app screenshot is the one exhibit that does not come from the notebook |
| Two files, under 50 MB in total | PASS | Notebook 2.4 MB, prospectus 0.4 MB |
| Optional app: lets the user change a meaningful assumption and see performance and the benchmark comparison; calculations consistent with the notebook | PASS | `tracker_app.py`: six assumptions and three benchmarks; every change calls the notebook's `run_backtest`; `tests/test_tracker_app.py` compares its figures with the engine's |
| Optional app: deployed on Streamlit, source on GitHub, both URLs in prospectus and notebook | PASS | Source, dependencies (`requirements.txt`) and run instructions (`README.md`) are in the repository. Deployed at <https://quantile-alpha.streamlit.app>; opened and checked on 25 November 2026 (`validation_report.md`, section 10) |

Lecture 5 adds one expectation that is not in the brief: the Monte Carlo section must **state and justify its simulation design** (independent coin flip or Markov chain). PASS: notebook section 10 states nine design decisions with reasons, runs both designs, and shows how the choice changes the risk figures.

## Good practice beyond the brief

| Item | Status | Where |
|---|---|---|
| AI usage and decision log; no invented approval or verification | PASS | `ai_usage_log.md`, `decision_log.md` |
| Economic motivation with verified references | PASS | Section 0; references in 12.4 |
| Historical constituents at each reference date; ticker mappings; reused tickers; share classes | PASS | Section 3; `data_feasibility.md` |
| Data-quality gates, with failures reported | PASS | Section 3.4; `data_feasibility.md`, section 7 |
| Yahoo retrieval: explicit `auto_adjust`, end-date check, month-end on the final session, no forward fill, no winsorising of returns | PASS | Sections 2 and 3; tests |
| Exact self-financing costs; both turnover definitions; gross as a separate run; NAV starts at 1 | PASS | Section 4.6; tests |
| Checks against real funds (SPY for the universe, SPMO for the strategy) | PASS | Section 5.2 |
| Quintile portfolios, Q5 minus Q1, stock-level regressions and rank correlations | PASS | Section 7 |
| One-at-a-time sensitivities, break-even cost, rank migration, rolling measures, block bootstrap, random-portfolio baseline | PASS | Section 8 |
| Statement that the result is in-sample | PASS | Sections 8, 9.3 and 12.3 |
| Sector exposure with today's labels, clearly restricted | PASS | Section 9.1 |
| Risk and bias audit; retail example with USD 100,000 | PASS | Sections 9.2 and 9.3 |
| Central configuration; calculation separate from plotting; reusable backtest function for the app | PASS | `Config`; engine cells; `run_backtest`; `tracker_app.md` |
| Automated tests, including one that rewrites future data | PASS | 46 tests |
