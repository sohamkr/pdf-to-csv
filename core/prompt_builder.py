BASE_PROMPT = """
You are extracting structured billing table data from an invoice image.

Return a strictly valid JSON array.

Each object in the array represents exactly ONE visible table row.

Required fields per row:
- start_date
- end_date
- destination
- rate
- minutes
- amount

==============================
CRITICAL EXTRACTION RULES
==============================

1. ROW DETECTION RULE
- Every visible line that begins with a start_date AND end_date is a new row.
- If a row spans multiple wrapped lines visually, treat it as ONE row.
- If two consecutive rows share the same destination but have different date ranges, they MUST be separate JSON objects.
- If rate type changes (Rate 1 / Rate 2), they MUST be separate rows.
- Never merge rows under any circumstance.

IMPORTANT MULTI-LINE RULE:

- If a line does NOT begin with a valid Start Date,
  it MUST belong to the previous row.
- Do NOT treat standalone words like:
  "Surcharge"
  "Zone 2"
  "Zone 3"
  as new rows.
- If Destination text wraps onto multiple lines,
  concatenate all wrapped lines into a single destination string
  BEFORE extracting values.

SPECIAL WRAP CASE:

If destination text breaks after a comma, such as:

"UK,Geographic,Non"
"Surcharge"

These lines MUST be merged into:

"UK,Geographic,Non Surcharge"

before creating the JSON row.

Never drop wrapped fragments.
Never treat wrapped fragments as separate rows.



2. DO NOT GROUP
- Do NOT group rows by destination.
- Do NOT combine rows even if:
  - Destination text is identical
  - Dates partially overlap
  - Amounts look related
  - One row is negative and one is positive

3. DESTINATION HANDLING
- Preserve destination text exactly as displayed.
- Do not remove prefixes like:
  - "Grace Period -"
  - "Commitment Shortfall -"
- Preserve capitalization exactly.
- Do not normalize wording.
- Do not add or remove spaces.
- Do not modify punctuation.

4. NUMERIC RULES (CRITICAL)

- Remove thousand separators (commas).
- Preserve numeric precision exactly as shown.
- Do NOT round values.
- Do NOT recalculate amounts.
- Keep negative signs if present.

VERY IMPORTANT:
- Carefully verify each digit of every numeric value.
- Double-check that each digit matches the image visually.
- Pay special attention to:
  - 0 vs 8
  - 3 vs 8
  - 6 vs 8
  - 1 vs 7
- After extracting all rows, re-check every numeric value against the image before returning.
- Do not guess or approximate any number.

5. EXCLUSION RULES (STRICT)

EXCLUDE rows ONLY if they explicitly contain:
- "Subtotal"
- "Total Charges"
- "Tax"
- "Service:"
- Repeated column headers

DO NOT exclude rows based on:
- Large minute values
- Large amount values
- Being near the end of the table
- Destination wording patterns

6. COMPLETENESS CHECK
- Count the number of visible data rows on the page.
- Your JSON array length MUST equal that count.
- If any row is missing, re-check before returning.

7. OUTPUT FORMAT
- Return ONLY a valid JSON array.
- Do not include markdown.
- Do not include explanation text.
"""

def build_prompt(vendor_rules):
    return BASE_PROMPT + "\n\n" + vendor_rules