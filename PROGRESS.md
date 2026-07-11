# GTM Agent — Build Progress

> Reference for picking up where you left off. Update this after each session.

---

## What's Been Built

### Core agent pipeline (`gtm_agent.py`)
- **LangGraph StateGraph** — full pipeline with conditional edges and human-in-the-loop
- **Dedup check node** — skips leads already marked `contacted` in the sheet
- **Research subagent** — a constrained ReAct agent with three tools:
  - `scrape_website` — BeautifulSoup scraper, detects configurable signals from nav links
  - `research_search` — Tavily web search (3 results per query)
  - `lookup_crm` — reads the Google Sheet to find contacts at the same company
- **Lead scoring node** *(added July 2026)* — rubric-based, deterministic scoring:
  - LLM maps research findings to 6 signal categories via structured output (`with_structured_output`)
  - Score is calculated with fixed point values (not a raw LLM number)
  - Rubric: Funding +25, Hiring +20, Product launch +15, Tech alignment +15, Engagement +10, Negative signals -25, Base 15
  - Score shown color-coded in terminal (green ≥75, yellow ≥50, dim ≥25, red <25)
  - `LEAD_SCORE_THRESHOLD` in `config.py` auto-skips leads below the cutoff (default 0 = informational only)
- **Relationship classifier node** — cold vs. contacted_other_person
- **Email drafting node** — Claude writes personalized email using research + signals + style memory
- **Human review node** — terminal UI showing draft, reasoning, score breakdown; Send / Edit / Cancel
- **CRM update node** — marks lead `contacted` in Google Sheets on send
- **Style-learning memory** (SQLite):
  - `learn_from_edit()` — diffs original vs. edited draft, extracts preferences via LLM
  - `get_style_preferences()` — injects stored prefs into every future draft prompt
  - `compact_memories()` — consolidates redundant preferences (run via `compact` command)
  - Two tables: `style_preferences`, `draft_history`

### Configuration (`config.py`)
- Single file to customize: company description, target personas, pain points, email style guide
- `WEBSITE_SIGNAL_KEYWORDS` — what to look for when scraping
- `RESEARCH_SIGNAL_KEYWORDS` — what to extract from web search results as signals
- `LEAD_SCORE_THRESHOLD` — auto-skip threshold (0 = off)
- Example config: `example/config_saas.py`

### Infrastructure
- `requirements.txt` — all 13 dependencies listed and pinned with minimum versions
- `.gitignore` — credentials.json and .env excluded

---

## What Was Done This Session (July 2026)

1. **Added lead scoring node** between `research` and `classify` in the graph
   - `LeadSignals` Pydantic model for structured LLM output
   - `_calculate_score()` — deterministic math, not LLM-generated number
   - Score + breakdown shown during research step and again in human review
   - Auto-skip logic wired through conditional edge to `log_skip`

2. **Added draft quality evaluation node** between `draft` and `human_review`
   - `DraftQuality` Pydantic model: Personalization, Relevance, CTA softness (1–5 each)
   - Two-stage gate: rule checks first (free), then LLM scoring (structured output)
   - Rule checks: word count ≤100, subject ≤8 words, no generic phrases (12 blocked)
   - LLM scoring via `eval_llm.with_structured_output(DraftQuality)` — strict, not lenient
   - Auto-redrafts up to 2 times with targeted per-dimension feedback injected into the draft prompt
   - After 2 failed redrafts, passes to human with a warning banner instead of looping forever
   - `auto_redraft_count` kept separate from `attempt_number` so human edits don't pollute style learning

3. **Fixed `requirements.txt`** — was listing only 3 packages; now lists all 13

4. **Added `LEAD_SCORE_THRESHOLD`** to `config.py` with comment explaining usage

---

## What to Build Next

Listed roughly in order of portfolio impact vs. effort:

### High priority

- [x] **Draft quality evaluation node** *(done)*

