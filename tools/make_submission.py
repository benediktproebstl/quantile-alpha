"""Write the two files that are submitted on Moodle, with the members' student numbers, into submission/.

    python tools/make_submission.py

This repository is public, so the notebook and the prospectus in it name the group members without their student
numbers. The numbers are kept in prospectus/details.local.toml, a file git ignores. This script

* builds the prospectus once more with the numbers on the cover     -> submission/investor_prospectus.pdf
* copies the executed notebook and adds the numbers to the table at
  its top; nothing else in the notebook is touched                  -> submission/Financial_Modeling_Quantile_Alpha.ipynb

The folder submission/ is ignored by git as well.
"""
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = "Financial_Modeling_Quantile_Alpha.ipynb"
LIMIT_MB = 50                                    # the brief: two files, smaller than 50 MB in total


def main():
    local = ROOT / "prospectus" / "details.local.toml"
    if not local.exists():
        raise SystemExit("prospectus/details.local.toml is missing: it holds the student numbers.")
    numbers = tomllib.loads(local.read_text(encoding="utf-8")).get("student_numbers", {})
    members = tomllib.loads((ROOT / "prospectus" / "details.toml").read_text(encoding="utf-8")).get("members", [])
    names = [m if isinstance(m, str) else m.get("name", "") for m in members]
    without = [n for n in names if n not in numbers]
    if without:
        raise SystemExit("No student number in details.local.toml for: " + ", ".join(without))

    out = ROOT / "submission"
    out.mkdir(exist_ok=True)
    result = subprocess.run([sys.executable, str(ROOT / "prospectus" / "build_prospectus.py"), "--submission"])
    if result.returncode:
        raise SystemExit("The prospectus was not built.")

    nb = json.loads((ROOT / NOTEBOOK).read_text(encoding="utf-8"))
    public_row = "| Group members | " + ", ".join(names) + " |"
    private_row = "| Group members | " + ", ".join(f"{n} ({numbers[n]})" for n in names) + " |"
    changed = 0
    for cell in nb["cells"]:
        if cell["cell_type"] != "markdown":
            continue
        text = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
        if public_row in text:
            text = text.replace(public_row, private_row)
            cell["source"] = text.splitlines(keepends=True) if not isinstance(cell["source"], str) else text
            changed += 1
    if changed != 1:
        raise SystemExit(f"Expected the members' row once at the top of the notebook, found it {changed} times.")
    (out / NOTEBOOK).write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    sizes = {name: (out / name).stat().st_size / 1e6 for name in ("investor_prospectus.pdf", NOTEBOOK)}
    total = sum(sizes.values())
    for name, mb in sizes.items():
        print(f"submission/{name}: {mb:.2f} MB")
    print(f"together {total:.2f} MB (limit {LIMIT_MB} MB): {'OK' if total < LIMIT_MB else 'TOO LARGE'}")


if __name__ == "__main__":
    main()
