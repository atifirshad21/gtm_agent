# LangGraph GTM Agent

An open-source, AI-powered outbound sales agent built with LangChain, LangGraph, and Claude. It researches leads, drafts personalized emails, and learns from your edits over time.

**Configure it for any business in under 5 minutes** by editing a single file (`config.py`).

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![LangChain](https://img.shields.io/badge/LangChain-latest-green)
![LangGraph](https://img.shields.io/badge/LangGraph-latest-purple)
![Claude](https://img.shields.io/badge/LLM-Claude_Sonnet_4-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## What it does

```
Google Sheet     →    Research     →    Draft     →    You review     →    CRM updated
(new lead)           (AI agent)       (Claude)      (Send/Edit/Cancel)   (auto)
```

Instead of spending 15 minutes per lead toggling between tabs, the agent does it in under 60 seconds:

1. **Checks contact history** — prevents duplicate outreach automatically
2. **Researches the company** — scrapes their website, searches for news, finds relevant signals
3. **Drafts a personalized email** — different strategies for cold vs. warm leads
4. **You review** — Send, Edit (with feedback), or Cancel. Nothing sends without your approval
5. **Learns from your edits** — remembers your style preferences for future drafts
6. **Updates your CRM** — marks leads as "contacted" in Google Sheets

Inspired by [How LangChain built their GTM Agent](https://blog.langchain.com/how-we-built-langchains-gtm-agent/) which increased lead conversion by 250%.

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/langgraph-gtm-agent.git
cd langgraph-gtm-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Add your API keys

```bash
cp .env.example .env
# Edit .env with your keys
```

You need:
- **Anthropic API key** → [console.anthropic.com](https://console.anthropic.com)
- **Tavily API key** → [tavily.com](https://tavily.com) (free: 1000 searches/month)
- **Google Sheets service account** → [console.cloud.google.com](https://console.cloud.google.com) (enable Sheets + Drive APIs)

### 3. Set up your Google Sheet

Create a sheet with these columns:

| Lead ID | Company | Company URL | Contact Name | Title | Email | Status |
|---------|---------|-------------|-------------|-------|-------|--------|
| 1 | Acme Corp | https://acme.com | Jane Smith | VP Sales | jane@acme.com | new |

Share the sheet with your service account email.

### 4. Configure for your business

Edit `config.py` — this is the only file you need to customize:

```python
COMPANY_NAME = "Your Company"
COMPANY_DESCRIPTION = "We help [customers] solve [problem] by [solution]."
TARGET_PERSONAS = "VP of Sales, Head of Ops, CTO"
PAIN_POINTS = "- Problem 1\n- Problem 2"
```

See `examples/` for complete configs for SaaS, fashion, and recruiting.

### 5. Run

```bash
python gtm_agent.py
```

---

## Architecture

```
┌─────────────────────┐
│  Google Sheet (CRM)  │
│  New lead detected   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Should we contact?  │──── NO ───▶ Skip & log
│  (history check)     │
└─────────┬───────────┘
          │ YES
          ▼
┌─────────────────────────────────────────┐
│         Research Subagent                │
│  ┌──────────┐ ┌────────┐ ┌───────────┐ │
│  │ Website  │ │ Web    │ │ CRM       │ │
│  │ scraper  │ │ search │ │ lookup    │ │
│  └──────────┘ └────────┘ └───────────┘ │
│  AI decides which tools to use          │
│  and adapts if something fails          │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────┐
│  Classify relationship│
│  cold / warm          │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Draft email          │◀──── Style preferences
│  (Claude + memory)    │      from past edits
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Human review         │
│  [S]end [E]dit [C]ancel│
└──┬──────┬──────┬────┘
   │      │      │
   ▼      │      ▼
 Update   │    Log &
 CRM      │    skip
           │
           ▼
      Redraft with
      feedback ──▶ Review again
```

### Key patterns

**Subagent pattern** — The research step uses a mini AI agent with constrained tools. Unlike a fixed script, it adapts: if a website is down, it does extra web searches. If it finds a funding round, it digs deeper. But it can only research — it can't draft emails or update the CRM.

**Memory system** — When you edit a draft and approve the revision, the agent compares the original against the final, extracts your style preferences, and stores them in SQLite. Future drafts automatically apply your preferences.

**Human-in-the-loop** — Nothing sends without your explicit approval. Every draft shows the agent's reasoning and the research signals that informed it.

---

## Configuration reference

Everything is in `config.py`:

| Setting | What it does |
|---------|-------------|
| `COMPANY_NAME` | Your company name (shown in terminal and used in prompts) |
| `COMPANY_DESCRIPTION` | 2-3 sentences about what you do (injected into email drafting) |
| `TARGET_PERSONAS` | Job titles you're targeting (helps the agent match tone) |
| `PAIN_POINTS` | Problems you solve (gives the agent outreach angles) |
| `EMAIL_STYLE_GUIDE` | Rules for how emails should be written |
| `WEBSITE_SIGNAL_KEYWORDS` | What to look for when scraping websites |
| `RESEARCH_SIGNAL_KEYWORDS` | What to flag from web search results |
| `GOOGLE_SHEET_NAME` | Name of your Google Sheet |

### Example configs

| Industry | File | What it targets |
|----------|------|----------------|
| SaaS | `examples/config_saas.py` | Product analytics for SaaS companies |
| Fashion | `examples/config_fashion.py` | Recommerce for fashion brands |
| Recruiting | `examples/config_recruiting.py` | AI recruiting for scaling startups |

To use an example: `cp examples/config_saas.py config.py`

---

## Project structure

```
langgraph-gtm-agent/
├── gtm_agent.py          # The entire agent (run this)
├── config.py              # Your business config (edit this)
├── examples/
│   ├── config_saas.py     # Example: SaaS analytics company
│   ├── config_fashion.py  # Example: Fashion recommerce
│   └── config_recruiting.py # Example: Recruiting tech
├── credentials.json       # Google Sheets auth (not in repo)
├── .env                   # API keys (not in repo)
├── .env.example           # Template for API keys
├── .gitignore
├── requirements.txt
└── README.md
```

---

## How the memory works

```
Draft v1                     You edit                    Draft v2
"Hi Jane, I noticed          "Make it shorter            "Hi Jane, saw your
your team is growing         and more casual"            new API launch..."
rapidly..."                        │
                                   ▼
                          Agent compares v1 vs v2
                                   │
                                   ▼
                          Extracts preferences:
                          • "Prefers casual tone"
                          • "Shorter emails (~50 words)"
                                   │
                                   ▼
                          Stored in SQLite ──▶ Applied to ALL future drafts
```

View your stored preferences:
```bash
sqlite3 agent_memory.db "SELECT * FROM style_preferences;"
```

Compact redundant preferences:
```
Lead # to process: compact
Compacted 12 preferences → 6
```

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| Workflow engine | LangGraph (StateGraph with conditional edges) |
| Agent framework | LangChain (ReAct agent with tools) |
| LLM | Claude Sonnet 4 (Anthropic API) |
| CRM | Google Sheets (gspread) |
| Web research | Tavily API |
| Web scraping | BeautifulSoup4 |
| Memory | SQLite |
| Terminal UI | Rich |

---

## Extending

Some ideas for what to build next:

- **Slack delivery** — Send drafts to Slack instead of terminal using the Slack SDK
- **Follow-up sequences** — Queue 2-3 follow-up emails after the first one
- **Lead scoring** — Score leads based on research signals before drafting
- **Multi-rep support** — Separate memory per rep name (already supported in the DB schema)
- **Streamlit dashboard** — Build a web UI instead of terminal
- **LangSmith tracing** — Add observability to track agent performance

---

## Built by

[Atif Irshad](https://linkedin.com/in/atifirshad) — GTM operator and builder exploring AI-powered sales workflows.

Built as a hands-on learning project after studying [LangChain's GTM Agent case study](https://blog.langchain.com/how-we-built-langchains-gtm-agent/).

---

## License

MIT — use it, modify it, ship it.