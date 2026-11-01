"""
data/build_dataset.py — Day 16
Builds the instruction-tuning dataset for fraud classification.
Generates 500+ labeled examples in Alpaca format.

Format:
{
  "instruction": "Classify this transaction for fraud risk",
  "input": "<transaction description>",
  "output": "<RISK_LEVEL> — <reason>"
}

Usage: python data/build_dataset.py
Output: data/fraud_dataset.json, data/fraud_dataset_train.json, data/fraud_dataset_test.json
"""
import json
import random
from datetime import datetime, timedelta

random.seed(42)

# ── Building blocks ───────────────────────────────────────────────────────────

HIGH_RISK_TEMPLATES = [
    # Structuring
    (
        "₹{amount} NEFT transfer at {time} from {account} to {beneficiary}. "
        "Amount is ₹{margin} below the ₹50,000 reporting threshold.",
        "HIGH RISK — Classic structuring pattern. Amount deliberately kept ₹{margin} "
        "below ₹50,000 reporting threshold. Recommend immediate SAR filing and account freeze."
    ),
    (
        "Debit of ₹{amount} to {beneficiary} at {time}. "
        "Third such transaction this week, all between ₹48,000–₹49,900.",
        "HIGH RISK — Repeated structuring. Multiple transactions just below threshold "
        "indicate systematic avoidance of reporting requirements. Classic smurfing pattern."
    ),
    # Late night + high amount
    (
        "₹{large_amount} transfer at {late_time} to newly added beneficiary {beneficiary}. "
        "Beneficiary added 8 minutes before transfer.",
        "HIGH RISK — Large amount transferred at {late_time} to a beneficiary added "
        "just 8 minutes prior. High-risk combination: late night + new payee + large amount."
    ),
    (
        "UPI payment of ₹{large_amount} to {beneficiary} at {late_time}. "
        "Account {account} shows 12 transactions in last 6 hours.",
        "HIGH RISK — Extremely high transaction velocity (12 in 6 hours) combined with "
        "large late-night UPI payment. Likely account takeover or money mule activity."
    ),
    # Unknown beneficiary
    (
        "₹{amount} sent to 'Unknown Co' via RTGS at {time} from {account}. "
        "No prior transactions with this beneficiary.",
        "HIGH RISK — Transfer to 'Unknown Co', a vague beneficiary name commonly "
        "associated with money mules. No transaction history. Requires immediate KYC verification."
    ),
    (
        "Three consecutive transfers totalling ₹{total} to FastCash within 2 hours "
        "from {account}. Individual amounts: ₹{a1}, ₹{a2}, ₹{a3}.",
        "HIGH RISK — Layering pattern detected. Funds split across three rapid transfers "
        "to FastCash, a high-risk informal money transfer operator. Possible hawala activity."
    ),
    # Rapid fund movement
    (
        "₹{large_amount} credited to {account} at {time1}, then ₹{large_amount2} "
        "debited to {beneficiary} at {time2} (within 45 minutes).",
        "HIGH RISK — Rapid fund movement (credit then debit within 45 minutes) "
        "is a strong layering indicator. Funds are being passed through this account."
    ),
    (
        "ATM withdrawal of ₹{amount} at {late_time} from location flagged in "
        "prior fraud case. Account {account}.",
        "HIGH RISK — Cash withdrawal at {late_time} from a previously flagged ATM location. "
        "Immediate card block and branch notification recommended."
    ),
]

MEDIUM_RISK_TEMPLATES = [
    (
        "₹{amount} NEFT to {beneficiary} at {evening_time}. "
        "Beneficiary added to {account} yesterday.",
        "MEDIUM RISK — Transaction to a recently added beneficiary. "
        "While the amount and time are within normal range, new payee warrants monitoring "
        "for the next 30 days."
    ),
    (
        "5 UPI transactions from {account} totalling ₹{total} in the last 3 hours. "
        "Usual daily average is 2 transactions.",
        "MEDIUM RISK — Transaction velocity elevated (5 in 3 hours vs daily avg of 2). "
        "Could be legitimate bulk payments but warrants automated monitoring."
    ),
    (
        "₹{amount} transferred to {beneficiary} at {late_time}. "
        "First transaction from {account} at this hour.",
        "MEDIUM RISK — Late evening transaction ({late_time}) is unusual for this account "
        "which has no prior transactions after 9pm. Monitor for pattern repetition."
    ),
    (
        "Round number transaction: exactly ₹{round_amount} sent to {beneficiary} "
        "via IMPS. Third round-number transaction this month.",
        "MEDIUM RISK — Round number bias (exactly ₹{round_amount}) combined with "
        "repeated pattern suggests possible structured payments. Monitor beneficiary."
    ),
    (
        "EMI payment of ₹{amount} to {beneficiary} but no loan account found "
        "in system for {account}.",
        "MEDIUM RISK — EMI payment to unverified lender. No corresponding loan "
        "account on record. Could be legitimate external loan or unauthorized debit."
    ),
    (
        "₹{amount} cash deposit followed immediately by ₹{amount2} NEFT transfer "
        "from {account} within 20 minutes.",
        "MEDIUM RISK — Cash deposit immediately followed by digital transfer suggests "
        "possible cash-to-digital conversion. Verify source of cash deposit."
    ),
]

