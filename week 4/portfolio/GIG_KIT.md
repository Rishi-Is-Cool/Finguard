# Gig kit — turning FinGuard into first clients

Everything below is built only from what FinGuard actually does. Don't add claims
you can't demo live. Replace `[brackets]` before posting.

**Your proof links**
- Code: https://github.com/Rishi-Is-Cool/Finguard
- Live demo (runs in ~1 min): `[deploy first — the URL the deploy script prints, with ?demo on the end]`
- Case study: `week 4/portfolio/CASE_STUDY.md` (publish it as a LinkedIn article or blog post)

---

## 1. Positioning

Pick one sentence and use it everywhere:

> I build RAG and AI-agent systems for fintech and compliance teams — the kind that
> show their work, so every automated decision can be reviewed and audited.

Why this niche: fraud/AML/compliance buyers have budget, a painful problem (alert
volume), and a hard requirement generic AI freelancers ignore (auditability). FinGuard
demonstrates exactly that requirement.

Adjacent gigs FinGuard also proves you can do: *RAG over company documents*, *LLM
agents with tool use*, *FastAPI backends for AI apps*, *fine-tuning a small model*,
*MCP servers*, *deploying an AI demo*.

---

## 2. Upwork profile

**Title** (pick one)
- AI Engineer — RAG, LLM Agents & Auditable AI for Fintech
- RAG & AI Agent Developer | FastAPI + React | Fintech & Compliance

**Overview**
> I build AI systems that have to be trusted: retrieval-augmented generation,
> multi-agent pipelines, and LLM features that record *why* they decided what they did.
>
> Recent work — FinGuard AI (live demo below): a fraud-triage copilot that runs
> deterministic rules, screens every flagged transaction with a confidence-scored
> model, escalates only uncertain cases to an LLM, retrieves policy with corrective
> RAG, and writes a compliance report. Every step lands in a tamper-evident audit
> log, and reviewers confirm or dismiss each case with one click.
>
> What I can build for you:
> • RAG over your documents, with retrieval you can evaluate — hybrid search, reranking, query rewriting
> • AI agents and tool-calling workflows (LangGraph, MCP servers)
> • FastAPI backends with streaming UIs, containerised and deployed
> • Fine-tuning small open models (QLoRA) when an API model isn't the right fit
>
> I ship with tests, a README a new engineer can follow, and a live demo link.
>
> Try it: [demo link] · Code: [GitHub link]

**Skills tags:** Retrieval Augmented Generation, LangChain, LangGraph, FastAPI, React,
Python, LLM Fine-Tuning, AI Agent Development, Docker, Hugging Face, Fraud Detection.

**Portfolio item:** title "FinGuard AI — auditable fraud triage", the
`docs/screenshots/report.png` image, and the first paragraph of the case study.

---

## 3. Service packages (Upwork Project Catalog / Fiverr / Contra)

Set prices by looking at 10 comparable listings and landing in the middle. Price
the first two or three jobs to win reviews, then raise them. Reviews are worth more
than margin at this stage.

| | **Starter** | **Standard** | **Advanced** |
|---|---|---|---|
| Offer | RAG chatbot over your documents | RAG + agent with tools, deployed | Auditable AI workflow |
| Includes | Ingestion, hybrid retrieval, a simple chat UI, README | + tool calls (APIs/DB), streaming UI, Docker, deployment to a URL | + decision log, human review step, evaluation set, tests + CI |
| Delivery | [5] days | [10] days | [3] weeks |
| Price | [$ ] | [$ ] | [$ ] |

Offer a paid **one-week pilot** for larger asks: a working prototype on their data
before they commit to a full build.

---

## 4. Proposal template

Keep it under 150 words. Lead with their problem, not your bio.

