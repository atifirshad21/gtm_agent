<div align="center">

# LangGraph GTM Agent

### AI-powered outbound sales — research, score, draft, evaluate, learn, repeat.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Workflow-7C3AED?style=for-the-badge)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/LangChain-Agent-16A34A?style=for-the-badge)](https://langchain.com)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4-D97706?style=for-the-badge)](https://anthropic.com)
[![LangSmith](https://img.shields.io/badge/LangSmith-Tracing-FF6B35?style=for-the-badge)](https://smith.langchain.com)

**Configure it for any business in under 5 minutes by editing a single file.**

[View Demo](#usage) · [Report Bug](https://github.com/atifirshad21/langgraph-gtm-agent/issues) · [Request Feature](https://github.com/atifirshad21/langgraph-gtm-agent/issues)

</div>

---

## About The Project

Most outbound sales workflows are a grind: open a tab, Google the company, check the CRM, think of an angle, write a draft, edit it, repeat. 15 minutes per lead, every lead.

This agent collapses that to under 60 seconds — and gets smarter every time you use it.

It reads new leads from Google Sheets, scores them by research signal strength, dispatches an AI research subagent to scrape websites and scan for news, drafts a personalized email, runs it through an automated quality gate, and waits for your approval. When you edit a draft, it learns your writing style and applies it automatically to every future email.

> Inspired by [How LangChain built their GTM Agent](https://blog.langchain.com/how-we-built-langchains-gtm-agent/), which increased lead conversion by 250%.

---

## How It Works

```
Google Sheet → Dedup check → Research → Score → Classify → Draft → Quality eval → You review → CRM updated
  (new lead)     (auto)     (subagent) (0-100) (cold/warm) (Claude)  (auto-redraft)  (Send/Edit/Cancel)  (auto)
```

1. **Dedup check** — Skips leads already marked `contacted`. No accidental double-outreach.
2. **Research subagent** — A mini ReAct agent with three tools: website scraper, web search, CRM lookup. Adapts if a tool fails.
3. **Lead scoring** — Scores each lead 0–100 using a fixed rubric applied to research findings. Funding rounds, hiring signals, product launches, tech alignment, engagement activity, and negative signals each carry defined point values. The LLM maps findings to categories; the math is deterministic. Leads below your configured threshold are auto-skipped.
4. **Relationship classifier** — Detects if someone else at the same company has already been contacted and adjusts the draft angle accordingly.
5. **Email draft** — Claude writes a personalized email using research signals, relationship context, and your stored style preferences.
6. **Quality evaluation** — Before you ever see the draft, it passes through a two-stage gate: rule-based checks (word count, subject length, generic phrase detection) followed by LLM scoring on Personalization, Relevance, and CTA softness. Failures trigger automatic redrafts with targeted feedback — up to 2 attempts before handing off to you.
7. **Human review** — You see the draft, lead score, quality scores, agent reasoning, and the signals that shaped it. Nothing sends without your explicit `[S]end`.
8. **Style learning** — When you edit and approve a revision, the agent diffs original vs. final, extracts your implied style preferences, and stores them in SQLite. All future drafts apply them automatically.
9. **CRM update** — On send, the lead is marked `contacted` in Google Sheets.

---

## Built With

| Layer | Technology |
|-------|-----------|
| Workflow orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) — StateGraph with conditional edges |
| Research agent | [LangChain](https://langchain.com) — ReAct agent with tool use |
| LLM | [Claude Sonnet 4](https://anthropic.com) — drafting, scoring, evaluation, learning |
| CRM | [Google Sheets](https://developers.google.com/sheets) via `gspread` |
| Web search | [Tavily API](https://tavily.com) — 1,000 free searches/month |
| Web scraping | [BeautifulSoup4](https://pypi.org/project/beautifulsoup4/) |
| Memory | SQLite — style preferences + draft history |
| Observability | [LangSmith](https://smith.langchain.com) — optional tracing |
| Terminal UI | [Rich](https://github.com/Textualize/rich) |

---

## Getting Started

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com)
- A [Tavily API key](https://tavily.com) (free tier: 1,000 searches/month)
- A Google Cloud project with Sheets + Drive APIs enabled and a service account JSON downloaded

### Installation

```bash
git clone https://github.com/atifirshad21/langgraph-gtm-agent.git
cd langgraph-gtm-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 1. Add your API keys

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```env
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
```

Place your Google service account JSON at the root as `credentials.json`.

### 2. Set up your Google Sheet

Create a sheet with these columns and share it with your service account email:

| Lead ID | Company | Company URL | Contact Name | Title | Email | Status |
|---------|---------|-------------|--------------|-------|-------|--------|
| 1 | Acme Corp | https://acme.com | Jane Smith | VP Sales | jane@acme.com | new |

Set `Status` to `new` for any lead you want the agent to process.

### 3. Configure for your business

Edit `config.py` — the only file you need to customize:

```python
COMPANY_NAME        = "Your Company"
COMPANY_DESCRIPTION = "We help [customers] solve [problem] by [solution]."
TARGET_PERSONAS     = "VP of Sales, Head of Ops, CTO"
PAIN_POINTS         = "- Problem 1\n- Problem 2"
GOOGLE_SHEET_NAME   = "Your Sheet Name"
LEAD_SCORE_THRESHOLD = 0   # auto-skip leads below this score (0 = off)
LANGSMITH_PROJECT   = "gtm-agent"  # project name if using LangSmith
```

See [`example/config_saas.py`](example/config_saas.py) for a complete, ready-to-use configuration.

---

## Usage

```bash
python3 gtm_agent.py
```

The agent loads new leads, runs research and scoring, evaluates drafts automatically, and presents each for review:

```
═══ Acme Corp GTM Agent ═══
📡 LangSmith tracing active → project: gtm-agent

Found 3 new leads

┌─────────────────────────────────────────────────────────────────┐
│  To: Jane Smith (VP Sales) @ Acme Corp                          │
│  Email: jane@acme.com                                           │
│  Type: cold | Attempt: #1 | Score: 75/100                       │
└─────────────────────────────────────────────────────────────────┘

Subject: Saw your API launch

Hi Jane — noticed Acme just shipped a new API layer. [...]

🧠 Reasoning: Cold outreach, opportunity-first framing...
📊 Score breakdown: Funding signals (+25)  Product launch (+15)  Tech alignment (+15)
🔍 Research signals: funding, api launch

Action:  [S]end  |  [E]dit  |  [C]ancel
```

**Commands:**
- `all` — process every new lead in sequence
- `1`, `2`, `3` — process a specific lead by number
- `compact` — consolidate redundant style preferences when memory grows stale

---

## Architecture

```
┌─────────────────────────────────┐
│     Google Sheet (new leads)    │
└──────────────┬──────────────────┘
               │
               ▼
┌──────────────────────────┐
│   Should we contact?     │── contacted ──▶ Skip & log
│   (dedup check)          │
└──────────────┬───────────┘
               │ new
               ▼
┌─────────────────────────────────────────┐
│           Research Subagent             │
│  ┌──────────┐ ┌────────┐ ┌───────────┐  │
│  │ Website  │ │  Web   │ │    CRM    │  │
│  │ scraper  │ │ search │ │  lookup   │  │
│  └──────────┘ └────────┘ └───────────┘  │
│  ReAct agent — adapts if tools fail     │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│           Lead Scoring               │
│  LLM maps research → signal cats     │
│  Deterministic math → score 0–100    │
│  Funding +25 | Hiring +20            │
│  Product launch +15 | Tech +15       │
│  Engagement +10 | Negative -25       │
└──────────┬──────────────┬────────────┘
        below           above
      threshold       threshold
           │               │
           ▼               ▼
        Skip           Classify
                     cold / warm
                           │
                           ▼
               ┌───────────────────────┐
               │     Draft Email       │◀── Style preferences
               │  (Claude + memory     │◀── Eval feedback (if redraft)
               │   + eval feedback)    │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │   Quality Evaluation  │
               │  1. Rule checks       │
               │     · ≤100 words      │
               │     · subject ≤8 wds  │
               │     · no clichés      │
               │  2. LLM scoring 1–5   │
               │     · Personalization │
               │     · Relevance       │
               │     · CTA softness    │
               └──┬──────────────┬─────┘
               pass           fail
                  │         (≤2 retries)
                  │              │
                  │              ▼
                  │          Redraft with
                  │          feedback ──────┐
                  │                        │ (loop)
                  │          fail          │
                  │       (budget out) ────┘
                  │              │
                  └──────────────▼
               ┌───────────────────────────┐
               │       Human Review        │
               │  Draft + score + signals  │
               │  [S]end [E]dit [C]ancel   │
               └──┬──────────┬──────────┬──┘
                  │          │          │
                  ▼          ▼          ▼
            Update CRM   Redraft     Cancel
            (contacted)  (human)
```

### Key design patterns

**Rubric-based lead scoring** — Instead of asking the LLM to invent a number, the agent defines fixed point values per signal category and has the LLM only identify which signals are present. The score is reproducible and auditable.

**Two-stage quality gate** — Rule checks run first (free, instant). Only drafts that pass rules go to the LLM evaluator. Failed drafts receive targeted per-dimension feedback injected directly into the next draft prompt.

**Subagent pattern** — Research is handled by a constrained ReAct agent with only three tools. It cannot draft emails or update the CRM — only gather intelligence.

**Memory system** — When you approve an edited draft, Claude diffs the original against the final, extracts your implied style preferences, and stores them in SQLite. Future drafts apply these automatically.

**Human-in-the-loop** — Every draft surfaces the lead score, quality scores, agent reasoning, and the research signals that shaped it. Nothing sends without explicit approval.

---

## Configuration Reference

All settings live in `config.py`:

| Setting | What it does |
|---------|-------------|
| `COMPANY_NAME` | Used in terminal output and injected into prompts |
| `COMPANY_DESCRIPTION` | 2-3 sentences about what you do — the core of the draft prompt |
| `TARGET_PERSONAS` | Job titles you target; helps the agent calibrate tone |
| `PAIN_POINTS` | Problems you solve; gives the agent outreach angles |
| `EMAIL_STYLE_GUIDE` | Hard rules for how emails should be written |
| `WEBSITE_SIGNAL_KEYWORDS` | What to look for when scraping company websites |
| `RESEARCH_SIGNAL_KEYWORDS` | What to flag from web search results as signals |
| `LEAD_SCORE_THRESHOLD` | Auto-skip leads below this score (0 = off, informational only) |
| `LANGSMITH_PROJECT` | LangSmith project name for tracing (enable via `.env`) |
| `GOOGLE_SHEET_NAME` | Name of the Google Sheet to read leads from |

---

## Optional: LangSmith Tracing

Enable full observability — node-by-node latency, token usage, LLM inputs/outputs, tool calls — for every agent run.

1. Sign up free at [smith.langchain.com](https://smith.langchain.com)
2. Add to your `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
```

The project name is set in `config.py` (`LANGSMITH_PROJECT`). Everything else traces automatically.

---

## How Memory Works

```
You send an edited draft        Agent compares v1 vs. v2       Stored in SQLite
                                                                      │
Draft v1: "Hi Jane,             Claude extracts:                      ▼
 your team is growing..."  ───▶ · "Prefers casual tone"   Applied to ALL future drafts
                                · "Shorter, under 50 words"
Draft v2: "Hi Jane,
 saw your new API launch..."
```

View stored preferences:
```bash
sqlite3 agent_memory.db "SELECT * FROM style_preferences;"
```

Compact redundant preferences when they accumulate:
```
Lead # to process: compact
Compacted 12 preferences → 6
```

---

## Project Structure

```
langgraph-gtm-agent/
├── gtm_agent.py          # The entire agent — run this
├── config.py             # Your business config — edit this
├── example/
│   └── config_saas.py    # Ready-to-use SaaS example
├── PROGRESS.md           # Build log and next steps
├── .env.example          # Copy to .env and fill in keys
├── credentials.json      # Google service account (not in repo)
├── .env                  # API keys (not in repo)
├── requirements.txt
└── README.md
```

---

## Author

**Atif Irshad** — GTM operator and builder exploring AI-powered sales workflows.

Built as a hands-on learning project after studying [LangChain's GTM Agent case study](https://blog.langchain.com/how-we-built-langchains-gtm-agent/).

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat&logo=linkedin)](https://linkedin.com/in/atifirshad21)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?style=flat&logo=github)](https://github.com/atifirshad21)