LOW_RISK_TEMPLATES = [
    (
        "Salary credit of ₹{salary} to {account} from employer {beneficiary} "
        "on {date}. Consistent with last 6 months.",
        "LOW RISK — Regular salary credit from known employer. "
        "Amount consistent with historical pattern. No action required."
    ),
    (
        "EMI debit of ₹{emi} from {account} to {beneficiary} on scheduled date. "
        "Matches loan repayment schedule.",
        "LOW RISK — Scheduled EMI payment on due date. "
        "Matches loan account records. No action required."
    ),
    (
        "UPI payment of ₹{small_amount} from {account} to {beneficiary} "
        "at {daytime}. Described as grocery purchase.",
        "LOW RISK — Small retail UPI payment during business hours "
        "to a known merchant. Normal consumer behavior."
    ),
    (
        "Online purchase of ₹{amount} from {beneficiary} at {daytime}. "
        "Merchant is registered e-commerce platform.",
        "LOW RISK — E-commerce purchase from registered merchant. "
        "Amount within normal spending range. No action required."
    ),
    (
        "₹{small_amount} ATM withdrawal at {daytime} from home branch. "
        "Within weekly withdrawal limit for {account}.",
        "LOW RISK — ATM withdrawal within normal limits during business hours "
        "at home branch. No suspicious indicators."
    ),
    (
        "NEFT transfer of ₹{amount} from {account} to {beneficiary}. "
        "Regular monthly transfer, consistent for 18 months.",
        "LOW RISK — Recurring monthly NEFT to established beneficiary. "
        "18-month consistent pattern. No action required."
    ),
]

# ── Value pools ───────────────────────────────────────────────────────────────
ACCOUNTS     = ["ACC001", "ACC002", "ACC003", "SB-4421", "CA-7890"]
BENEFICIARIES_HIGH   = ["Unknown Co", "FastCash", "QuickPay Ltd", "RapidFunds", "CashXpress"]
BENEFICIARIES_MEDIUM = ["New Payee Ltd", "FirstTime Co", "Unverified Services", "EasyLoan"]
BENEFICIARIES_LOW    = ["Amazon India", "HDFC Bank EMI", "Raj Kumar", "Priya Enterprises", "TechCorp Salary"]

def rand_structuring_amount():
    base   = 50000
    margin = random.randint(100, 2000)
    return base - margin, margin

def rand_large_amount():
    return random.choice([75000, 100000, 150000, 200000, 500000])

def rand_small_amount():
    return random.randint(200, 5000)

def rand_salary():
    return random.choice([35000, 42000, 55000, 68000, 85000])

def rand_emi():
    return random.choice([8500, 12000, 15500, 22000])

def rand_round():
    return random.choice([10000, 25000, 50000, 100000])

def rand_late_time():
    h = random.choice([23, 0, 1, 2, 3])
    return f"{h:02d}:{random.randint(0,59):02d}"

def rand_evening_time():
    h = random.choice([20, 21, 22])
    return f"{h:02d}:{random.randint(0,59):02d}"

def rand_daytime():
    h = random.choice([9,10,11,12,13,14,15,16,17])
    return f"{h:02d}:{random.randint(0,59):02d}"

def rand_date():
    base = datetime(2024, 1, 1)
    return (base + timedelta(days=random.randint(0,90))).strftime("%Y-%m-%d")

def rand_total_from_parts():
    a1 = random.randint(15000, 20000)
    a2 = random.randint(15000, 20000)
    a3 = random.randint(10000, 15000)
    return a1+a2+a3, a1, a2, a3


