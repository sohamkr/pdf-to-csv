## extractor.py for orange ft

import base64
import json
import re
from openai import AzureOpenAI
from config.settings import settings


# ---------------------------
# Azure Client Initialization
# ---------------------------
client = AzureOpenAI(
    api_key=settings.AZURE_OPENAI_API_KEY,
    api_version=settings.AZURE_OPENAI_API_VERSION,
    azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
)


# ---------------------------
# Encode Image to Base64
# ---------------------------
def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ---------------------------
# Clean & Extract JSON safely
# ---------------------------
def extract_json_from_response(text):
    if not text:
        raise ValueError("Empty response from LLM")

    text = text.strip()

    # Remove markdown fences
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Extract JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in model response")

    json_text = match.group(0)

    # NOTE: Do NOT apply any backslash escaping here.
    # The LLM returns destination strings like "Belgium -Mob ORANGE\VB01.A"
    # which in JSON must be represented as "Belgium -Mob ORANGE\\VB01.A".
    # The LLM already does this correctly when instructed.
    # Applying a regex substitution here corrupts correctly escaped strings.

    return json_text


# ---------------------------
# PASS 1 - Extraction
# ---------------------------
def extract_page_data(image_path, prompt):
    base64_image = encode_image(image_path)

    response = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all billing table rows from this invoice page. Return JSON only."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
    )

    raw_output = response.choices[0].message.content

    print("\n-----------------------------")
    print(f"Processing page: {image_path}")
    print("RAW LLM OUTPUT (PASS 1):")
    print(raw_output)
    print("-----------------------------\n")

    try:
        clean_json = extract_json_from_response(raw_output)
        return json.loads(clean_json)
    except Exception as e:
        print("❌ Failed to parse JSON:", e)
        return []


# ---------------------------
# PASS 2 - Self Validation
# ---------------------------
VALIDATION_PROMPT = r"""
You are auditing a structured data extraction from a telecom invoice image.

You will receive:
1. A JSON array of extracted rows
2. The original invoice image

Your job is to find and fix ALL errors by comparing the JSON to the image.

==================================================
STEP 1 — ROW COUNT CHECK
==================================================

Count the number of visible data rows on the invoice image
(rows that contain a date, destination, and amount).

Count the number of JSON objects provided.

These counts MUST match.

- If JSON has FEWER rows than the image: find the missing rows and ADD them.
- If JSON has MORE rows than the image: find the hallucinated rows and REMOVE them.

Pay special attention to:
- Rows with small amounts (0.00, 0.01) near page bottom
- Rows immediately after section headers
- Rows at page edges

==================================================
STEP 2 — PER-ROW FIELD AUDIT
==================================================

For every row in the JSON, compare each field to the image:

start_date:
- Verify day, month, year digit-by-digit.
- Format must be YYYY/MM/DD.
- A row whose first column shows "24 Jul" must have start_date 2024/07/24, NOT 2024/07/01.
- A row whose first column shows "09 Jul" must have start_date 2024/07/09, NOT 2024/07/01.
- A row whose first column shows "20 Jul" must have start_date 2024/07/20, NOT 2024/07/01.

end_date:
- Verify this row's OWN end date from its own period column ("/ DD Mon YYYY").
- Do NOT accept an end date copied from an adjacent row.
- Format must be YYYY/MM/DD.
- Must not be earlier than start_date.
- "24 Jul" and "31 Jul" are different — verify the exact day digits on each row's own line.
- A row whose period column shows "/ 24 Jul" must have end_date 2024/07/24, NOT 2024/07/31.
- Do NOT normalize a group of rows to the same end date just because most share it.

destination:
- Compare character-by-character to the image.
- Backslashes MUST be present where shown: "ORANGE\VR01.A" not "ORANGEVR01.A"
- Check for swapped characters:
    "I" vs "1": VI60 not V160, VI05 not V105
    "O" vs "0": VN01 not VNO1, VD00 not VDO0
- Check for transposed letters: VS50 not SV50
- Check provider spelling: SFR not SRR, MOBILTEL not MOBITEL, MOLDCELL not MOLDCEILL
- Spacing: "-Mob" not "- Mob", "-Fix" not "- Fix"

rate:
- Verify digit-by-digit against the "tax rate" column.
- Rate must be a small decimal (typically 0.001 to 6.0).
- Count decimal places carefully: 0.0117 has 4 decimal places, 0.117 has 3 — they are different.
- Check for digit transpositions: 0.235379 ≠ 0.233579 — verify each digit left to right.
- If rate looks unusually large, verify it is not from the "rate total" column.

minutes:
- Verify digit-by-digit from THIS ROW'S own horizontal line.
- Large values like 5,485,466.53 are valid — verify all digits present.
- CRITICAL: Do NOT borrow minutes from a nearby row on the same page.
  Each row's minutes is printed on its own line. If two rows appear close together,
  their minutes values are completely independent — read each one separately.
  Wrong minutes will cause wrong amounts. Use the arithmetic check below to catch this.

amount:
- Verify digit-by-digit.
- ARITHMETIC CHECK: amount must be approximately equal to minutes × rate.
  Tolerance: ±0.10 EUR.
  If amount differs from minutes × rate by more than 0.10 EUR,
  re-read the amount from the image and correct it.
  Example: minutes=3.85, rate=0.72 → expected amount ≈ 2.77. If JSON shows 27.77, fix to 2.77.
  Example: minutes=204.88, rate=0.0482 → expected amount ≈ 9.88. If JSON shows 98.88, fix to 9.88.

==================================================
STEP 3 — RETURN CORRECTED JSON
==================================================

Return the FULL corrected JSON array.
Include ALL rows (both corrected and unchanged).
Return JSON only. No explanation. No markdown.
"""


def validate_extraction(image_path, extracted_json):
    base64_image = encode_image(image_path)

    response = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": VALIDATION_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Here is the extracted JSON to audit:\n\n{json.dumps(extracted_json, indent=2)}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
    )

    raw_output = response.choices[0].message.content

    print("VALIDATION RAW OUTPUT (PASS 2):")
    print(raw_output)

    try:
        clean_json = extract_json_from_response(raw_output)
        return json.loads(clean_json)
    except Exception as e:
        print("⚠ Validation parsing failed:", e)
        return extracted_json  # fallback to original extraction
