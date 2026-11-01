"""
backend/knowledge.py
The written fraud policy. Retrieved by CRAG, sent to Jev as the policy it
judges against, and exposed by the MCP server — so it must stay import-light.
"""

FRAUD_RULES = [
    "Structuring: Deliberately breaking large transactions into smaller ones below ₹50,000 to avoid reporting. Also called smurfing.",
    "Layering: Moving money through multiple accounts rapidly to obscure the source. Look for circular transfers.",
    "Late night transactions: Legitimate businesses rarely transact between 11pm and 4am. These warrant investigation.",
    "Round number transactions: Fraudsters often use round numbers like ₹10,000, ₹50,000, ₹1,00,000.",
    "New beneficiary + high amount: Adding a new payee and immediately sending a large amount is high risk.",
    "Transaction velocity: More than 10 transactions per account per day is unusual for retail customers.",
    "Unknown beneficiaries: Transfers to businesses with vague names like 'Unknown Co' or 'FastCash' are red flags.",
    "Rapid fund movement: Funds credited then immediately debited (within hours) suggests layering.",
    "Threshold avoidance: Amounts just below ₹50,000 (like ₹49,800 or ₹49,500) indicate structuring.",
    "Mule accounts: Accounts receiving money from many sources and forwarding to one destination.",
    "Hawala indicators: Cash-equivalent transfers without clear business purpose to informal networks.",
    "Invoice fraud: Duplicate invoices or invoices with slight variations to same beneficiary.",
    "Velocity abuse: Multiple transactions in a short time window from same account.",
    "Geographic anomaly: Transactions from unusual or previously unseen locations.",
    "Time clustering: Multiple transactions within minutes of each other from the same account.",
]
