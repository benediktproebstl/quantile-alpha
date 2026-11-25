"""Take the screenshot of the tracker app that the prospectus shows (prospectus/app_screenshot.png).

    streamlit run tracker_app.py                       # in one terminal
    python tools/app_screenshot.py http://localhost:8501

Needs the package `playwright` and an installed Google Chrome; neither is needed to run the app or the notebook.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main(url, out=ROOT / "prospectus" / "app_screenshot.png", width=900, height=1120):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(".qa-value", timeout=120_000)                 # the headline value is on the page
        page.wait_for_selector(".js-plotly-plot .main-svg", timeout=60_000)   # and the first chart is drawn
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": width, "height": height})
        text = page.inner_text(".qa-hero")
        browser.close()
    print(f"written: {out} | the page shows: {' '.join(text.split())[:120]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501")
