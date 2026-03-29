import csv
from functools import lru_cache


@lru_cache(maxsize=1)
def load_baseline_data(path="data/baseline_prices.csv"):
    with open(path, newline='', encoding='utf-8') as f:
        data = list(csv.DictReader(f))

        for row in data:
            row["year_from"] = int(row["year_from"])
            row["year_to"] = int(row["year_to"])
            row["median_price"] = int(row["median_price"])
            row["typical_mileage"] = int(row["typical_mileage"])
            row["sample_size"] = int(row["sample_size"])

        return data