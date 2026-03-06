INFO_RULES = r"""
Vendor Format: Info Telecom (IDD Traffic Table)

The table structure is fixed and column-based.

========================================
COLUMN STRUCTURE (STRICT POSITIONAL)
========================================

Column order is strictly:

1. Start Date
2. End Date
3. Origin (IGNORE)
4. Destination/Product
5. Rate Type (IGNORE)
6. Rate
7. Calls (IGNORE)
8. Minutes
9. Amount

Extract ONLY:

- start_date  → column 1
- end_date    → column 2
- destination → column 4
- rate        → column 6
- minutes     → column 8
- amount      → column 9

Ignore columns 3, 5, and 7 completely.

Do NOT infer values.
Do NOT shift columns.
Do NOT guess from alignment.
Only use strict column position.

========================================
ROW CONSTRUCTION ALGORITHM (CRITICAL)
========================================

1. Scan the table from top to bottom.
2. Every time a valid Start Date appears in column 1,
   begin a new row.
3. Continue collecting all text and numeric values
   until the NEXT Start Date appears.
4. Everything between two Start Dates belongs to ONE row.
5. Never stop a row because of section titles,
   large numbers, or visual gaps.

A row ALWAYS begins with a Start Date.
A row NEVER begins without a Start Date.

========================================
MULTI-LINE DESTINATION HANDLING (CRITICAL)
========================================

If Destination/Product text wraps onto multiple lines:

Example:

Line 1:
"Grace Period - UK,Geographic,Non"

Line 2:
"Surcharge"

These lines MUST be merged into:

"Grace Period - UK,Geographic,Non Surcharge"

Rules:
- If a line does NOT begin with a Start Date,
  it belongs to the previous row.
- Standalone words like:
  "Surcharge"
  "Zone 2"
  "Zone 3"
  MUST be merged with the previous destination.
- Never drop wrapped fragments.
- Never treat wrapped fragments as new rows.

========================================
NUMERIC ALIGNMENT RULE (VERY IMPORTANT)
========================================

If numeric columns (Rate, Minutes, Amount)
appear on a line BELOW part of the destination text,
and that line does NOT begin with a new Start Date,

those numeric values belong to the previous Start Date.

Example:

Line 1:
"2025/01/01 2025/01/24 Grace Period - UK,Geographic,Non"

Line 2:
"Surcharge 0.0015 562,473.06 854.96"

These two lines together form ONE row.

Do NOT drop such rows.

========================================
MANDATORY VALID ROWS
========================================

The following are VALID TRAFFIC ROWS and MUST be extracted:

- Rows beginning with "Grace Period -"
- Rows beginning with "Commitment Shortfall -"
- Rows containing "UK,Geographic"
- Rows containing "Non Surcharge"
- Rows containing negative minutes or negative amounts
- Rate 2 rows
- Short date range rows
- Rows with very large minute values

These are NOT subtotal rows.

Even if:
- Minutes are very large
- They appear near totals
- They appear mid-table
- They visually resemble summary rows

They MUST produce JSON objects.

========================================
EXCLUSIONS (STRICT)
========================================

Exclude rows ONLY if they explicitly contain:

- "Service: IDD"
- Column header text
- "Subtotal"
- "Total Charges"

Do NOT exclude rows based on:
- Position in table
- Large numbers
- Destination wording
- Similarity to other rows

========================================
STRICT COMPLETENESS
========================================

Every visible row that contains BOTH:
- Start Date
- End Date

must produce exactly ONE JSON object.

If any Start Date is visible and not extracted,
the output is incomplete and must be corrected.

Return JSON only.
"""

