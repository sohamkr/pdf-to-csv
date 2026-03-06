import re
import logging

logger = logging.getLogger(__name__)

# Tolerance for rate * minutes ≈ amount check (in EUR)
AMOUNT_TOLERANCE = 0.10


def clean_number(value):
    """
    Removes thousand separators and converts to float.
    Handles negative numbers.
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).strip()
    value = value.replace(",", "")  # remove thousand separator

    return float(value)


def validate_rows(rows):
    validated = []

    for i, row in enumerate(rows):
        try:
            # --- Date format check ---
            assert re.match(r"\d{4}/\d{2}/\d{2}", str(row["start_date"])), \
                f"Bad start_date: {row['start_date']}"
            assert re.match(r"\d{4}/\d{2}/\d{2}", str(row["end_date"])), \
                f"Bad end_date: {row['end_date']}"

            # --- End date not before start date ---
            assert row["end_date"] >= row["start_date"], \
                f"end_date {row['end_date']} is before start_date {row['start_date']}"

            # --- Numeric parsing ---
            rate = clean_number(row["rate"])
            minutes = clean_number(row["minutes"])
            amount = clean_number(row["amount"])

            # --- Arithmetic check ---
            calculated = rate * minutes
            difference = abs(calculated - amount)
            numeric_valid = difference <= AMOUNT_TOLERANCE

            if not numeric_valid:
                logger.warning(
                    f"Row {i} [{row.get('destination', '?')}]: "
                    f"amount mismatch — {minutes} × {rate} = {calculated:.4f}, "
                    f"but extracted amount = {amount} (diff={difference:.4f})"
                )

            row["rate"] = rate
            row["minutes"] = minutes
            row["amount"] = amount
            row["numeric_valid"] = numeric_valid
            row["difference"] = round(difference, 4)

            validated.append(row)

        except AssertionError as e:
            logger.warning(f"Row {i} failed validation: {e} | Row data: {row}")
            row["numeric_valid"] = False
            row["difference"] = None
            validated.append(row)

        except Exception as e:
            logger.warning(f"Row {i} unexpected error: {e} | Row data: {row}")
            row["numeric_valid"] = False
            row["difference"] = None
            validated.append(row)

    total = len(validated)
    invalid = sum(1 for r in validated if not r.get("numeric_valid", False))
    logger.info(f"Validation complete: {total} rows, {invalid} invalid, {total - invalid} valid")

    return validated
