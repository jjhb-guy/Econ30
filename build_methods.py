#!/usr/bin/env python3
"""Build a "research fingerprint" per era for poverty/inequality papers.

For each era we hit OpenAlex once for the baseline count of cited
poverty/inequality papers in econ+sociology, then once per keyword to
count how many of those papers mention the keyword in title or abstract.
The keywords are grouped into three buckets:

  * Data sources  (PSID, CPS, ACS, IRS, administrative data ...)
  * Methods       (RCT, difference-in-differences, regression discontinuity ...)
  * Subjects      (race, gender, mobility, neighborhood, child ...)

Result is written to data/methods.js and consumed by the website to show
"what data + methods + subjects show up in the average paper of each
era" — a quantitative answer to "what is the literature about?"

Usage:
    python build_methods.py
    python build_methods.py --quick           # 1990-2024 only
    python build_methods.py --min-cites 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://api.openalex.org/works"
POLITE = "mailto=econ30-knowledge-base@example.com"

POVERTY_CONCEPTS = "C189326681|C513380476"
FIELD_CONCEPTS = "C162324750|C144024400"

ERAS = [
    (1970, 1974), (1975, 1979), (1980, 1984), (1985, 1989),
    (1990, 1994), (1995, 1999), (2000, 2004), (2005, 2009),
    (2010, 2014), (2015, 2019), (2020, 2024),
]

# Each entry: (display label, query string for title_and_abstract.search)
# Quoted phrases are passed as-is; OpenAlex search treats spaces as AND.
KEYWORDS = {
    "Data sources": [
        ("PSID",                  '"PSID"'),
        ("CPS / Current Pop. Survey", '"Current Population Survey"'),
        ("ACS",                   '"American Community Survey"'),
        ("Decennial Census",      '"decennial census"'),
        ("Tax records / IRS",     '"tax records"'),
        ("Administrative data",   '"administrative data"'),
        ("Survey data",           '"survey data"'),
        ("Longitudinal / panel",  '"panel data"'),
        ("Cross-country",         '"cross-country"'),
    ],
    "Methods": [
        ("Experiment / RCT",      '"randomized"'),
        ("Difference-in-diff.",   '"difference-in-differences"'),
        ("Regression discontinuity", '"regression discontinuity"'),
        ("Instrumental variable", '"instrumental variable"'),
        ("Structural model",      '"structural model"'),
        ("Machine learning",      '"machine learning"'),
        ("Natural experiment",    '"natural experiment"'),
        ("Decomposition",         '"decomposition"'),
        ("Simulation",            '"simulation"'),
    ],
    "Subjects": [
        ("Race",                  '"race"'),
        ("Gender",                '"gender"'),
        ("Immigration",           '"immigration"'),
        ("Education",             '"education"'),
        ("Mobility",              '"mobility"'),
        ("Neighborhood / place",  '"neighborhood"'),
        ("Children",              '"children"'),
        ("Health",                '"health"'),
        ("Wealth",                '"wealth"'),
        ("Tax / transfer",        '"tax"'),
        ("Welfare reform",        '"welfare"'),
        ("Top incomes",           '"top income"'),
    ],
}


def fetch_count(filt: str) -> int:
    url = (
        f"{API}?filter={urllib.parse.quote(filt, safe='=:,|<>-')}"
        f"&per-page=1&{POLITE}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Econ30-KnowledgeBase/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return int(data.get("meta", {}).get("count", 0))
        except Exception as e:
            wait = 1.5 ** attempt
            print(f"    retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed: {filt}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-cites", type=int, default=25)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--output", default="data/methods.js")
    ap.add_argument("--cache-dir", default="data/_cache/methods")
    args = ap.parse_args()

    eras = ERAS
    if args.quick:
        eras = [e for e in ERAS if e[0] >= 1990]

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    era_rows = []

    for start, end in eras:
        label = f"{start}\u2013{end % 100:02d}" if end >= 2000 else f"{start}\u2013{end}"
        cache_fp = cache_dir / f"{start}_{end}.json"

        if cache_fp.exists():
            cached = json.loads(cache_fp.read_text(encoding="utf-8"))
            era_rows.append(cached)
            print(f"  {label} (cache, {cached['total']} papers)", file=sys.stderr)
            continue

        base = (
            f"concepts.id:{POVERTY_CONCEPTS},"
            f"concepts.id:{FIELD_CONCEPTS},"
            f"cited_by_count:>{args.min_cites},"
            f"from_publication_date:{start}-01-01,"
            f"to_publication_date:{end}-12-31"
        )

        print(f"  fetch {label} baseline ...", file=sys.stderr)
        total = fetch_count(base)
        if total == 0:
            print(f"    {label}: 0 papers — skipping", file=sys.stderr)
            era_rows.append({"label": label, "start": start, "end": end, "total": 0, "categories": {}})
            cache_fp.write_text(json.dumps(era_rows[-1]), encoding="utf-8")
            continue

        categories: dict[str, list[dict]] = {}
        for cat, items in KEYWORDS.items():
            cat_rows = []
            for name, query in items:
                filt = base + f",title_and_abstract.search:{query}"
                try:
                    c = fetch_count(filt)
                except Exception as e:
                    print(f"    {name}: ERR {e}", file=sys.stderr)
                    c = 0
                share = round(100 * c / total, 2) if total else 0
                cat_rows.append({"name": name, "count": c, "share": share})
                time.sleep(0.12)
            cat_rows.sort(key=lambda r: -r["share"])
            categories[cat] = cat_rows
            print(f"    {label} {cat:14s} top: {cat_rows[0]['name']} ({cat_rows[0]['share']}%)", file=sys.stderr)

        era_data = {
            "label": label,
            "start": start,
            "end": end,
            "total": total,
            "categories": categories,
        }
        cache_fp.write_text(json.dumps(era_data), encoding="utf-8")
        era_rows.append(era_data)

    payload = {
        "meta": {
            "source": "OpenAlex Works API · title_and_abstract.search",
            "filter": (
                f"concepts.id:{POVERTY_CONCEPTS} (poverty|inequality) "
                f"AND concepts.id:{FIELD_CONCEPTS} (econ|soc), "
                f"cited_by_count:>{args.min_cites}"
            ),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "eras": len(era_rows),
            "categories": list(KEYWORDS.keys()),
        },
        "eras": era_rows,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.METHOD_DATA = " + json.dumps(payload) + ";\n", encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