- [x] **LangSmith tracing** *(done)*
  - `LANGSMITH_PROJECT` added to `config.py` (default: `"gtm-agent"`)
  - `gtm_agent.py` sets `LANGCHAIN_PROJECT` from config at startup if tracing is enabled
  - Startup banner shows `📡 LangSmith tracing active → project: gtm-agent` when on
  - `langsmith>=0.1.0` added to `requirements.txt`
  - `.env.example` created with all required + optional env vars documented
  - To enable: set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY=ls__...` in `.env`
  - Everything traces automatically — LLM calls, tool calls, node execution, latency, token counts

### Medium priority

- [x] **Richer relationship types** *(done)*
  - Five types now: `cold`, `inbound`, `referral`, `customer`, `contacted_other_person`, `follow_up`
  - `classify_relationship` reads optional `Source` column from the sheet (`inbound` / `referral` / `customer`)
  - Falls back to `cold` if column is absent or empty — fully backwards compatible
  - Each type has a distinct prompt angle in `draft_email`'s `relationship_guide`
  - Priority order: `follow_up` > `contacted_other_person` > `customer` > `inbound` > `referral` > `cold`

- [x] **Follow-up state machine** *(done)*
  - Status flow: `new` → `contacted` → (rep sets) `following_up` → `no_response`
  - `followup` command at the lead prompt loads all `following_up` leads into a separate queue
  - `make_initial_state(lead, is_followup=True)` flags the run; `classify_relationship` routes to `follow_up` type
  - `get_last_touch_date()` looks up the last send date from `draft_history` and injects it into the draft prompt
  - `update_crm` sets `no_response` (not `contacted`) after a follow-up send
  - Startup banner now shows both new leads count and follow-up queue size
  - Lead table shows `Source` column

- [x] **Memory viewer command** *(done)*
  - `memories` — Rich table of all stored preferences with ID, observation, example, date
  - `forget <id>` — deletes a single preference by ID
  - Both handled in the CLI input loop alongside `compact`

### Lower priority / stretch

- [ ] **Multi-rep support** — DB schema already supports `rep_name`; just need CLI prompt at startup ("Who's running this? [default]")
- [ ] **Streamlit dashboard** — web UI alternative to terminal; shows leads table, let you click to process
- [ ] **Slack delivery** — post draft to a Slack channel instead of terminal; rep reacts with ✅/✏️/❌ to trigger send/edit/cancel
- [x] **Parallel research tools** *(done)*
  - Replaced sequential ReAct subagent with `ThreadPoolExecutor(max_workers=3)`
  - `scrape_website`, `research_search`, `lookup_crm` all fire simultaneously
  - Results merged and passed to `synthesis_llm` for a structured summary
  - Removed `create_react_agent` import (no longer needed)
  - Output format identical to before — downstream nodes unchanged

---

## Known Issues / Tech Debt

- Model name `claude-sonnet-4-20250514` is hardcoded in 3 places; should be a single constant in `config.py`
- `check_should_contact` sets `should_contact = False` but `make_initial_state` now sets it `True` — these should be consistent (currently works because the check node always overwrites the value)
- JSON parsing in `learn_from_edit` and `compact_memories` strips ``` manually; should use `with_structured_output` for reliability
- ~~No `.env.example` file~~ *(fixed — `.env.example` created)*

---

## Architecture Diagram (current state)

```
Google Sheet (new leads)
        │
        ▼
check_should_contact ── contacted ──▶ log_skip ──▶ END
        │
      new
        │
        ▼
    research
  (ReAct subagent:
   scrape + search + CRM)
        │
        ▼
    score_lead
  (LeadSignals structured output
   → deterministic rubric 0–100)
        │
     below           at/above
   threshold ──────── threshold
        │                  │
        ▼                  ▼
    log_skip           classify
      END            (cold / warm)
                          │
                          ▼
                        draft ◀──────────────────────┐
                   (Claude + memory                   │
                    + style prefs                     │
                    + eval feedback)                  │
                          │                           │
                          ▼                           │
                   evaluate_draft                     │
                  (rule checks +               fail + budget
                   LLM scoring)                remaining
                    /        \                        │
                 pass      fail + budget ─────────────┘
                   │         exhausted
                   │              │
                   │              ▼  (warning shown)
                   └──────▶ human_review
                           [S]end [E]dit [C]ancel
                            /       |        \
                           ▼        ▼         ▼
                      update_crm  draft    log_cancel
                         END    (human      END
                                 loop)
```
