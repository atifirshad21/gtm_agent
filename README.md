<div align="center">

# LangGraph GTM Agent

### AI-powered outbound sales — research, draft, learn, repeat.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Workflow-7C3AED?style=for-the-badge)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/LangChain-Agent-16A34A?style=for-the-badge)](https://langchain.com)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4-D97706?style=for-the-badge)](https://anthropic.com)

**Configure it for any business in under 5 minutes by editing a single file.**

[View Demo](#usage) · [Report Bug](https://github.com/atifirshad21/langgraph-gtm-agent/issues) · [Request Feature](https://github.com/atifirshad21/langgraph-gtm-agent/issues)

</div>

---

## About The Project

Most outbound sales workflows are a grind: open a tab, Google the company, check the CRM, think of an angle, write a draft, edit it, repeat. 15 minutes per lead, every lead.

This agent collapses that to under 60 seconds.

It reads new leads from Google Sheets, dispatches an AI research subagent to scrape websites and scan for news, drafts a personalized email, and waits for your approval — all from a single terminal command. When you edit a draft, it learns your writing style and applies it automatically to every future email.

> Inspired by [How LangChain built their GTM Agent](https://blog.langchain.com/how-we-built-langchains-gtm-agent/), which increased lead conversion by 250%.

---

## How It Works

```
Google Sheet  →  Dedup check  →  Research subagent  →  Draft  →  You review  →  CRM updated
 (new lead)       (auto)        (web + scrape + CRM)   (Claude)  (Send/Edit/Cancel)   (auto)
```

1. **Dedup check** — Skips leads already marked `contacted`. No accidental double-outreach.
2. **Research subagent** — A mini ReAct agent with three tools: website scraper, web search, CRM lookup. It adapts — if the website is down, it does more web searches. If it finds a funding round, it digs deeper.
3. **Email draft** — Claude writes a personalized email using research signals, relationship context (cold vs. warm), and your stored style preferences.
4. **Human review** — You see the draft, the agent's reasoning, and the signals that shaped it. Nothing sends without your explicit `[S]end`.
5. **Style learning** — When you edit and approve a revision, the agent diffs original vs. final and stores your preferences in SQLite. All future drafts apply them automatically.
6. **CRM update** — On send, the lead is marked `contacted` in Google Sheets.

---

## Built With

| Layer | Technology |
|-------|-----------|
| Workflow orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) — StateGraph with conditional edges |
| Research agent | [LangChain](https://langchain.com) — ReAct agent with tool use |
| LLM | [Claude Sonnet 4](https://anthropic.com) — drafting, learning, compaction |
| CRM | [Google Sheets](https://developers.google.com/sheets) via `gspread` |
| Web search | [Tavily API](https://tavily.com) — 1,000 free searches/month |
| Web scraping | [BeautifulSoup4](https://pypi.org/project/beautifulsoup4/) |
| Memory | SQLite — style preferences + draft history |
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
COMPANY_NAME = "Your Company"
COMPANY_DESCRIPTION = "We help [customers] solve [problem] by [solution]."
TARGET_PERSONAS  = "VP of Sales, Head of Ops, CTO"
PAIN_POINTS      = "- Problem 1\n- Problem 2"
GOOGLE_SHEET_NAME = "Your Sheet Name"
```

See [`example/config_saas.py`](example/config_saas.py) for a complete, ready-to-use configuration.

---

## Usage

```bash
python gtm_agent.py
```

The agent loads new leads from your sheet, runs research, and presents each draft for review:

```
═══ Acme Corp GTM Agent ═══
Found 3 new leads

┌──────────────────────────────────────────────────┐
│  To: Jane Smith (VP Sales) @ Acme Corp           │
│  Type: cold | Attempt: #1                        │
└──────────────────────────────────────────────────┘

Subject: Saw your API launch

Hi Jane — noticed Acme just shipped a new API layer.
[...]

🧠 Reasoning: Cold outreach, opportunity-first framing...
📊 Signals: api launch, series-b

Action:  [S]end  |  [E]dit  |  [C]ancel
```

**Commands:**
- `all` — process every new lead in sequence
- `1`, `2`, `3` — process a specific lead by number
- `compact` — consolidate redundant style preferences when memory grows stale

---

## Architecture

```
┌─────────────────────┐
│  Google Sheet (CRM) │
│  New lead detected  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Should we contact? │──── NO ───▶ Skip & log
│  (dedup check)      │
└─────────┬───────────┘
          │ YES
          ▼
┌─────────────────────────────────────────┐
│         Research Subagent               │
│  ┌──────────┐ ┌────────┐ ┌───────────┐  │
│  │ Website  │ │  Web   │ │    CRM    │  │
│  │ scraper  │ │ search │ │  lookup   │  │
│  └──────────┘ └────────┘ └───────────┘  │
│  AI decides which tools to use          │
│  and adapts if something fails          │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌──────────────────────┐
│  Classify lead type  │
│  cold / warm         │
└─────────┬────────────┘
          │
          ▼
┌─────────────────────┐
│  Draft email        │◀──── Stored style preferences
│  (Claude + memory)  │      from your past edits
└─────────┬───────────┘
          │
          ▼
┌──────────────────────────┐
│  Human review            │
│  [S]end [E]dit [C]ancel  │
└──┬───────┬───────┬───────┘
   │       │       │
   ▼       │       ▼
Update     │     Log &
 CRM       │     skip
           │
           ▼
       Redraft with
       feedback ──▶ Review again
```

### Key design patterns

**Subagent pattern** — Research is handled by a constrained ReAct agent with only three tools. It cannot draft emails or update the CRM — only gather intelligence. This keeps the research step adaptive without giving it too much surface area.

**Memory system** — When you approve an edited draft, Claude diffs the original against the final, extracts your implied style preferences, and stores them in SQLite. Future drafts apply these automatically — you shouldn't have to ask for the same change twice.

**Human-in-the-loop** — Every draft surfaces the agent's reasoning and the research signals that shaped it. Nothing sends without explicit approval.

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
| `GOOGLE_SHEET_NAME` | Name of the Google Sheet to read leads from |

**Using an example config:**
```bash
cp example/config_saas.py config.py
```

---

## Project Structure

```
langgraph-gtm-agent/
├── gtm_agent.py          # The entire agent — run this
├── config.py             # Your business config — edit this
├── example/
│   └── config_saas.py    # Ready-to-use SaaS example
├── credentials.json       # Google service account (not in repo)
├── .env                   # API keys (not in repo)
├── requirements.txt
└── README.md
```

---

## How Memory Works

```
You send an edited draft         Agent compares v1 vs. v2        Stored in SQLite
                                                                        │
Draft v1: "Hi Jane,              Claude extracts:                       ▼
 your team is growing..."  ───▶  • "Prefers casual tone"    Applied to ALL future drafts
                                 • "Shorter, under 50 words"
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

## Ideas for What to Build Next

- **Slack delivery** — Send drafts to Slack instead of terminal using the Slack SDK
- **Follow-up sequences** — Queue 2-3 follow-up emails automatically after the first
- **Lead scoring** — Score leads based on research signals before drafting
- **Multi-rep support** — Separate memory per rep (the DB schema already supports this)
- **Streamlit dashboard** — Web UI instead of terminal
- **LangSmith tracing** — Add observability to track agent decisions over time

---

## Author

**Atif Irshad** — GTM operator and builder exploring AI-powered sales workflows.

Built as a hands-on learning project after studying [LangChain's GTM Agent case study](https://blog.langchain.com/how-we-built-langchains-gtm-agent/).

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat&logo=linkedin)](https://linkedin.com/in/atifirshad21)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?style=flat&logo=github)](https://github.com/atifirshad21)
