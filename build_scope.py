#!/usr/bin/env python3
"""Estimate US-focused vs global/development poverty research by era (OpenAlex).

For each 5-year window, counts cited econ+sociology poverty/inequality papers and
the share that are:
  * US-affiliated (any author at a US institution)
  * US-named in abstract ("United States")
  * Development economics (also tagged OpenAlex concept C47768531)
  * Global keywords in abstract (developing countries, cross-country, etc.)

Usage:
    python build_scope.py
    python build_scope.py --quick
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
DEV_ECON = "C47768531"

ERAS = [
    (1970, 1974), (1975, 1979), (1980, 1984), (1985, 1989),
    (1990, 1994), (1995, 1999), (2000, 2004), (2005, 2009),
    (2010, 2014), (2015, 2019), (2020, 2024),
]

SCOPES = [
    ("usAffiliation", "authorships.institutions.country_code:us", "US-affiliated"),
    ("usText", 'title_and_abstract.search:"United States"', "US named in abstract"),
    ("developmentEcon", f"concepts.id:{DEV_ECON}", "Development economics co-tag"),
    (
        "globalKeywords",
        "title_and_abstract.search:developing|cross-country|global poverty|Sub-Saharan",
        "Global keywords in abstract",
    ),
]


def fetch_count(filter_str: str) -> int:
    url = f"{API}?filter={urllib.parse.quote(filter_str)}&per-page=1&{POLITE}"
    req = urllib.request.Request(url, headers={"User-Agent": "Econ30-KnowledgeBase/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return int(data.get("meta", {}).get("count", 0))
        except Exception as e:
            wait = 2 ** attempt
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed: {filter_str}")


def era_base(start: int, end: int, min_cites: int) -> str:
    return ",".join([
        f"concepts.id:{POVERTY_CONCEPTS}",
        f"concepts.id:{FIELD_CONCEPTS}",
        f"cited_by_count:>{min_cites}",
        f"from_publication_date:{start}-01-01",
        f"to_publication_date:{end}-12-31",
    ])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-cites", type=int, default=25)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--output", default="data/scope.js")
    ap.add_argument("--cache-dir", default="data/_cache/scope")
    args = ap.parse_args()

    eras = [e for e in ERAS if e[0] >= 2000] if args.quick else ERAS
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for start, end in eras:
        label = f"{start}\u2013{end % 100:02d}" if end >= 2000 else f"{start}\u2013{end}"
        base = era_base(start, end, args.min_cites)
        cache_fp = cache_dir / f"{start}_{end}.json"

        if cache_fp.exists():
            row = json.loads(cache_fp.read_text(encoding="utf-8"))
            print(f"  {label} (cache)", file=sys.stderr)
        else:
            print(f"  fetch {label} ...", file=sys.stderr)
            total = fetch_count(base)
            scopes = {}
            for key, extra, _label in SCOPES:
                count = fetch_count(f"{base},{extra}")
                scopes[key] = {
                    "count": count,
                    "share": round(100 * count / total, 2) if total else 0,
                }
                time.sleep(0.12)
            row = {"label": label, "start": start, "end": end, "total": total, "scopes": scopes}
            cache_fp.write_text(json.dumps(row), encoding="utf-8")
            time.sleep(0.12)

        rows.append(row)

    payload = {
        "meta": {
            "source": "OpenAlex",
            "filter": (
                f"poverty/inequality in econ+sociology, >{args.min_cites} cites; "
                "scope buckets are overlapping, not mutually exclusive"
            ),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "scopes": [{"key": k, "label": lbl} for k, _, lbl in SCOPES],
        },
        "eras": rows,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.SCOPE_DATA = " + json.dumps(payload) + ";\n", encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
