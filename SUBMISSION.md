# Submission

**Name:** Nadja Toroponina
**Email:** not.provided@example.com

## Approach

I implemented `src/parser.py` as a rule-based parser operating on layout-preserved PDF text. The main strategy was to first identify fiscal year columns and then map each financial metric row to the correct year-specific numeric value.

Key decisions:

- Parse line-by-line from `extract_pdf()` output and split rows into columns using preserved spacing.
- Normalize Finnish text for robust matching and support terminology variants across different templates.
- Build explicit pattern mapping for all required variables in income statement and balance sheet.
- Keep parsing section-aware (`tuloslaskelma`, `tase`, `aktiva`, `passiva`) to avoid noise from unrelated sections.
- Implement numeric parsing for Finnish number formats (thousand separators, comma decimals, negative conventions).
- Detect unit scaling (`1 000 euroa`) and convert all extracted values to euros.
- Add fallback handling for rows where values are collapsed or year headers are partially ambiguous.

I validated the parser with the provided tests and refined heuristics until all test cases passed.

## AI Tools

I used Cursor AI assistance to:

- inspect repository files and task requirements,
- implement and iterate parser heuristics,
- run tests repeatedly and debug failing edge cases,
- finalize `SUBMISSION.md`.
