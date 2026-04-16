"""
Financial Statement Parser

YOUR TASK: Implement the parse_financial_statement function below.

Given a path to a PDF containing Finnish financial statements,
extract the target variables and return a list of FinancialStatement objects.

Some PDFs contain data for multiple fiscal years - return one object per year.

You may:
- Use the provided pdf_reader module or implement your own extraction
- Add helper functions, classes, or modules as needed
- Use any approach you think is appropriate

Run tests with: docker compose run test
"""

from pathlib import Path
import re
from typing import Optional

from src.schema import FinancialStatement
from src.pdf_reader import extract_pdf


YEAR_RE = re.compile(r"\b(20\d{2})\b")
NUMBER_RE = re.compile(r"\(?-?\d[\d\s.]*(?:,\d+)?\)?-?")

FIELD_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "revenue": [
        re.compile(r"\bliikevaihto\b"),
    ],
    "operating_profit": [
        re.compile(r"\bliikevoitto\b"),
        re.compile(r"\bliiketulos\b"),
        re.compile(r"\bliiketoiminnan tulos\b"),
    ],
    "profit_before_taxes": [
        re.compile(r"\bvoitto ennen veroja\b"),
        re.compile(r"\btulos ennen veroja\b"),
        re.compile(r"\btulos ennen tilinpaatossiirtoja ja veroja\b"),
        re.compile(r"\bvoitto tappio ennen veroja\b"),
    ],
    "net_profit": [
        re.compile(r"\btilikauden voitto\b"),
        re.compile(r"\btilikauden tulos\b"),
    ],
    "fixed_assets": [
        re.compile(r"\bpysyvat vastaavat\b"),
    ],
    "current_assets": [
        re.compile(r"\bvaihtuvat vastaavat\b"),
    ],
    "total_assets": [
        re.compile(r"\bvastaavaa yhteensa\b"),
        re.compile(r"\baktiva yhteensa\b"),
    ],
    "equity": [
        re.compile(r"\boma paaoma\b"),
    ],
    "liabilities": [
        re.compile(r"\bvieras paaoma\b"),
    ],
    "total_equity_and_liabilities": [
        re.compile(r"\bvastattavaa yhteensa\b"),
        re.compile(r"\bpassiva yhteensa\b"),
    ],
}

FIELD_GROUP: dict[str, str] = {
    "revenue": "income",
    "operating_profit": "income",
    "profit_before_taxes": "income",
    "net_profit": "income",
    "fixed_assets": "balance",
    "current_assets": "balance",
    "total_assets": "balance",
    "equity": "balance",
    "liabilities": "balance",
    "total_equity_and_liabilities": "balance",
}

EXCLUDED_YEAR_HINTS = ("budjet", "budget", "ennuste", "forecast")


def _normalize(text: str) -> str:
    cleaned = text.lower()
    cleaned = cleaned.replace("ä", "a").replace("ö", "o").replace("å", "a")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_number(token: str) -> Optional[float]:
    token = token.strip()
    if not token:
        return None

    negative = False
    if token.startswith("(") and token.endswith(")"):
        negative = True
        token = token[1:-1]

    if token.endswith("-"):
        negative = True
        token = token[:-1]

    token = token.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        value = float(token)
    except ValueError:
        return None

    if negative:
        value = -abs(value)
    return value


def _extract_number_from_cell(cell: str) -> Optional[float]:
    matches = NUMBER_RE.findall(cell)
    if not matches:
        return None

    # Last token is typically the actual value in mixed-content cells.
    for raw in reversed(matches):
        value = _parse_number(raw)
        if value is not None:
            return value
    return None


def _extract_numbers_from_text(text: str) -> list[float]:
    values: list[float] = []
    for raw in NUMBER_RE.findall(text):
        parsed = _parse_number(raw)
        if parsed is not None:
            values.append(parsed)
    return values


def _detect_scale(text: str) -> int:
    normalized = _normalize(text)
    if (
        re.search(r"\b1\s*000\s*(euroa|eur|€)\b", normalized)
        or "tuhansina euroina" in normalized
        or "tuhat euroa" in normalized
    ):
        return 1000
    return 1


def _detect_section(line: str, current: Optional[str]) -> Optional[str]:
    nline = _normalize(line)
    if any(key in nline for key in ("tuloslaskelma", "resultatrakning")):
        return "income"
    if any(key in nline for key in ("tase", "aktiva", "passiva", "balansrakning")):
        return "balance"
    if any(key in nline for key in ("rahoituslaskelma", "tunnusluvut", "liitetiedot")):
        return None
    return current


