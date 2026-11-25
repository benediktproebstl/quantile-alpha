"""Export the calculation engine and its tests from the notebook.

The notebook is the single source of truth. Code cells whose first line starts
with ``# [engine]`` are concatenated into ``quantile_alpha/engine.py`` and cells
starting with ``# [tests]`` into ``tests/test_engine.py``, so that the future
Streamlit app and ``pytest`` run exactly the code the notebook runs.

Usage (from the repository root):
    python tools/export_engine.py            # write the two files
    python tools/export_engine.py --check    # exit 1 if they are out of date
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "Financial_Modeling_Quantile_Alpha.ipynb"
TARGETS = {
    "# [engine]": ROOT / "quantile_alpha" / "engine.py",
    "# [tests]": ROOT / "tests" / "test_engine.py",
}
HEADERS = {
    "# [engine]": '"""Quantile Alpha calculation engine.\n\nAUTO-GENERATED from Financial_Modeling_Quantile_Alpha.ipynb by tools/export_engine.py.\nDo not edit by hand: change the notebook cell marked "# [engine]" and re-export.\n"""\n',
    "# [tests]": '"""Engine tests.\n\nAUTO-GENERATED from Financial_Modeling_Quantile_Alpha.ipynb by tools/export_engine.py.\nDo not edit by hand: change the notebook cell marked "# [tests]" and re-export.\n"""\nfrom quantile_alpha.engine import *  # noqa: F401,F403\n',
}


def collect(marker):
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    parts = []
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        src = "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
        if src.lstrip().startswith(marker):
            parts.append(src.rstrip() + "\n")
    return HEADERS[marker] + "\n\n" + "\n\n".join(parts)


def main():
    check = "--check" in sys.argv
    stale = []
    for marker, path in TARGETS.items():
        text = collect(marker)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)} ({len(text.splitlines())} lines)")
    if check:
        if stale:
            print("OUT OF DATE:", ", ".join(stale))
            sys.exit(1)
        print("engine and tests are in sync with the notebook")


if __name__ == "__main__":
    main()
