## pass3.py — Targeted re-extraction for flagged rows
##
## Fires ONLY on rows that failed validator.py checks.
## Sends each flagged row back to the LLM with the original image,
## asking it to re-read ONLY that specific row with focused attention.
##
## Catches errors that survive PASS 1 and PASS 2:
##   - Co-contaminated rate+amount (both wrong but self-consistent)
##   - Digit transpositions in minutes (7180.38 → 7180.83)
##   - Date digit misreads (19 vs 29, 26 vs 29, 30 vs 31)
##   - Missing rows (row count mismatch)

import base64
import json
import re
import logging
from openai import AzureOpenAI
from config.settings import settings

logger = logging.getLogger(__name__)

client = AzureOpenAI(
    api_key=settings.AZURE_OPENAI_API_KEY,
    api_version=settings.AZURE_OPENAI_API_VERSION,
    azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
)


def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_json_from_response(text):
    if not text:
        raise ValueError("Empty response")
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return "[" + match.group(0) + "]"
    raise ValueError("No JSON found in response")


# ------------------------------------------------------------------
# Determine which rows need PASS 3 re-checking
# ------------------------------------------------------------------

def get_flagged_rows(validated_rows):
    """
    Returns list of (index, row, reason) for rows that need re-checking.
    Reasons:
      - numeric_invalid: rate * minutes != amount (beyond tolerance)
      - suspicious_rate: rate has unusual decimal place count
      - suspicious_minutes: last two decimal digits look transposed
      - date_suspicious: date range seems implausibly long or mismatched
    """
    flagged = []

    for i, row in enumerate(validated_rows):
        reasons = []

        # 1. Failed arithmetic validation
        if not row.get("numeric_valid", True):
            diff = row.get("difference")
            if diff is not None and float(diff) > 0.10:
                reasons.append(f"arithmetic_fail: rate×min≠amount (diff={diff})")

        # 2. Suspicious rate — decimal point may be shifted
        try:
            rate = float(row["rate"])
            minutes = float(row["minutes"])
            amount = float(row["amount"])

            # Check if rate looks 10× too high (common decimal shift error)
            # If rate/10 * minutes is much closer to amount, flag it
            if rate > 0.05:
                alt_amount = (rate / 10) * minutes
                actual_diff = abs(rate * minutes - amount)
                alt_diff = abs(alt_amount - amount)
                if alt_diff < actual_diff and alt_diff < 0.10:
                    reasons.append(
                        f"rate_decimal_shift: rate={rate} may be {rate/10:.4f} "
                        f"(alt_diff={alt_diff:.4f} < actual_diff={actual_diff:.4f})"
                    )

        except (ValueError, TypeError, KeyError):
            pass

        # 3. Suspicious minutes — last two decimal digits transposed
        try:
            min_str = str(row["minutes"])
            if "." in min_str:
                decimals = min_str.split(".")[1]
                if len(decimals) >= 2:
                    last_two = decimals[-2:]
                    reversed_two = last_two[::-1]
                    if last_two != reversed_two:  # not palindrome
                        # Check if reversing last two decimal digits gets closer to expected
                        min_val = float(min_str)
                        # Construct reversed version
                        reversed_str = min_str[:-2] + reversed_two
                        try:
                            reversed_min = float(reversed_str)
                            rate = float(row["rate"])
                            amount = float(row["amount"])
                            actual_diff = abs(rate * min_val - amount)
                            alt_diff = abs(rate * reversed_min - amount)
                            if alt_diff < actual_diff and actual_diff > 0.10:
                                reasons.append(
                                    f"minutes_transposition: {min_str} may be {reversed_str} "
                                    f"(alt_diff={alt_diff:.4f} < actual_diff={actual_diff:.4f})"
                                )
                        except ValueError:
                            pass
        except (ValueError, TypeError, KeyError):
            pass

        # 4. Suspicious date range — end date same as start but looks wrong
        try:
            start = row.get("start_date", "")
            end = row.get("end_date", "")
            if start and end:
                from datetime import datetime
                s = datetime.strptime(start, "%Y/%m/%d")
                e = datetime.strptime(end, "%Y/%m/%d")
                span = (e - s).days
                # Flag if span is suspiciously long (>28 days) for a row
                # that historically should be short — heuristic based on minutes
                minutes_val = float(row.get("minutes", 0))
                if span > 28 and minutes_val < 10:
                    reasons.append(
                        f"date_span_suspicious: {span} day span but only {minutes_val} minutes"
                    )
        except (ValueError, TypeError, KeyError):
            pass

        if reasons:
            flagged.append((i, row, reasons))

    return flagged


# ------------------------------------------------------------------
# PASS 3 prompt — focused single-row re-read
# ------------------------------------------------------------------