def _year_columns(columns: list[str]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for idx, cell in enumerate(columns):
        ncell = _normalize(cell)
        if any(hint in ncell for hint in EXCLUDED_YEAR_HINTS):
            continue
        years = YEAR_RE.findall(cell)
        if len(years) == 1:
            mapping[idx] = int(years[0])
    return mapping


def _match_field(label: str, section: Optional[str]) -> Optional[str]:
    normalized = _normalize(label)
    if not normalized:
        return None

    for field, patterns in FIELD_PATTERNS.items():
        if section is not None and FIELD_GROUP[field] != section:
            continue
        for pattern in patterns:
            if pattern.search(normalized):
                return field
    return None


def parse_financial_statement(pdf_path: str | Path) -> list[FinancialStatement]:
    """
    Parse a Finnish financial statement PDF and extract key metrics.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of FinancialStatement objects, one per fiscal year found in the PDF.
        Most PDFs have one year, but some have multiple (e.g., current + previous).

    Example:
        >>> results = parse_financial_statement("pdfs/test_01.pdf")
        >>> for stmt in results:
        ...     print(f"{stmt.fiscal_year}: revenue={stmt.revenue}")
    """
    doc = extract_pdf(pdf_path)
    text = doc.text or ""
    lines = text.splitlines()

    scale = _detect_scale(text)
    all_years = sorted({int(year) for year in YEAR_RE.findall(text)}, reverse=True)
    primary_year = all_years[0] if all_years else 0

    current_section: Optional[str] = None
    current_year_columns: dict[int, int] = {}
    current_year_sequence: list[int] = []
    discovered_table_years: set[int] = set()
    data_by_year: dict[int, dict[str, float]] = {}

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        current_section = _detect_section(line, current_section)
        if current_section is None:
            continue

        line_years = YEAR_RE.findall(line)
        if len(line_years) >= 2:
            dedup: list[int] = []
            for year in line_years:
                year_int = int(year)
                if year_int not in dedup:
                    dedup.append(year_int)
            if len(dedup) >= 2:
                current_year_sequence = dedup

        columns = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]

        if len(columns) >= 2:
            year_map = _year_columns(columns)
            if year_map:
                unique_years = sorted(set(year_map.values()), reverse=True)
                if len(unique_years) >= 2:
                    if 0 in year_map and len(year_map) == len(columns):
                        year_map = {idx + 1: year for idx, year in year_map.items()}
                    current_year_columns = year_map
                    discovered_table_years.update(unique_years)

        label_for_match = columns[0] if columns else line
        field = _match_field(label_for_match, current_section)
        if not field:
            continue

        values_by_col: dict[int, float] = {}
        if len(columns) >= 2:
            for col_idx in range(1, len(columns)):
                number = _extract_number_from_cell(columns[col_idx])
                if number is not None:
                    values_by_col[col_idx] = number

        if not values_by_col and len(columns) < 2:
            row_numbers = _extract_numbers_from_text(line)
            if current_year_columns and row_numbers:
                ordered_year_cols = sorted(current_year_columns.items())
                ordered_years = [year for _, year in ordered_year_cols]
                if len(row_numbers) >= len(ordered_years):
                    aligned = row_numbers[-len(ordered_years):]
                    for year, value in zip(ordered_years, aligned):
                        data_by_year.setdefault(year, {})[field] = value * scale
                    continue
            if row_numbers:
                fallback_years = sorted(discovered_table_years, reverse=True)
                if not fallback_years and current_year_sequence:
                    fallback_years = current_year_sequence
                if not fallback_years and primary_year:
                    fallback_years = [primary_year]
                aligned = row_numbers[-len(fallback_years):] if fallback_years else []
                for year, value in zip(fallback_years, aligned):
                    data_by_year.setdefault(year, {})[field] = value * scale
            continue

        if not values_by_col:
            continue

        assigned = False
        for col_idx, value in values_by_col.items():
            year = current_year_columns.get(col_idx)
            if year is None:
                continue
            data_by_year.setdefault(year, {})[field] = value * scale
            assigned = True

        if assigned:
            ordered_year_cols = sorted(current_year_columns.items())
            ordered_years = [year for _, year in ordered_year_cols]
            row_numbers = _extract_numbers_from_text(" ".join(columns[1:]))
            if ordered_years and len(row_numbers) >= len(ordered_years):
                aligned = row_numbers[-len(ordered_years):]
                for year, value in zip(ordered_years, aligned):
                    data_by_year.setdefault(year, {})[field] = value * scale
            continue

        # Fallback: if year columns are not clear, map from left-to-right
        # to descending known fiscal years from table headers.
        fallback_years = sorted(discovered_table_years, reverse=True)
        if not fallback_years and current_year_sequence:
            fallback_years = current_year_sequence
        if not fallback_years and primary_year:
            fallback_years = [primary_year]

        target_years = fallback_years[: len(values_by_col)]
        if not target_years:
            continue
        ordered_values = [values_by_col[idx] for idx in sorted(values_by_col)]
        aligned_values = ordered_values[-len(target_years):]
        for year, value in zip(target_years, aligned_values):
            data_by_year.setdefault(year, {})[field] = value * scale

    results: list[FinancialStatement] = []
    for year in sorted(data_by_year.keys(), reverse=True):
        values = data_by_year[year]
        results.append(
            FinancialStatement(
                fiscal_year=year,
                revenue=values.get("revenue"),
                operating_profit=values.get("operating_profit"),
                profit_before_taxes=values.get("profit_before_taxes"),
                net_profit=values.get("net_profit"),
                fixed_assets=values.get("fixed_assets"),
                current_assets=values.get("current_assets"),
                total_assets=values.get("total_assets"),
                equity=values.get("equity"),
                liabilities=values.get("liabilities"),
                total_equity_and_liabilities=values.get("total_equity_and_liabilities"),
            )
        )

    return results


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.parser <pdf_path>")
        sys.exit(1)

    results = parse_financial_statement(sys.argv[1])
    print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