ORANGE_RULES = r"""
Vendor Format: Orange FT – Voice Billing Table

==================================================
SCOPE — WHICH SECTIONS TO EXTRACT
==================================================

Extract rows from BOTH of the following sections:

1. "Direct traffic - REVERSE"
2. "Special Transit"

These sections appear in the "traffic detail" pages.

Ignore completely:
- Voice summary page (first page of invoice)
- TOTAL VOLUME rows
- SUBTOTAL rows
- Tax summary blocks
- Currency-only rows
- Column header rows
- Section title rows

==================================================
DIRECT TRAFFIC - REVERSE SECTION RULES
==================================================

Rows under "Direct traffic - REVERSE" have a sub-header like:
  "ITFS Bilateral IFN UFN DID"

These rows use a special destination format:
  France [G__]-IFN_ALL
  France [G__]-UFN_ALL

CRITICAL formatting rules for these rows:
- The bracket content is [G__] — that is G followed by TWO underscores, then dash.
- Do NOT write [G_] (one underscore).
- Do NOT omit the dash: it is [G__]-IFN_ALL not [G__]IFN_ALL.
- Correct: "France [G__]-IFN_ALL"
- Correct: "France [G__]-UFN_ALL"
- Wrong:   "France [G_]IFN_ALL"   ← missing underscore and dash
- Wrong:   "France [G_]-IFN_ALL"  ← missing one underscore



A row is defined as one horizontal data line containing:

- A Start Date      (e.g. 01 Jul 2024)
- A Period/End Date (e.g. / 31 Jul 2024)
- A Destination
- A Minutes value
- A Tax Rate value
- An Amount value

IMPORTANT — SHARED DATES:

- Multiple consecutive rows often share the SAME Start Date.
- Multiple consecutive rows often share the SAME End Date.
- These are STILL separate rows if the destination differs.
- DO NOT merge rows that share identical dates.
- Each row must be extracted independently regardless of shared dates.

==================================================
COLUMN MAPPING (STRICT)
==================================================

Each data row in the Orange FT table contains these columns left to right:

| Column         | Extract? | Maps to     |
|----------------|----------|-------------|
| Start Date     | YES      | start_date  |
| / End Date     | YES      | end_date    |
| Destination    | YES      | destination |
| Tax code       | NO       | —           |
| Taxed calls    | NO       | —           |
| Minutes        | YES      | minutes     |
| Tax Rate       | YES      | rate        |
| Rate total     | NO       | —           |
| Amount         | YES      | amount      |
| Currency (EUR) | NO       | —           |

IMPORTANT — RATE COLUMN:

- The rate column is labelled "tax rate" in the invoice header.
- It contains a small decimal value like: 0.005, 0.1917, 0.6505
- This IS the per-minute rate to extract.
- Do NOT confuse with the "rate total" block which is a larger number.
- The rate is always a small decimal, never a large integer.

==================================================
END DATE RULE (CRITICAL)
==================================================

Each row has its OWN end date in the period column shown as "/ DD Mon YYYY".

Rules:
- Read the end date from THAT ROW'S own period column only.
- Do NOT copy end date from the row above.
- Do NOT copy end date from the row below.
- Do NOT assume all rows in a block share the same end date.
- Even if two adjacent rows look similar, each has its own end date.

How to read the end date:
- Look at the "/" character on the SAME HORIZONTAL LINE as the row's start date.
- The date immediately after that "/" is the end date for that row only.
- Read the day number carefully — "24" and "31" look different. Do not confuse them.
- Convert to ISO format: "DD Mon YYYY" → "YYYY/MM/DD"

CRITICAL EXAMPLE — adjacent rows with DIFFERENT end dates:
  "01 Jul 2024  / 24 Jul 2024  France -Fix ORANGE\VFF1.B  ..."  → end: 2024/07/24  ← 24, not 31
  "01 Jul 2024  / 31 Jul 2024  France -Fix ORANGE\VFF1.A  ..."  → end: 2024/07/31  ← 31, not 24
  "01 Jul 2024  / 24 Jul 2024  France -Mob SFR\VFM1.A    ..."  → end: 2024/07/24  ← 24, not 31
  "01 Jul 2024  / 31 Jul 2024  France -Mob SFR\VFM1.F    ..."  → end: 2024/07/31  ← 31, not 24
  "01 Jul 2024  / 29 Jul 2024  Andorra -Mob\VA01.B        ..."  → end: 2024/07/29  ← 29, not 31

COMMON MISTAKE — DO NOT DO THIS:
  If a block of rows has mixed end dates (some "24 Jul", some "31 Jul"),
  do NOT normalize them all to "31 Jul".
  Each row's end date is independent. Read it fresh for every single row.

START DATE RULE:
- Read the start date from THAT ROW'S own first column only.
- Do NOT inherit start date from rows above or below.
- "01 Jul" and "24 Jul" are different — read carefully on every row.
- A row starting with "24 Jul 2024" must NOT be written as "01 Jul 2024".

ANOTHER COMMON MISTAKE — wrong start dates:
  "24 Jul 2024  / 30 Jul 2024  Mayotte -Mob SRR\VF06.B   ..."  → start: 2024/07/24  ← NOT 01
  "24 Jul 2024  / 31 Jul 2024  Mayotte -Mob TELCO OI\VF07.A ..." → start: 2024/07/24  ← NOT 01
  "09 Jul 2024  / 09 Jul 2024  Malta -Mob\VM20.A          ..."  → start: 2024/07/09  ← NOT 01
  "11 Jul 2024  / 31 Jul 2024  Central African -Mob NATIONLINK ..." → start: 2024/07/11 ← NOT 01
  "13 Jul 2024  / 16 Jul 2024  Congo Kinshasa -Mob Orange  ..."  → start: 2024/07/13  ← NOT 01
  "20 Jul 2024  / 20 Jul 2024  Romania -Mob VODAFONE\VR01.A ..." → start: 2024/07/20  ← NOT 01

ANOTHER COMMON MISTAKE — wrong end dates (digit confusion):
  Row showing "/ 04 Jul": end must be 2024/07/04, not 2024/07/02  (Guadeloupe -Mob\VF04.A)
  Row showing "/ 19 Jul": end must be 2024/07/19, not 2024/07/29  (Ireland -Mob VODAFONE)
  Row showing "/ 16 Jul": end must be 2024/07/16, not 2024/07/29  (Ireland -Mob\VI60.A/B)
  Row showing "/ 30 Jul": end must be 2024/07/30, not 2024/07/31  (Italy)
  Row showing "/ 26 Jul": end must be 2024/07/26, not 2024/07/29  (Moldova MOLDCELL)
  Row showing "/ 31 Jul": end must be 2024/07/31, not 2024/07/29  (Moldova ORANGE VM41.A)

Digit pairs most often confused: 9↔1, 0↔9, 4↔1. Read each day digit carefully.

==================================================
DATE FORMAT CONVERSION
==================================================

Convert all dates to ISO format YYYY/MM/DD.

Month mapping:
  Jan=01, Feb=02, Mar=03, Apr=04, May=05, Jun=06
  Jul=07, Aug=08, Sep=09, Oct=10, Nov=11, Dec=12

Examples:
  "01 Jul 2024"  →  "2024/07/01"
  "19 Jul 2024"  →  "2024/07/19"
  "31 Jul 2024"  →  "2024/07/31"

Rule: end_date must never be earlier than start_date. If it appears so, re-read the dates.

==================================================
DESTINATION RULES (VERY STRICT)
==================================================

Copy the destination text character-by-character exactly as printed.

BACKSLASH RULE:
- A backslash character "\" appears between the operator name and the variant code.
- It MUST be preserved exactly.
- Never omit the backslash.
- Never merge the characters on either side of the backslash.

Correct examples (copy these patterns exactly):
  "Belgium -Mob ORANGE\VB01.A"
  "Belgium -Mob PROXIMUS\VB01.A"
  "Belgium -Mob\VB01.A"              ← backslash immediately after "Mob", no space before it
  "Belgium -Mob\VB01.B"              ← same pattern
  "Romania -Mob ORANGE\VR01.A"
  "France -Fix OLO\VFF1.A"           ← backslash between OLO and VFF1
  "France -Fix OLO\VFF1.B"
  "France -Fix OLO\VFF1.C"
  "France -Fix OLO\VFF1.D"
  "France -Fix ORANGE\VFF1.A"
  "Ireland -Mob METEOR\VI60.A"
  "Ireland -Mob HUTCHISON\VI60.A"
  "Ireland -Mob O2\VI60.A"
  "Ireland -Mob VODAFONE\VI60.A"
  "Ireland -Mob\VI60.A"
  "Ireland -Mob\VI60.B"
  "Ireland\VI61.A"
  "Italy -Mob WIND3\VI05.A"
  "United Kingdom -Mob EE\VG21.A"    ← backslash between EE and VG21
  "Slovakia -Mob T MOBILE\VS30.A"
  "Switzerland -Mob SUNRISE\VS50.C"
  "Mayotte -Mob TELCO OI\VF07.A"
  "Bulgaria -Mob MOBILTEL\VB30.A"    ← MOBILTEL with L before T
  "Portugal -Mob VODAFONE\VP33.A"    ← VP33 not PV33 (V before P)

WRONG examples (never produce these):
  "Belgium -Mob ORANGEVB01.A"        ← backslash missing
  "Belgium -Mob VB01.A"              ← backslash replaced by space
  "Belgium -Mob VB01.B"              ← backslash replaced by space
  "France -Fix OLOVFF1.A"            ← backslash missing
  "France -Fix OLOVFF1.B"            ← backslash missing
  "Ireland -Mob METEORV60.A"         ← backslash missing AND letter missing
  "United Kingdom -Mob EEVG21.A"     ← backslash missing
  "Bulgaria -Mob MOBITEL\VB30.A"     ← MOBITEL wrong, must be MOBILTEL
  "Network Int -M2M TRANSACTEL"      ← TRANSACTEL wrong, must be TRANSATEL (no C)
  "Portugal -Mob VODAFONE\PV33.A"    ← PV33 wrong, must be VP33 (V before P)

CHARACTER CONFUSION — READ CAREFULLY:

The following characters are visually similar in this invoice font.
Read them carefully and do not swap them:

  "I" (capital i) vs "1" (digit one):
    - VI60 not V160    (Ireland codes use VI = V then I)
    - VI05 not V105    (Italy WIND3 uses VI = V then I)
    - VI61 not V161
    - VS30 not V30     (Slovakia uses VS)

  "O" (capital o) vs "0" (digit zero):
    - VN01 not VNO1    (Netherlands KPN uses VN01)
    - VD00 not VDO0    (Martinique Fix ORANGE uses VD00)
    - VB00 not VBO0

  Letter order — do not transpose:
    - VS50 not SV50    (Switzerland SUNRISE)
    - VS30 not SV30

  Provider name spelling — read letter by letter:
    - MOBILTEL not MOBITEL   (Bulgaria — the L comes before T: M-O-B-I-L-T-E-L)
    - MOLDCELL not MOLDCEILL (Moldova — only one L at the end)
    - SRR is wrong; correct spelling is SFR (Mayotte provider)
    - TRANSATEL not TRANSACTEL (Network Int — no C: T-R-A-N-S-A-T-E-L)
    - VP33 not PV33 (Portugal VODAFONE — V comes first, then P)

SPACING RULE:
  - There is exactly one space between "-" and "Mob" or "-" and "Fix".
  - Example: "Guadeloupe -Fix OLO" not "Guadeloupe - Fix OLO"
  - Example: "Gambia -Mob QCELL" not "Gambia - Mob QCELL"

==================================================
NUMERIC RULES (VERY STRICT)
==================================================

- Remove thousand separators (commas) from numbers.
- Preserve numeric precision exactly as printed.
- Do NOT round any value.
- Do NOT recalculate amounts.
- Keep negative signs if present.

CRITICAL — VERIFY EVERY DIGIT:

After extracting each number, verify it digit-by-digit against the image.

For RATE values:
  - Rate is always a small decimal: typically between 0.001 and 6.0
  - Verify the decimal point position carefully.
  - Example: 0.0115 is NOT the same as 0.115 — it has FOUR decimal places, not three.
    Specifically: Guadeloupe -Mob DIGICEL\VF01.A has rate 0.0115, not 0.115.
  - Example: 0.0117 is NOT the same as 0.117 — count digits after the decimal point.
  - Example: 0.235379 is NOT the same as 0.233579 — read each digit left to right.
  - Example: Network Int -AEROMOBILE has rate 5.009 — verify the leading "5" is present.

For MINUTES values:
  - Large values like 5,485,466.53 are valid — preserve all digits.
  - Verify no leading digit is dropped.
  - CRITICAL: Do NOT borrow minutes from a different row on the same page.
    Each row's minutes value is printed on its own horizontal line.
    Example on the same page: Romania -Mob ORANGE\VR01.C and Senegal -Mob ORANGE
    may appear near each other — they have completely different minutes values.
    Read each row's minutes from its own line only.

For AMOUNT values:
  - Cross-check: amount must be approximately equal to minutes × rate.
  - Tolerance: ±0.10 EUR.
  - If amount differs by more than 0.10 EUR from minutes × rate, re-read from the image.
  - Example: if minutes=3.85 and rate=0.72, amount must be ~2.77, not 27.77.
  - Example: if minutes=204.88 and rate=0.0482, amount must be ~9.88, not 98.88.

==================================================
EXCLUSIONS
==================================================

Exclude a row ONLY if it explicitly contains one of:
  - "TOTAL VOLUME"
  - "SUBTOTAL"
  - "TAX" as a standalone label row
  - Column header text repeated mid-table
  - "Direct traffic - REVERSE" section title (exclude the title, not its rows)

Do NOT exclude rows based on:
  - Large minute values
  - Large amount values
  - Repeated start dates
  - Similar destination names to other rows

==================================================
COMPLETENESS CHECK (MANDATORY BEFORE RETURNING)
==================================================

Before returning your JSON:

Step 1 — Count every visible data row on the page (rows with dates + destination + amount).
Step 2 — Count your JSON objects.
Step 3 — These counts MUST match.
Step 4 — If they do not match, identify the missing row and add it.
Step 5 — Pay special attention to:
  - Rows with very small amounts (0.00, 0.01) — these are easy to miss.
  - Rows near page boundaries.
  - Rows immediately after section headers.
  - Ireland -Mob\VI60.B (16 Jul → 16 Jul, amount=0.03) — this row is easily missed.
    It appears between Ireland -Mob VODAFONE\VI60.A and Ireland\VI61.A.
    It MUST be included.

DIGIT TRANSPOSITION CHECK:
  After extracting minutes, re-read the last two digits specifically.
  Example: 7180.38 is NOT 7180.83 — the digits "38" must not become "83".

Return JSON only. No explanation. No markdown.
"""
