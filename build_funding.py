#!/usr/bin/env python3
"""Build NSF funding time series for poverty/inequality research.

Fetches awards matching configurable keywords from the NSF Awards API
(https://www.research.gov/common/webapi/awardapisearch-v1.htm),
deduplicates across keywords, groups by start-date year, sums obligated
funds, applies CPI adjustment to constant 2023 dollars, and writes both
a clean JSON file and a JS file that the static page can load directly
(no server required, works on file:// URLs).

Usage
-----
    python build_funding.py                       # default: 1990 -> current year
    python build_funding.py --start 2000 --end 2024
    python build_funding.py --keywords poverty inequality "income inequality"
    python build_funding.py --no-cache            # ignore cache, re-fetch
    python build_funding.py --quick               # 2015 -> current only

Output
------
    data/funding.json   structured data + per-year top awards
    data/funding.js     same data exposed as window.NSF_FUNDING
    data/_cache/*.json  per (keyword, year) raw API responses

Notes
-----
* Pure standard library (no pip install).
* NSF Awards API caps results at offset 3000 per query. Splitting the
  query by year (and by keyword) keeps every slice well below that.
* Records-per-page is 25; we paginate until a short page or the cap.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
import urllib.error
import urllib.request

API = "https://api.nsf.gov/services/v1/awards.json"
DEFAULT_KEYWORDS = ["poverty", "inequality"]
PRINT_FIELDS = "id,fundsObligatedAmt,startDate,title,agency,awardeeName,piFirstName,piLastName"
RPP = 25                # NSF API max per page
MAX_OFFSET = 3000       # NSF API hard cap
USER_AGENT = "Econ30-KnowledgeBase/1.0 (educational)"

# CPI-U annual averages (1982-84 = 100). Source: BLS.
# Used to deflate nominal NSF dollars to constant 2023 USD.
CPI_U = {
    1990: 130.7, 1991: 136.2, 1992: 140.3, 1993: 144.5, 1994: 148.2,
    1995: 152.4, 1996: 156.9, 1997: 160.5, 1998: 163.0, 1999: 166.6,
    2000: 172.2, 2001: 177.1, 2002: 179.9, 2003: 184.0, 2004: 188.9,
    2005: 195.3, 2006: 201.6, 2007: 207.342, 2008: 215.303, 2009: 214.537,
    2010: 218.056, 2011: 224.939, 2012: 229.594, 2013: 232.957, 2014: 236.736,
    2015: 237.017, 2016: 240.007, 2017: 245.120, 2018: 251.107, 2019: 255.657,
    2020: 258.811, 2021: 270.970, 2022: 292.655, 2023: 304.702, 2024: 313.689,
    2025: 320.000,  # provisional estimate
}
CPI_BASE_YEAR = 2023


def http_get_json(url: str, retries: int = 5, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            wait = 2 ** attempt
            print(f"  ! retry {attempt + 1}/{retries} after {wait}s ({e})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed after {retries} retries: {url}")


def fetch_awards(keyword: str, year: int) -> list[dict]:
    """Fetch all NSF awards matching keyword whose startDate falls in `year`."""
    awards: list[dict] = []
    offset = 1
    while offset <= MAX_OFFSET:
        params = {
            "keyword": keyword,
            "dateStart": f"01/01/{year}",
            "dateEnd":   f"12/31/{year}",
            "offset":    offset,
            "rpp":       RPP,
            "printFields": PRINT_FIELDS,
        }
        url = f"{API}?{urlencode(params)}"
        data = http_get_json(url)
        page = data.get("response", {}).get("award", []) or []
        awards.extend(page)
        if len(page) < RPP:
            break
        offset += RPP
        time.sleep(0.1)
    return awards


def parse_amount(raw) -> float:
    if raw in (None, ""):
        return 0.0
    try:
        return float(str(raw).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def cpi_factor(year: int) -> float:
    """Return multiplier to convert nominal $year to constant CPI_BASE_YEAR $."""
    if year not in CPI_U:
        # extrapolate linearly using last two known years
        years = sorted(CPI_U)
        last, second_last = years[-1], years[-2]
        delta = CPI_U[last] - CPI_U[second_last]
        cpi_y = CPI_U[last] + delta * (year - last)
    else:
        cpi_y = CPI_U[year]
    return CPI_U[CPI_BASE_YEAR] / cpi_y


def load_cache(cache_dir: Path, keyword: str, year: int) -> list[dict] | None:
    fp = cache_dir / f"{keyword.replace(' ', '_')}_{year}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def save_cache(cache_dir: Path, keyword: str, year: int, awards: list[dict]) -> None:
    fp = cache_dir / f"{keyword.replace(' ', '_')}_{year}.json"
    fp.write_text(json.dumps(awards), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=1990, help="start year (default 1990)")
    ap.add_argument("--end",   type=int, default=datetime.now().year, help="end year (default current year)")
    ap.add_argument("--keywords", nargs="+", default=DEFAULT_KEYWORDS, help="search keywords (OR'd, dedup'd)")
    ap.add_argument("--output", default="data/funding.json", help="JSON output path")
    ap.add_argument("--js-output", default="data/funding.js", help="JS output path")
    ap.add_argument("--cache-dir", default="data/_cache", help="cache directory")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached results and re-fetch")
    ap.add_argument("--quick", action="store_true", help="shortcut for --start 2015")
    args = ap.parse_args()

    if args.quick:
        args.start = max(args.start, 2015)

    out_json = Path(args.output)
    out_js   = Path(args.js_output)
    cache_dir = Path(args.cache_dir)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_js.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    years_out: list[dict] = []
    total_awards = 0
    total_nominal = 0.0

    print(f"NSF funding fetch: years {args.start}-{args.end}, keywords={args.keywords}", file=sys.stderr)

    for year in range(args.start, args.end + 1):
        seen: set[str] = set()
        year_awards: list[dict] = []
        from_cache_count = 0

        for kw in args.keywords:
            cached = None if args.no_cache else load_cache(cache_dir, kw, year)
            if cached is not None:
                awards = cached
                from_cache_count += 1
            else:
                print(f"  fetch {kw!r} {year} ...", file=sys.stderr)
                awards = fetch_awards(kw, year)
                save_cache(cache_dir, kw, year, awards)

            for a in awards:
                aid = a.get("id")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                year_awards.append(a)

        nominal = sum(parse_amount(a.get("fundsObligatedAmt")) for a in year_awards)
        real = nominal * cpi_factor(year)

        top = sorted(year_awards, key=lambda a: parse_amount(a.get("fundsObligatedAmt")), reverse=True)[:10]
        top_compact = []
        for a in top:
            amt = parse_amount(a.get("fundsObligatedAmt"))
            if amt <= 0:
                continue
            top_compact.append({
                "id": a.get("id"),
                "title": (a.get("title") or "").strip(),
                "amount": amt,
                "startDate": a.get("startDate"),
                "awardee": (a.get("awardeeName") or "").strip(),
            })

        cache_tag = f" (cache {from_cache_count}/{len(args.keywords)})" if from_cache_count else ""
        print(f"  {year}: {len(year_awards):4d} awards  nominal=${nominal:>14,.0f}  real23=${real:>14,.0f}{cache_tag}",
              file=sys.stderr)

        years_out.append({
            "year": year,
            "awardCount": len(year_awards),
            "nominalAmount": round(nominal, 2),
            "realAmount2023": round(real, 2),
            "topAwards": top_compact,
        })
        total_awards += len(year_awards)
        total_nominal += nominal

    payload = {
        "meta": {
            "source": "NSF Awards API",
            "keywords": args.keywords,
            "yearRange": [args.start, args.end],
            "cpiBaseYear": CPI_BASE_YEAR,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "totalAwards": total_awards,
            "totalNominal": round(total_nominal, 2),
        },
        "years": years_out,
    }

    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_js.write_text("window.NSF_FUNDING = " + json.dumps(payload) + ";\n", encoding="utf-8")

    print(f"\nwrote {out_json}", file=sys.stderr)
    print(f"wrote {out_js}", file=sys.stderr)
    print(f"total: {total_awards:,} unique awards, ${total_nominal:,.0f} nominal across {len(years_out)} years",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