# ── Dataset builder ───────────────────────────────────────────────────────────

def build_example(template_tuple, risk_level: str) -> dict:
    inp_tmpl, out_tmpl = template_tuple
    account     = random.choice(ACCOUNTS)
    date        = rand_date()
    late_time   = rand_late_time()
    evening_time = rand_evening_time()
    daytime     = rand_daytime()
    amount, margin = rand_structuring_amount()
    large_amount   = rand_large_amount()
    small_amount   = rand_small_amount()
    salary         = rand_salary()
    emi            = rand_emi()
    round_amount   = rand_round()
    total, a1, a2, a3 = rand_total_from_parts()
    large_amount2  = int(large_amount * 0.9)

    if risk_level == "HIGH":
        beneficiary = random.choice(BENEFICIARIES_HIGH)
    elif risk_level == "MEDIUM":
        beneficiary = random.choice(BENEFICIARIES_MEDIUM)
    else:
        beneficiary = random.choice(BENEFICIARIES_LOW)

    # time1 and time2 for rapid movement template
    h1 = random.randint(10, 14)
    time1 = f"{h1:02d}:00"
    time2 = f"{h1:02d}:45"

    fmt = dict(
        account=account, date=date, beneficiary=beneficiary,
        amount=f"{amount:,}", margin=f"{margin:,}",
        large_amount=f"{large_amount:,}", large_amount2=f"{large_amount2:,}",
        small_amount=f"{small_amount:,}", salary=f"{salary:,}",
        emi=f"{emi:,}", round_amount=f"{round_amount:,}",
        total=f"{total:,}", a1=f"{a1:,}", a2=f"{a2:,}", a3=f"{a3:,}",
        late_time=late_time, evening_time=evening_time, daytime=daytime,
        time=daytime if risk_level == "LOW" else late_time,
        time1=time1, time2=time2,
    )

    try:
        inp = inp_tmpl.format(**fmt)
        out = out_tmpl.format(**fmt)
    except KeyError:
        inp = inp_tmpl
        out = out_tmpl

    return {
        "instruction": "You are a financial fraud analyst. Classify this transaction for fraud risk and explain your reasoning.",
        "input": inp.strip(),
        "output": out.strip(),
        "risk_level": risk_level,
    }


def build_dataset(n_per_class: int = 170) -> list:
    examples = []

    for _ in range(n_per_class):
        tmpl = random.choice(HIGH_RISK_TEMPLATES)
        examples.append(build_example(tmpl, "HIGH"))

    for _ in range(n_per_class):
        tmpl = random.choice(MEDIUM_RISK_TEMPLATES)
        examples.append(build_example(tmpl, "MEDIUM"))

    for _ in range(n_per_class):
        tmpl = random.choice(LOW_RISK_TEMPLATES)
        examples.append(build_example(tmpl, "LOW"))

    random.shuffle(examples)
    return examples


if __name__ == "__main__":
    import os, json
    os.makedirs("data", exist_ok=True)

    dataset = build_dataset(n_per_class=170)
    print(f"Total examples: {len(dataset)}")
    print(f"  HIGH:   {sum(1 for d in dataset if d['risk_level']=='HIGH')}")
    print(f"  MEDIUM: {sum(1 for d in dataset if d['risk_level']=='MEDIUM')}")
    print(f"  LOW:    {sum(1 for d in dataset if d['risk_level']=='LOW')}")

    # Split 80/20
    split = int(len(dataset) * 0.8)
    train = dataset[:split]
    test  = dataset[split:]

    with open("data/fraud_dataset.json",       "w") as f: json.dump(dataset, f, indent=2)
    with open("data/fraud_dataset_train.json", "w") as f: json.dump(train,   f, indent=2)
    with open("data/fraud_dataset_test.json",  "w") as f: json.dump(test,    f, indent=2)

    print(f"\nSaved:")
    print(f"  data/fraud_dataset.json       ({len(dataset)} examples)")
    print(f"  data/fraud_dataset_train.json ({len(train)} train)")
    print(f"  data/fraud_dataset_test.json  ({len(test)} test)")

    print("\nSample HIGH example:")
    high = next(d for d in dataset if d["risk_level"] == "HIGH")
    print(f"  Input:  {high['input'][:120]}...")
    print(f"  Output: {high['output'][:120]}...")