PASS3_PROMPT = r"""
You are re-reading ONE specific row from a telecom invoice image.

The row has been flagged because its extracted values may contain errors.

You will be given:
1. The destination name of the row to find
2. Its approximate start date
3. The original invoice image

Your task:
1. Find that specific row on the invoice image.
2. Re-read ONLY that row's values very carefully.
3. Return a corrected JSON object for that row only.

Fields to return:
- start_date  (YYYY/MM/DD)
- end_date    (YYYY/MM/DD)
- destination (exact text as printed)
- rate        (exact decimal as printed — count decimal places carefully)
- minutes     (exact number — verify every digit, especially the last two)
- amount      (exact number)

CRITICAL READING RULES:

Dates:
- Read start and end dates from THIS ROW'S own line only.
- "01 Jul", "11 Jul", "13 Jul", "20 Jul", "24 Jul" are all different.
- "04 Jul", "16 Jul", "19 Jul", "26 Jul", "29 Jul", "30 Jul", "31 Jul" are all different.
- Do not borrow dates from adjacent rows.

Rate:
- Count the decimal places: 0.0115 has 4 decimal places, 0.115 has 3. They are different.
- The rate comes from the "Tax Rate" column (small decimal).
- Do NOT read from the "Rate total" column (larger number).

Minutes:
- Read every digit. Pay special attention to the last two decimal digits.
- 7180.38 ≠ 7180.83. Read "38" not "83".

Amount:
- Verify: amount ≈ minutes × rate (within 0.10 EUR).
- If amount is 10× larger or smaller than minutes×rate, re-read it.

Return JSON only. Return a single JSON object (not an array).
"""


def recheck_row(image_path, row, reasons):
    """
    Re-extract a single flagged row using focused PASS 3 prompt.
    Returns corrected row dict, or original row if re-check fails.
    """
    base64_image = encode_image(image_path)

    context = (
        f"Row to find and re-read:\n"
        f"  Destination: {row.get('destination', '?')}\n"
        f"  Start date:  {row.get('start_date', '?')}\n"
        f"  Currently extracted values (may be wrong):\n"
        f"    rate={row.get('rate')}  minutes={row.get('minutes')}  amount={row.get('amount')}\n"
        f"    end_date={row.get('end_date')}\n"
        f"  Flagged because: {'; '.join(reasons)}\n\n"
        f"Please re-read this row from the image and return the corrected JSON."
    )

    try:
        response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": PASS3_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": context},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                        }
                    ]
                }
            ]
        )

        raw = response.choices[0].message.content
        logger.info(f"PASS 3 raw response for '{row.get('destination')}':\n{raw}")

        clean = extract_json_from_response(raw)
        corrected_list = json.loads(clean)
        corrected = corrected_list[0] if corrected_list else {}

        if not corrected:
            logger.warning(f"PASS 3 returned empty for '{row.get('destination')}' — keeping original")
            return row

        # Only accept correction if it contains all required fields
        required = {"start_date", "end_date", "destination", "rate", "minutes", "amount"}
        if not required.issubset(corrected.keys()):
            logger.warning(f"PASS 3 missing fields for '{row.get('destination')}' — keeping original")
            return row

        logger.info(
            f"PASS 3 corrected '{row.get('destination')}': "
            f"rate {row.get('rate')}→{corrected.get('rate')}, "
            f"min {row.get('minutes')}→{corrected.get('minutes')}, "
            f"amt {row.get('amount')}→{corrected.get('amount')}, "
            f"end {row.get('end_date')}→{corrected.get('end_date')}"
        )

        # Preserve validation metadata from original, will be re-validated after
        corrected.pop("numeric_valid", None)
        corrected.pop("difference", None)
        return corrected

    except Exception as e:
        logger.warning(f"PASS 3 failed for '{row.get('destination')}': {e} — keeping original")
        return row


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

def run_pass3(image_path, validated_rows):
    """
    Run PASS 3 on all flagged rows.
    Returns the full row list with corrections applied.
    """
    flagged = get_flagged_rows(validated_rows)

    if not flagged:
        logger.info("PASS 3: No rows flagged — all rows passed checks")
        return validated_rows

    logger.info(f"PASS 3: {len(flagged)} rows flagged for re-check")
    for i, row, reasons in flagged:
        logger.info(f"  Row {i} [{row.get('destination')}]: {reasons}")

    corrected_rows = list(validated_rows)  # copy

    for i, row, reasons in flagged:
        logger.info(f"PASS 3: Re-checking row {i} — {row.get('destination')}")
        corrected = recheck_row(image_path, row, reasons)
        corrected_rows[i] = corrected

    return corrected_rows