> Hi [name] — you need [restate their goal in one line, using their words].
>
> I recently built something close to this: FinGuard, a [RAG / agent / compliance]
> system that [the one feature that maps to their job]. You can run it in a minute
> here: [demo link] (it's public, on sample data).
>
> For your project I'd [2–3 concrete steps, e.g. "ingest your PDFs with hybrid search,
> add a reranker, and give you an evaluation set so you can see answer quality before
> launch"].
>
> One question so I scope it right: [one sharp question about their data or users].
>
> — Rishikesh

Tailoring rules: answer every question in the job post; mention one detail from it
that shows you read it; attach the case study only if they asked for past work.

---

## 5. LinkedIn launch post

> I spent 30 days building an AI fraud-triage system, and the most useful thing it
> taught me came from where my rules and my model *disagreed*.
>
> On 200 sample transactions my rules flagged 166. That's alert fatigue in miniature.
> The model layer earned its keep by pushing back, e.g. downgrading a ₹49,800 payment
> the rules called "structuring" because it was an EMI debit.
>
> What I built:
> → rules + a confidence-scored screener + LLM escalation only when uncertain
> → corrective RAG over the fraud policy
> → a tamper-evident audit trail and one-click human review
> → an MCP server so other AI agents can call the rules
>
> Deploying it also surfaced a privacy bug a demo never shows: users could see each
> other's data through a shared vector store. Fixed, and written up.
>
> Try it (1 min, sample data): [demo link]
> Code: [GitHub link]
>
> I'm taking on RAG and AI-agent projects, especially in fintech and compliance. DMs open.
>
> #AI #RAG #Fintech #Compliance #MachineLearning

Post with the `report.png` screenshot, or a 30-second screen recording of `?demo`
running. Video gets far more reach than a link.

---

## 6. Cold outreach

Target: fintechs, payment companies, NBFCs, compliance/regtech startups, and agencies
that build for them. Message the head of engineering, head of risk, or a founder.

**LinkedIn DM (under 300 characters)**
> Hi [name] — I build auditable AI for fraud/compliance workflows. Made a public demo
> that triages transactions and logs every decision for review: [demo link]. Would a
> 15-min look at how [company] handles alert volume be useful?

**Email**
> Subject: Cutting alert noise at [company] — 1-minute demo
>
> Hi [name],
>
> Teams like yours usually have more rule alerts than reviewers. I built a small
> system that screens every alert with a confidence-scored model, sends only the
> uncertain ones to an LLM or a person, and records each decision in a tamper-evident
> log. Demo on sample data: [demo link].
>
> If it's relevant, I could prototype the same approach on a slice of your
> [alerts / documents] in a week. Worth a short call?
>
> Rishikesh · [LinkedIn] · [GitHub]

Send 10 a day, personalised in the first line. Follow up once after 4–5 days. Stop there.

---

## 7. Where to find first gigs

- **Upwork searches:** "RAG", "LangChain", "LangGraph", "AI agent", "chatbot for documents",
  "FastAPI AI", "LLM fine-tuning", "MCP server", "fraud detection", "compliance AI".
  Filter: fixed-price, payment verified, fewer than 10 proposals, posted in the last 24h.
- **Contra / Fiverr:** publish the three packages above.
- **LinkedIn:** the launch post, then comment usefully on posts by fintech and risk leaders.
- **Communities:** Hugging Face, LangChain and MCP Discords have job/showcase channels.
  Share the demo where self-promotion is allowed.

---

## 8. Days 22–30 checklist

**Deployed**
- [ ] `hf auth login`, then `python deploy/hf_space.py --set-secrets`
- [ ] Build succeeds; the printed Space URL with `?demo` completes a run end to end
- [ ] Paste that URL into the root README, CASE_STUDY.md and GIG_KIT.md
- [ ] Open the demo on your phone once

**GitHub portfolio**
- [ ] Push to GitHub; CI goes green (backend, frontend, docker)
- [ ] Repo description + topics: `rag`, `llm`, `ai-agents`, `fraud-detection`, `fastapi`, `react`, `mcp`
- [ ] Pin the repo on your GitHub profile
- [ ] Fix the empty LoRA adapter repo on Hugging Face or delete it (see Week 3 README)

**First gigs live**
- [ ] Upwork profile + portfolio item
- [ ] Three packages published
- [ ] Case study published (LinkedIn article or blog)
- [ ] LinkedIn launch post with screenshot/video
- [ ] 5 tailored proposals a day
- [ ] 10 cold messages a day
