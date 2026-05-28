#!/usr/bin/env python3
"""Build co-occurring topic mix for poverty/inequality research by era.

Queries OpenAlex for cited econ/sociology papers tagged poverty or
inequality, groups by OpenAlex topic, and writes era-level facet shares
to data/topics.js.

Usage:
    python build_topics.py
    python build_topics.py --quick          # 2000-2024 only
    python build_topics.py --top 8 --min-cites 25
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://api.openalex.org/works"
POLITE = "mailto=econ30-knowledge-base@example.com"

POVERTY_CONCEPTS = "C189326681|C513380476"   # poverty | economic inequality (OpenAlex concept IDs)
FIELD_CONCEPTS = "C162324750|C144024400"     # economics | sociology

ERAS = [
    (1970, 1974), (1975, 1979), (1980, 1984), (1985, 1989),
    (1990, 1994), (1995, 1999), (2000, 2004), (2005, 2009),
    (2010, 2014), (2015, 2019), (2020, 2024),
]

EXCLUDE_NAME = re.compile(
    r"poverty|inequal|income distrib|wealth distrib|social stratif|"
    r"economic dispar|welfare|deprivation|impoverish",
    re.I,
)


def fetch_group(filter_str: str) -> list[dict]:
    url = (
        f"{API}?filter={urllib.parse.quote(filter_str)}"
        f"&group_by=topics.id&per-page=200&{POLITE}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Econ30-KnowledgeBase/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("group_by") or []
        except Exception as e:
            wait = 2 ** attempt
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed: {filter_str}")


def clean_name(name: str) -> str:
    return (name or "Unknown").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=8, help="topics per era")
    ap.add_argument("--min-cites", type=int, default=25)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--output", default="data/topics.js")
    ap.add_argument("--cache-dir", default="data/_cache/topics")
    args = ap.parse_args()

    eras = ERAS
    if args.quick:
        eras = [e for e in ERAS if e[0] >= 2000]

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    era_rows = []
    topic_totals: dict[str, int] = {}

    for start, end in eras:
        label = f"{start}\u2013{end % 100:02d}" if end >= 2000 else f"{start}\u2013{end}"
        cache_fp = cache_dir / f"{start}_{end}.json"

        if cache_fp.exists():
            groups = json.loads(cache_fp.read_text(encoding="utf-8"))
            print(f"  {label} (cache)", file=sys.stderr)
        else:
            filt = (
                f"concepts.id:{POVERTY_CONCEPTS},"
                f"concepts.id:{FIELD_CONCEPTS},"
                f"cited_by_count:>{args.min_cites},"
                f"from_publication_date:{start}-01-01,"
                f"to_publication_date:{end}-12-31"
            )
            print(f"  fetch {label} ...", file=sys.stderr)
            groups = fetch_group(filt)
            cache_fp.write_text(json.dumps(groups), encoding="utf-8")
            time.sleep(0.15)

        filtered = []
        for g in groups:
            name = clean_name(g.get("key_display_name", ""))
            if EXCLUDE_NAME.search(name):
                continue
            filtered.append({"id": g.get("key", ""), "name": name, "count": g.get("count", 0)})

        filtered.sort(key=lambda x: x["count"], reverse=True)
        top = filtered[: args.top]
        total_top = sum(t["count"] for t in top) or 1
        era_total = sum(g.get("count", 0) for g in groups) or total_top

        topics = []
        for t in top:
            pct = 100 * t["count"] / era_total
            topics.append({**t, "share": round(pct, 2)})
            topic_totals[t["name"]] = topic_totals.get(t["name"], 0) + t["count"]

        era_rows.append({
            "label": label,
            "start": start,
            "end": end,
            "paperCount": era_total,
            "topics": topics,
        })

    payload = {
        "meta": {
            "source": "OpenAlex",
            "filter": f"poverty (C189326681) or economic inequality (C513380476) in econ+sociology with >{args.min_cites} cites",
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "eras": len(era_rows),
        },
        "eras": era_rows,
        "allTopics": sorted(topic_totals.items(), key=lambda x: -x[1])[:30],
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.TOPIC_DATA = " + json.dumps(payload) + ";\n", encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
