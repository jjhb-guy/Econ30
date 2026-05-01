from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover - fallback for environments with PyPDF2
    from PyPDF2 import PdfReader  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "Raw"
OUTPUT_FILE = ROOT / "dashboard" / "data" / "stl-progress.json"

STL_REGION = {"name": "St. Louis region", "lat": 38.6270, "lng": -90.1994}

MONEY_PATTERN = re.compile(
    r"(\$\s*[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:million|billion|m|bn)?)|"
    r"([0-9][0-9,]*(?:\.[0-9]+)?\s*(?:million|billion|m|bn))",
    re.IGNORECASE,
)
JOBS_PATTERN = re.compile(
    r"([0-9][0-9,]*)\s+(?:new\s+)?jobs?",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"(20[0-9]{2})")


@dataclass
class ParsedRecord:
    investment_usd: Optional[int]
    jobs: Optional[int]
    year: Optional[int]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def infer_publisher(filename: str) -> str:
    lower = filename.lower()
    if "department of economic development" in lower:
        return "Missouri Department of Economic Development"
    if "stlpr" in lower:
        return "St. Louis Public Radio"
    if "st. louis american" in lower:
        return "St. Louis American"
    if "st. louis magazine" in lower:
        return "St. Louis Magazine"
    return "Unknown publisher"


def infer_sector(filename: str) -> str:
    lower = filename.lower()
    if "economic development" in lower or "investment" in lower:
        return "Economic Development"
    if "wealth" in lower or "inequality" in lower:
        return "Inequality"
    if "segregation" in lower:
        return "Housing and Segregation"
    if "financial forecast" in lower:
        return "Public Finance"
    if "democracy collaborative" in lower:
        return "Community Development"
    return "Regional Progress"


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages_text: list[str] = []
    for page in reader.pages[:20]:
        pages_text.append(page.extract_text() or "")
    return "\n".join(pages_text)


def parse_money_to_usd(number_text: str, unit: Optional[str]) -> int:
    value = float(number_text.replace(",", ""))
    if unit:
        token = unit.lower()
        if token in {"million", "m"}:
            value *= 1_000_000
        elif token in {"billion", "bn"}:
            value *= 1_000_000_000
    return int(value)


def parse_record(text: str, filename: str) -> ParsedRecord:
    money_match = MONEY_PATTERN.search(text)
    jobs_match = JOBS_PATTERN.search(text)

    year = None
    year_match = YEAR_PATTERN.search(filename)
    if year_match:
        year = int(year_match.group(1))
    else:
        year_match = YEAR_PATTERN.search(text)
        if year_match:
            year = int(year_match.group(1))

    investment_usd = None
    if money_match:
        money_token = money_match.group(0)
        token_match = re.search(
            r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(million|billion|m|bn)?",
            money_token,
            re.IGNORECASE,
        )
        if token_match:
            parsed_usd = parse_money_to_usd(token_match.group(1), token_match.group(2))
            # Filter out likely non-financial values captured from document text.
            if parsed_usd >= 100_000:
                investment_usd = parsed_usd

    jobs = None
    if jobs_match:
        jobs = int(jobs_match.group(1).replace(",", ""))

    return ParsedRecord(investment_usd=investment_usd, jobs=jobs, year=year)


def build_dataset() -> dict:
    sources = []
    projects = []

    pdf_files = sorted(RAW_DIR.glob("*.pdf"))

    for pdf_file in pdf_files:
        source_id = f"src-{slugify(pdf_file.stem)}"
        rel_path = f"../Raw/{pdf_file.name}"
        publisher = infer_publisher(pdf_file.name)
        sector = infer_sector(pdf_file.name)

        text = extract_text(pdf_file)
        parsed = parse_record(text, pdf_file.name)

        sources.append(
            {
                "id": source_id,
                "title": pdf_file.stem.replace("_", " ").strip(),
                "publisher": publisher,
                "path": rel_path,
                "publishedDate": None,
                "extractionConfidence": "medium"
                if (parsed.investment_usd or parsed.jobs)
                else "low",
            }
        )

        if parsed.investment_usd is None and parsed.jobs is None:
            continue

        projects.append(
            {
                "id": f"project-{slugify(pdf_file.stem)}",
                "name": pdf_file.stem.split(" _ ")[0].strip(),
                "sector": sector,
                "year": parsed.year,
                "investmentUsd": parsed.investment_usd or 0,
                "jobs": parsed.jobs or 0,
                "location": STL_REGION,
                "sourceId": source_id,
            }
        )

    return {
        "meta": {
            "title": "St. Louis Progress Dashboard",
            "lastUpdated": date.today().isoformat(),
            "notes": "Auto-generated from all PDF files in Raw via dashboard/scripts/build_data.py",
            "sourceCount": len(sources),
            "projectCount": len(projects),
        },
        "sources": sources,
        "projects": projects,
    }


def main() -> None:
    if not RAW_DIR.exists():
        raise FileNotFoundError(f"Raw directory not found: {RAW_DIR}")

    dataset = build_dataset()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"Built dataset with {dataset['meta']['sourceCount']} sources and {dataset['meta']['projectCount']} projects")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
