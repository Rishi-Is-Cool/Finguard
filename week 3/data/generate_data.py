"""
generate_data.py
Run this ONCE to create transactions.csv
Usage: python generate_data.py
"""
import pandas as pd
import random
from datetime import datetime, timedelta

random.seed(42)

ACCOUNTS     = ["ACC001", "ACC002", "ACC003"]
BENEFICIARIES = ["Raj Kumar", "Priya Ltd", "Unknown Co", "FastCash", "Sneha Traders"]
DESCRIPTIONS  = [
    "NEFT transfer", "UPI payment", "ATM withdrawal",
    "Online purchase", "Salary credit", "EMI debit"
]

rows = []
base_date = datetime(2024, 1, 1)

for i in range(200):
    date  = base_date + timedelta(days=random.randint(0, 90))
    hour  = random.choice([2, 3, 11, 14, 15, 22, 23])
    minute = random.randint(0, 59)

    # Mix normal amounts with fraud-like structuring amounts
    amount_type = random.choices(
        ["normal", "structuring", "large"],
        weights=[0.70, 0.20, 0.10]
    )[0]

    if amount_type == "normal":
        amount = random.randint(1_000, 40_000)
    elif amount_type == "structuring":
        amount = random.choice([49_500, 49_800, 49_900, 49_000, 48_500])
    else:
        amount = random.randint(1_00_000, 5_00_000)

    rows.append({
        "date":        date.strftime("%Y-%m-%d"),
        "time":        f"{hour:02d}:{minute:02d}",
        "account":     random.choice(ACCOUNTS),
        "beneficiary": random.choice(BENEFICIARIES),
        "description": random.choice(DESCRIPTIONS),
        "amount":      amount,
        "type":        random.choice(["debit", "credit"]),
    })

df = pd.DataFrame(rows)
df.to_csv("transactions.csv", index=False)
print(f"Created transactions.csv with {len(df)} rows")
print(df.head(10).to_string())
