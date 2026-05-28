#!/usr/bin/env python3
"""Fetch Google Books Ngram frequencies and write data/ngrams.js.

Compares poverty/inequality discourse against tech/progress terms to
measure relative cultural prominence over time.

Usage:
    python build_ngrams.py
    python build_ngrams.py --start 1950 --end 2019
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

NGRAM_URL = "https://books.google.com/ngrams/json"
CORPUS = 1  # English 2019 (general corpus, matches alignment chart)
SMOOTHING = 3

TERM_GROUPS = {
    "poverty_inequality": ["poverty", "inequality"],
    "tech_progress": ["technology", "progress", "innovation"],
}

ALL_TERMS = ["poverty", "inequality", "technology", "progress", "innovation", "economic_growth"]


def fetch_ngrams(terms: list[str], start: int, end: int) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    # Google returns truncated/empty series if too many terms per request
    batch_size = 2
    for i in range(0, len(terms), batch_size):
        batch = terms[i : i + batch_size]
        params = {
            "content": ",".join(batch),
            "year_start": start,
            "year_end": end,
            "corpus": CORPUS,
            "smoothing": SMOOTHING,
        }
        url = f"{NGRAM_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Econ30-KnowledgeBase/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        for row in rows:
            name = row["ngram"].strip()
            out[name] = row["timeseries"]
        if i + batch_size < len(terms):
            time.sleep(0.3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=1950)
    ap.add_argument("--end", type=int, default=2011, help="API often returns zeros after ~2011")
    ap.add_argument("--output", default="data/ngrams.js")
    args = ap.parse_args()

    print(f"Fetching Ngrams {args.start}-{args.end} ...", file=sys.stderr)
    try:
        series = fetch_ngrams(ALL_TERMS, args.start, args.end)
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        return 1

    years = list(range(args.start, args.end + 1))
    by_year = []
    for i, year in enumerate(years):
        row = {"year": year}
        for term in ALL_TERMS:
            if term in series and i < len(series[term]):
                row[term] = series[term][i]
        pi = sum(row.get(t, 0) or 0 for t in TERM_GROUPS["poverty_inequality"])
        tp = sum(row.get(t, 0) or 0 for t in TERM_GROUPS["tech_progress"])
        total = pi + tp
        row["relativeProminence"] = (pi / tp) if tp > 0 else None
        row["discourseShare"] = (100 * pi / total) if total > 0 else None
        by_year.append(row)

    # Google Ngrams JSON API returns 0 for years beyond corpus coverage — trim tail
    while by_year and all((by_year[-1].get(t, 0) or 0) == 0 for t in ALL_TERMS):
        by_year.pop()
    if by_year:
        args.end = by_year[-1]["year"]
        years = [r["year"] for r in by_year]

    payload = {
        "meta": {
            "source": "Google Books Ngrams",
            "corpus": "English 2019 (corpus 1)",
            "smoothing": SMOOTHING,
            "yearRange": [args.start, args.end],
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "terms": ALL_TERMS,
        },
        "years": by_year,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.NGRAM_DATA = " + json.dumps(payload) + ";\n", encoding="utf-8")
    print(f"Wrote {out} ({len(by_year)} years)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
