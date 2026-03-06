import csv

def write_csv(rows, output_path):
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames = [
            "start_date",
            "end_date",
            "destination",
            "rate",
            "minutes",
            "amount",
            "numeric_valid",
            "difference"
        ]
        )
        writer.writeheader()
        writer.writerows(rows)