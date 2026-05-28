#!/usr/bin/env python3
"""Build data/ngrams.js from a saved Google Ngram Viewer HTML page.

The Ngram Viewer page embeds the full timeseries JSON inside a
<script id="ngrams-data" type="application/json"> tag, so we don't
have to hit the brittle JSON-API endpoint. This script reads the
saved page, parses that JSON, and writes data/ngrams.js in the same
shape the website expects.

Source page URL is preserved in the meta block so we know exactly
what corpus / smoothing / year-range the data came from.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_SAVED = (
    "Raw/Google Ngram Viewer_ inequality,poverty,innovation,tech,progress.html"
)
DEFAULT_OUTPUT = "data/ngrams.js"


# The saved page header tells us start/end years and corpus.
RE_YEAR_START = re.compile(r"year_start=(\d{4})")
RE_YEAR_END = re.compile(r"year_end=(\d{4})")
RE_CORPUS = re.compile(r"corpus=([a-z0-9_-]+)", re.I)
RE_SMOOTHING = re.compile(r"smoothing=(\d+)")
RE_SOURCE_URL = re.compile(r'saved from url=\(\d+\)(https?://[^"\s]+)')

RE_DATA_SCRIPT = re.compile(
    r'<script id="ngrams-data" type="application/json">(.*?)</script>',
    re.S,
)

# Map a few alternate term spellings to the canonical website keys.
TERM_ALIASES = {
    "tech": "technology",
    "economic growth": "economic_growth",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saved", default=DEFAULT_SAVED, help="saved Ngram Viewer .html")
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    saved = Path(args.saved)
    raw = saved.read_text(encoding="utf-8", errors="replace")

    m = RE_DATA_SCRIPT.search(raw)
    if not m:
        print("Could not find <script id='ngrams-data'> in saved file.", file=sys.stderr)
        return 2
    payload_json = html.unescape(m.group(1).strip())
    series = json.loads(payload_json)

    src_url = (RE_SOURCE_URL.search(raw) or [""])[0]
    year_start = int((RE_YEAR_START.search(raw) or ["", "1800"]).group(1))
    year_end = int((RE_YEAR_END.search(raw) or ["", "2022"]).group(1))
    corpus = (RE_CORPUS.search(raw) or ["", "en"]).group(1)
    smoothing = int((RE_SMOOTHING.search(raw) or ["", "3"]).group(1))

    # Build a {term -> [values per year]} map.
    term_to_values: dict[str, list[float]] = {}
    for s in series:
        if s.get("type") not in (None, "NGRAM"):
            # Skip parented variants like "_PRON_" expansions.
            continue
        term = (s.get("ngram") or "").strip().lower()
        if not term:
            continue
        key = TERM_ALIASES.get(term, term)
        term_to_values[key] = s.get("timeseries") or []

    if not term_to_values:
        print("No NGRAM series in saved payload.", file=sys.stderr)
        return 3

    n_years = max(len(v) for v in term_to_values.values())
    years = list(range(year_start, year_start + n_years))

    by_year = []
    for i, y in enumerate(years):
        row: dict = {"year": y}
        for key, vals in term_to_values.items():
            if i < len(vals):
                row[key] = vals[i]
            else:
                row[key] = 0.0
        # Compute the precomputed "discourse share" so consumers that already
        # use it don't break — but the website no longer surfaces it.
        pi = (row.get("poverty") or 0) + (row.get("inequality") or 0)
        tech_progress = (
            (row.get("technology") or 0)
            + (row.get("tech") or 0)
            + (row.get("progress") or 0)
            + (row.get("innovation") or 0)
        )
        denom = pi + tech_progress
        row["discourseShare"] = (pi / denom * 100) if denom else 0.0
        by_year.append(row)

    payload = {
        "meta": {
            "source": "Google Books Ngrams (saved viewer page)",
            "sourceUrl": src_url,
            "corpus": corpus,
            "smoothing": smoothing,
            "yearRange": [year_start, years[-1] if years else year_end],
            "terms": sorted(term_to_values.keys()),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "note": (
                "Extracted from Raw/Google Ngram Viewer_*.html — the exact "
                "series the user linked, 1800–2022, English corpus, smoothing=3."
            ),
        },
        "years": by_year,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "window.NGRAM_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {out}: {len(by_year)} years × {len(term_to_values)} terms", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
