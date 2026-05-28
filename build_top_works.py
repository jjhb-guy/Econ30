#!/usr/bin/env python3
"""Top-cited OpenAlex works on poverty/inequality, broken out by era.

For each 5-year era we fetch the top-N most-cited works tagged
poverty (C189326681) or economic inequality (C513380476), separately
for journal articles and books/book-chapters. Output goes to
data/top_works.js and is consumed by the website's Ngram section so
the reader can ask: "which actual papers and books were dominating
this era?"

Usage:
    python build_top_works.py
    python build_top_works.py --top 8 --quick
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
# Keep results inside disciplines that actually study poverty/inequality
# (econ, sociology, political science, public policy/development economics).
FIELD_CONCEPTS = "C162324750|C144024400|C17744445|C47768531"

ERAS = [
    (1970, 1974), (1975, 1979), (1980, 1984), (1985, 1989),
    (1990, 1994), (1995, 1999), (2000, 2004), (2005, 2009),
    (2010, 2014), (2015, 2019), (2020, 2024),
]

# OpenAlex `type` values:
#   article (journal article), book, book-chapter, dataset, review, ...
BUCKETS = [
    ("articles", "article|review", "Top journal articles / reviews"),
    ("books",    "book|book-chapter", "Top books / book chapters"),
]

SELECT = ",".join([
    "id", "doi", "display_name", "publication_year", "cited_by_count",
    "type", "authorships", "primary_topic", "primary_location",
])


def fetch(filt: str, sort: str, per_page: int) -> list[dict]:
    url = (
        f"{API}?filter={urllib.parse.quote(filt, safe='=:,|<>-')}"
        f"&sort={sort}&per-page={per_page}"
        f"&select={SELECT}&{POLITE}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Econ30-KnowledgeBase/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8")).get("results", [])
        except Exception as e:
            wait = 1.5 ** attempt
            print(f"    retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed: {filt}")


def shrink(w: dict) -> dict:
    auths = []
    for a in (w.get("authorships") or [])[:4]:
        name = (a.get("author") or {}).get("display_name") or ""
        if name:
            auths.append(name)
    venue = ""
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    venue = src.get("display_name") or ""
    topic = (w.get("primary_topic") or {}).get("display_name") or ""
    return {
        "id": (w.get("id") or "").replace("https://openalex.org/", ""),
        "doi": w.get("doi") or "",
        "title": w.get("display_name") or "",
        "year": w.get("publication_year"),
        "cites": w.get("cited_by_count") or 0,
        "type": w.get("type") or "",
        "authors": auths,
        "venue": venue,
        "topic": topic,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=8, help="works per bucket per era")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--output", default="data/top_works.js")
    ap.add_argument("--cache-dir", default="data/_cache/top_works")
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
            print(f"  {label} (cache)", file=sys.stderr)
            continue

        buckets: dict[str, dict] = {}
        for key, types_str, _label in BUCKETS:
            filt = (
                f"concepts.id:{POVERTY_CONCEPTS},"
                f"concepts.id:{FIELD_CONCEPTS},"
                f"type:{types_str},"
                f"from_publication_date:{start}-01-01,"
                f"to_publication_date:{end}-12-31,"
                f"cited_by_count:>0"
            )
            works = fetch(filt, "cited_by_count:desc", args.top)
            buckets[key] = [shrink(w) for w in works]
            time.sleep(0.12)
            top = buckets[key][0] if buckets[key] else None
            if top:
                print(f"  {label} {key:9s} top: ({top['cites']} cites) {top['title'][:60]}", file=sys.stderr)

        era_data = {"label": label, "start": start, "end": end, "buckets": buckets}
        cache_fp.write_text(json.dumps(era_data), encoding="utf-8")
        era_rows.append(era_data)

    payload = {
        "meta": {
            "source": "OpenAlex Works API · sort by cited_by_count desc",
            "filter": (
                f"concepts.id:{POVERTY_CONCEPTS} (poverty | economic inequality), "
                f"split by type (articles vs books)"
            ),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "perBucket": args.top,
            "buckets": [(b[0], b[2]) for b in BUCKETS],
        },
        "eras": era_rows,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.TOP_WORKS = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
