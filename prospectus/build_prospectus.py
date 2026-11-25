"""Build investor_prospectus.pdf from what the notebook wrote.

    python prospectus/build_prospectus.py

Reads   outputs/tables/tab_prospectus_key_figures.csv   every number, with its text "as printed" (notebook, section 12.6)
        outputs/prospectus/px_*.svg                      the five figures (notebook, section 12.6)
        prospectus/details.toml                          group name, members, date, app link: filled in by the group
        prospectus/template.html, style.css              text and layout
        static/Inter-*.ttf                               the typeface (shared with the tracker app)
        prospectus/app_screenshot.png                    optional: a screenshot of the tracker app
Writes  prospectus/build/investor_prospectus.html        the page that is printed
        investor_prospectus.pdf                          cover + 7 content pages, A4

With --submission the cover also shows the student numbers from prospectus/details.local.toml (a file git ignores,
because this repository is public) and the PDF goes to submission/investor_prospectus.pdf.

This script calculates no result. It prints the notebook's numbers into the template, and it refuses to build when a
sentence of the template no longer fits the numbers (see check_claims) or when a page overflows. The PDF is printed
by a Chromium-based browser in headless mode (Google Chrome, Chromium or Microsoft Edge must be installed).
"""
import argparse, base64, csv, json, os, re, shutil, subprocess, sys, tempfile, tomllib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT_PAGES = 7
MINUS = "\u2212"

FIGURES = {"cumulative": "px_cumulative_performance", "years": "px_calendar_years", "groups": "px_score_groups",
           "drawdowns": "px_drawdowns", "montecarlo": "px_monte_carlo"}
FIGURE_TEXT = {"cumulative": "Line chart: value of one dollar in the strategy, the S&P 500 index fund and the cap-weighted universe",
               "years": "Bar chart: strategy return minus index fund return for each calendar year",
               "groups": "Bar chart: average return per year of the five momentum score groups",
               "drawdowns": "Line chart: loss from the previous high, strategy and index fund",
               "montecarlo": "Fan chart: simulated value of 100,000 dollars over ten years"}
FONTS = (("Inter-Regular.ttf", 400), ("Inter-Medium.ttf", 500), ("Inter-SemiBold.ttf", 600), ("Inter-Bold.ttf", 700))

# the sensitivity table of page 6: label, key of the variant in the key-figure table
SENSITIVITIES = (("Base case", None), ("Equal weights", "sens_equal"), ("Market value only, no score", "sens_cap"),
                 ("No weight limits", "sens_nolimit"), ("Best tenth, not best fifth", "sens_top10"),
                 ("No buffer rule", "sens_nobuffer"), ("No risk adjustment", "sens_norisk"),
                 ("One stock fewer each time", "sens_fewer"), ("One stock more each time", "sens_more"),
                 ("Rebalanced every quarter", "sens_quarterly"), ("Rebalanced once a year", "sens_yearly"),
                 ("Trading cost of 50 bp", "sens_cost50"))


def typographic(text):
    """A real minus sign in front of numbers; nothing else is changed."""
    return re.sub(r"(?<![\w.])-(?=[\d$.])", MINUS, text)


