# Case study: an auditable fraud-triage copilot

*What I learned building FinGuard AI, and what happened when my rules and my model disagreed.*

**Code:** https://github.com/Rishi-Is-Cool/Finguard · **Live demo:** `[paste your Space URL here once deployed — see week 4/README.md → Deploy]`

---

## The problem

Fraud and AML teams drown in alerts. Rules are cheap and explainable but noisy;
language models are better at judgement but inconsistent, expensive per call, and
hard to defend to an auditor. Supervisors and internal audit expect every alert
decision — raised, dismissed or escalated — to be documented and reproducible, so
*"the model said so"* is not an answer.

## What I built

A five-agent pipeline behind a streaming web UI:

1. **Extract** the uploaded transactions.
2. **Rules** — structuring, late-night timing, high-risk beneficiaries, account velocity — each flag tagged with the ruleset version and thresholds that produced it.
3. **Screen** every flagged transaction with Jev, a typed-output model that returns a verdict *and a calibrated confidence*. Confident verdicts are accepted; uncertain ones escalate to an LLM; overflow goes to a human queue.
4. **Retrieve** the relevant fraud policy with corrective RAG (hybrid BM25 + embeddings, cross-encoder reranking, query rewriting when retrieval is weak).
5. **Report** — an LLM writes the compliance summary.

Around it: a **hash-chained audit log** (each event carries the previous event's
SHA-256, so any edit is detectable), a **reviewer workflow** (confirm / false
positive / escalate, with notes), a **case-file export**, and an **MCP server** so
other AI agents can call the rules directly.

## Three things I learned

**1. The rules alone can't prioritise.** On a 200-transaction sample the rules
fired 227 times across 166 transactions — 83% of the file — and the aggregate risk
score pinned at its maximum. That is the real-world alert-fatigue problem in
miniature. The model layer earns its place by *disagreeing*: it downgraded a
₹49,800 payment the rules called structuring after noticing the description was an
EMI debit. So the product surfaces disagreements instead of hiding them, and routes
them to a person.

**2. LLM verdicts are opinions, so record them.** Two identical runs had the LLM
confirm 4 of 5 and then 3 of 5 of the same rule-HIGH transactions, at temperature 0.
That isn't fixable by prompting; it's a property of the tool. The defensible answer
is an audit trail that records *which* model gave *which* verdict at *what*
confidence — and a human decision on top.

**3. Deploying found a privacy bug the demo never showed.** The retrieval layer
wrote every request into one shared vector collection, so one user's transactions
could surface in another user's report. Invisible on a laptop with one user; serious
on a public URL. I reproduced it, fixed it with per-run collections that are deleted
afterwards, and added the reproduction to the write-up.

## Engineering choices

- **Cost-aware cascade.** Screening all 166 flagged transactions with Jev is
  estimated at ~$0.005 at published pricing; the LLM is spent only on the uncertain
  few, with the budget as a setting.
- **One container, one URL.** FastAPI serves the React build and the API; the image
  bakes in the model weights so cold starts don't download anything.
- **Built for a public link.** Upload and row caps, per-IP rate limiting that
  can't be bypassed by spoofing `X-Forwarded-For`, bounded memory, path-safe IDs.
- **Tested without API keys.** 42 tests, including the Jev client against the
  vendor's documented response shapes and the MCP server through a real client over
  stdio. CI builds the Docker image and boots it.

## What a production version needs

Reviewer identity from SSO rather than a typed name; the audit head hash anchored
somewhere the operator can't rewrite; persistent storage; confidence thresholds
tuned on labelled historical alerts; velocity measured per day rather than per file.

---

*Built by Rishikesh — I build RAG, agent and LLM-evaluation systems for fintech and
compliance teams. Get in touch: [your email / LinkedIn].*
