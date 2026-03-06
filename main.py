## main.py
from core.prompt_builder import build_prompt
from core.vendor_rules import INFO_RULES, ORANGE_RULES
from core.extractor import extract_page_data, validate_extraction
from core.validator import validate_rows
from core.csv_writer import write_csv
from core.image_converter import pdf_to_images
from core.pass3 import run_pass3  # place pass3.py inside your core/ folder

def process_pdf(pdf_path, vendor="info"):
    if vendor == "info":
        prompt = build_prompt(INFO_RULES)
        dpi = 350
        output_file = "infotech_output.csv"
    elif vendor == "orange":
        prompt = build_prompt(ORANGE_RULES)
        dpi = 450  # Orange layout is denser
        output_file = "orange_output.csv"
    else:
        raise ValueError("Unsupported vendor")

    images = pdf_to_images(pdf_path, dpi=dpi)
    all_rows = []

    # Skip first 2 pages (cover + summary for both vendors)
    for img in images[2:]:
        print("\n==============================")
        print(f"Processing page: {img}")
        print("==============================")

        # PASS 1 — LLM extraction
        extracted = extract_page_data(img, prompt)
        print(f"Rows extracted (Pass 1): {len(extracted)}")

        # PASS 2 — LLM self-validation
        validated_llm = validate_extraction(img, extracted)
        print(f"Rows after LLM validation (Pass 2): {len(validated_llm)}")

        # Python validation — arithmetic + date format checks
        validated_py = validate_rows(validated_llm)
        flagged = sum(1 for r in validated_py if not r.get("numeric_valid", True))
        print(f"Rows after Python validation: {len(validated_py)} ({flagged} flagged)")

        # PASS 3 — targeted re-check of flagged rows only
        if flagged > 0:
            print(f"Running Pass 3 on {flagged} flagged rows...")
            corrected = run_pass3(img, validated_py)

            # Re-run Python validation after PASS 3 corrections
            final_rows = validate_rows(corrected)
            still_flagged = sum(1 for r in final_rows if not r.get("numeric_valid", True))
            print(f"Rows after Pass 3: {len(final_rows)} ({still_flagged} still flagged)")
        else:
            print("Pass 3: No flagged rows — skipping")
            final_rows = validated_py

        all_rows.extend(final_rows)

    write_csv(all_rows, output_file)
    print("\n✅ Extraction complete.")
    print(f"Vendor: {vendor}")
    print(f"Total rows extracted: {len(all_rows)}")

if __name__ == "__main__":
    # ---- Choose vendor here ----

    # For Info Telecom:
    # process_pdf(
    #     "Info Telecom_VEGL_IN_IDD_EUR_BIL_INV_20250211_00024649.pdf",
    #     vendor="info"
    # )

    # For Orange FT:
    process_pdf("5210505398.pdf", vendor="orange")