def load_key_figures(path):
    """-> (k, v): the text of every key figure as printed, and its value as a number where it is one."""
    k, v = {}, {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            k[row["key"]] = typographic(row["as printed"])
            try:
                v[row["key"]] = float(row["value"])
            except ValueError:
                v[row["key"]] = row["value"]
    return k, v


def check_claims(k, v):
    """Every statement the template makes in words must hold in the numbers. A failure means: rewrite the sentence."""
    claims = [
        ("the strategy returned more than the index fund", v["ret_s"] > v["ret_spy"] and v["lead_pp"] > 0 and v["value_s"] > v["value_spy"]),
        ("volatility is a little higher than the index fund's, and similar", 0 < v["vol_s"] - v["vol_spy"] < 0.03),
        ("the Sharpe ratio is above the index fund's", v["sharpe_s"] > v["sharpe_spy"]),
        ("alpha is positive but not statistically significant", v["alpha_s"] > 0 and abs(v["alpha_t"]) < 1.96 and v["alpha_ci_low"] < 0 < v["alpha_ci_high"]),
        ("beta is close to one", 0.85 < v["beta_s"] < 1.05),
        ("the worst loss is about the index fund's", abs(v["mdd_s"] - v["mdd_spy"]) < 0.03),
        ("the deepest drawdown has been recovered", k["dd_recovered"] != "not yet"),
        ("ahead in more calendar years than behind", v["years_ahead"] > v["years_behind"] and v["years_ahead"] + v["years_behind"] == v["n_years"]),
        ("the sample is ten calendar years ending in December 2025", v["n_years"] == 10 and v["sample_last"] == "2025-12"),
        ("most of the lead was earned in 2024 and 2025", v["late_share"] > 0.5 and 0 < v["lead_2023"] < v["lead_end"]),
        ("equal weights trail the index fund", v["sens_equal_vs_spy"] < 0),
        ("every other variant stays ahead of the index fund", all(v[key + "_vs_spy"] > 0 for _, key in SENSITIVITIES if key and key != "sens_equal")),
        ("only the top score group stands out", v["q5_ret"] == max(v[f"q{i}_ret"] for i in range(1, 6)) and abs(v["spread_t"]) < 1.96),
        ("the bootstrap interval of the lead includes zero", v["boot_low"] < 0 < v["boot_high"]),
        ("the strategy beats random selection", v["random_pctile"] >= 0.95),
        ("backtest and real fund agree", abs(v["spmo_backtest"] - v["spmo_fund"]) < 0.01 and v["spmo_corr"] > 0.95),
        ("the simulated median is above the index fund's", v["mc_median_s"] > v["mc_median_b"] > v["mc_start"]),
        ("clustered recessions make deep losses more likely", v["mc_dd30"] > v["mc_dd30_coin"]),
        ("without alpha the strategy is more likely to end behind", v["mc_behind"] < v["mc_behind0"]),
        ("coverage improves over the sample and some gates fail", v["coverage_first"] < v["coverage_last"] and v["gates_passed"] < v["gates_total"]),
        ("the strategy lagged in all five worst months for high scores", v["worst_rel_count"] == 5),
        ("some positions are smaller than one share", v["retail_below_one"] > 0),
        ("the rule is the one described in words", v["rule_lookback"] == 12 and v["rule_skip"] == 1 and k["rule_fraction"] == "fifth"
         and k["rule_trades_per_year"] == "twice" and abs(v["rule_buffer"] - 0.20) < 1e-12),
        ("the ten largest holdings are listed in order", all(v[f"top{i}_weight"] >= v[f"top{i + 1}_weight"] for i in range(1, 10))),
    ]
    failed = [text for text, holds in claims if not holds]
    if failed:
        raise SystemExit("The prospectus text no longer fits the notebook's numbers:\n  - " + "\n  - ".join(failed))
    return len(claims)


def inline_svg(path, prefix, label):
    """A matplotlib SVG as inline markup: no prolog, no fixed size, ids made unique within the document."""
    svg = path.read_text(encoding="utf-8")
    svg = svg[svg.index("<svg"):]
    svg = re.sub(r"<metadata>.*?</metadata>", "", svg, flags=re.S)
    svg = re.sub(r'\b(id|clip-path|xlink:href|href)="(url\(#|#)?([^")]+)(\))?"',
                 lambda m: f'{m.group(1)}="{m.group(2) or ""}{prefix}-{m.group(3)}{m.group(4) or ""}"'
                 if (m.group(1) == "id" or m.group(2)) else m.group(0), svg)
    svg = re.sub(r'<svg ([^>]*?)width="[^"]*" height="[^"]*"', r"<svg \1", svg, count=1)
    return Markup(svg.replace("<svg ", f'<svg role="img" aria-label="{label}" ', 1))


def fonts_css():
    rules = []
    for name, weight in FONTS:
        data = base64.b64encode((ROOT / "static" / name).read_bytes()).decode("ascii")
        rules.append(f'@font-face {{ font-family: "Inter"; font-style: normal; font-weight: {weight}; '
                     f'src: url("data:font/ttf;base64,{data}") format("truetype"); }}')
    return Markup("\n".join(rules))


def load_details(with_student_numbers=False):
    """The group's details. Student numbers are kept out of the public repository: they are read from
    details.local.toml (ignored by git) only for the copy that is submitted."""
    with open(HERE / "details.toml", "rb") as handle:
        d = tomllib.load(handle)
    numbers = {}
    if with_student_numbers:
        local = HERE / "details.local.toml"
        if not local.exists():
            raise SystemExit("prospectus/details.local.toml is missing: it holds the student numbers for the submitted copy.")
        with open(local, "rb") as handle:
            numbers = tomllib.load(handle).get("student_numbers", {})
    people = []                                   # a member is a name, or a table with a name and a student number
    for m in d.get("members", []):
        m = {"name": m} if isinstance(m, str) else dict(m)
        name = str(m.get("name", "")).strip()
        number = str(numbers.get(name, m.get("number", "") if with_student_numbers else "")).strip()
        if name:
            people.append({"name": name, "number": number})
    d["members"] = people
    for field in ("course", "moodle_group", "submission_date", "app_url", "repository_url", "group_checks", "other_ai_tools"):
        d[field] = str(d.get(field, "")).strip()
    for field in ("app_url", "repository_url"):                  # printed without the scheme; may break after a slash
        d[field + "_text"] = Markup("/<wbr>").join(re.sub(r"^https?://", "", d[field]).rstrip("/").split("/"))
    missing = [text for text, empty in (("group name", not d["moodle_group"]), ("members", not d["members"]),
                                        ("submission date", not d["submission_date"]), ("app link", not d["app_url"]),
                                        ("the group's own checks", not d["group_checks"]),
                                        ("other AI tools used (or \"none\")", not d["other_ai_tools"])) if empty]
    return d, missing


def sensitivity_rows(k, v):
    rows = [{"label": label, "base": key is None, "ret": k["ret_s" if key is None else key],
             "diff": ("+" + k["lead_pp"]) if key is None else k[key + "_vs_spy"],
             "value": v["lead_pp"] if key is None else v[key + "_vs_spy"]} for label, key in SENSITIVITIES]
    top = max(r["value"] for r in rows)                       # the bars share one scale; the axis sits at 28% of the cell
    for r in rows:
        r["pos"] = round(max(r["value"], 0.0) / top * 100, 1)
        r["neg"] = round(min(max(-r["value"], 0.0) / (top * 28 / 72) * 100, 100), 1)
    return rows


def calendar_years(k):
    """The rows of the calendar-year table: every year the notebook reports, in order."""
    found = sorted(int(m.group(1)) for key in k if (m := re.fullmatch(r"yr(\d{4})_s", key)))
    return [{"year": y, "s": k[f"yr{y}_s"], "spy": k[f"yr{y}_spy"]} for y in found]


def find_browser(explicit=None):
    candidates = [explicit, os.environ.get("CHROME_PATH"),
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  shutil.which("google-chrome"), shutil.which("google-chrome-stable"), shutil.which("chromium"),
                  shutil.which("chromium-browser"), shutil.which("chrome"), shutil.which("msedge"),
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    raise SystemExit("No Chromium-based browser found. Install Google Chrome, or pass --chrome /path/to/browser. "
                     "The HTML page was written and can also be printed to PDF by hand (A4, no margins, background graphics on).")


def run_browser(browser, args, timeout=180):
    with tempfile.TemporaryDirectory() as profile:
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars", f"--user-data-dir={profile}",
               "--virtual-time-budget=6000"] + args
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def page_count(pdf):
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf)).pages)
    except ImportError:
        data = pdf.read_bytes()
        return len(re.findall(rb"/Type\s*/Page(?![s\w])", data))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--outputs", default=str(ROOT / "outputs"), help="the notebook's output folder (default: outputs)")
    ap.add_argument("--pdf", default=str(ROOT / "investor_prospectus.pdf"), help="where to write the PDF")
    ap.add_argument("--chrome", default=None, help="path of a Chromium-based browser")
    ap.add_argument("--html-only", action="store_true", help="write the HTML page and stop")
    ap.add_argument("--submission", action="store_true",
                    help="the copy for Moodle: with the student numbers of details.local.toml, written to submission/")
    ap.add_argument("--layout-work", action="store_true", help="print the PDF even if a page overflows (never for the final file)")
    args = ap.parse_args()
    outputs = Path(args.outputs)

    k, v = load_key_figures(outputs / "tables" / "tab_prospectus_key_figures.csv")
    n_claims = check_claims(k, v)
    d, missing = load_details(with_student_numbers=args.submission)
    if args.submission and args.pdf == str(ROOT / "investor_prospectus.pdf"):
        args.pdf = str(ROOT / "submission" / "investor_prospectus.pdf")       # never over the public copy
        Path(args.pdf).parent.mkdir(exist_ok=True)
    top = v["top1_weight"]
    top10 = [{"name": k[f"top{i}_name"], "weight": k[f"top{i}_weight"], "width": round(v[f"top{i}_weight"] / top * 100, 1)}
             for i in range(1, 11)]
    shot = HERE / "app_screenshot.png"
    screenshot = ("data:image/png;base64," + base64.b64encode(shot.read_bytes()).decode("ascii")) if shot.exists() else ""

    sens = sensitivity_rows(k, v)
    half = (len(sens) + 1) // 2
    env = Environment(loader=FileSystemLoader(str(HERE)), undefined=StrictUndefined, autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    html = env.get_template("template.html").render(
        k=k, d=d, draft=bool(missing), missing=missing, top10=top10, sens_halves=(sens[:half], sens[half:]), years=calendar_years(k),
        screenshot=screenshot,
        fig={name: inline_svg(outputs / "prospectus" / f"{stem}.svg", name, FIGURE_TEXT[name]) for name, stem in FIGURES.items()},
        css=Markup((HERE / "style.css").read_text(encoding="utf-8")), fonts_css=fonts_css())
    build = HERE / "build"
    build.mkdir(exist_ok=True)
    page = build / ("investor_prospectus_submission.html" if args.submission else "investor_prospectus.html")
    page.write_text(html, encoding="utf-8")
    print(f"key figures: {len(k)} | statements checked against them: {n_claims} | page written: {page.relative_to(ROOT)}")
    if args.html_only:
        return

    browser = find_browser(args.chrome)
    dom = run_browser(browser, ["--dump-dom", page.as_uri()]).stdout
    found = re.search(r'<pre id="layout-report"[^>]*>(.*?)</pre>', dom, flags=re.S)
    if not found:
        raise SystemExit("The browser returned no layout report; the page did not finish loading.")
    report = json.loads(found.group(1).replace("&quot;", '"'))
    for p in report["pages"]:
        print(f"  page {p['page']}: {'OVERFLOW' if p['overflow'] else 'fits'}, {p['free_mm']:.1f} mm free below the last block")
    if not report["inter"]:
        raise SystemExit("The typeface Inter was not loaded by the browser.")
    over = [p["page"] for p in report["pages"] if p["overflow"]]
    if over and not args.layout_work:
        raise SystemExit(f"Content does not fit on page(s) {', '.join(over)}: shorten the text or the layout. No PDF written.")

    pdf = Path(args.pdf)
    result = run_browser(browser, ["--no-pdf-header-footer", f"--print-to-pdf={pdf}", page.as_uri()])
    if not pdf.exists():
        raise SystemExit("The browser did not write a PDF:\n" + result.stderr[-2000:])
    pages = page_count(pdf)
    if pages != CONTENT_PAGES + 1:
        raise SystemExit(f"The PDF has {pages} pages; expected a cover and {CONTENT_PAGES} content pages.")
    print(f"written: {pdf.relative_to(ROOT) if pdf.is_relative_to(ROOT) else pdf} | cover + {CONTENT_PAGES} content pages | {pdf.stat().st_size / 1e6:.2f} MB")
    print("status: " + ("DRAFT, still to be completed in prospectus/details.toml: " + ", ".join(missing) if missing else "complete"))


if __name__ == "__main__":
    sys.exit(main())
