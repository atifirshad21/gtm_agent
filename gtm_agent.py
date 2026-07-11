"""
LangGraph GTM Agent — AI-Powered Outbound Sales Agent
Built with LangChain, LangGraph, and Claude

An open-source GTM agent that researches leads, drafts personalized outreach
emails, and learns from your edits over time.

Inspired by: https://blog.langchain.com/how-we-built-langchains-gtm-agent/

Run: python gtm_agent.py
"""

import os
import json
import sqlite3
from typing import TypedDict
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import gspread
import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, END
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
console = Console()


# ═══════════════════════════════════════════
# CONFIGURATION — Customize for your business
# ═══════════════════════════════════════════
# Edit config.py to set your company info,
# outreach style, and research signals.

from config import (
    COMPANY_NAME,
    COMPANY_DESCRIPTION,
    TARGET_PERSONAS,
    PAIN_POINTS,
    EMAIL_STYLE_GUIDE,
    RESEARCH_SIGNAL_KEYWORDS,
    WEBSITE_SIGNAL_KEYWORDS,
    GOOGLE_SHEET_NAME,
    LEAD_SCORE_THRESHOLD,
    LANGSMITH_PROJECT,
)

# LangSmith: wire project name from config; tracing activates automatically
# when LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY are set in .env
if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
    os.environ.setdefault("LANGCHAIN_PROJECT", LANGSMITH_PROJECT)


# ═══════════════════════════════════════════
# CONNECTIONS (Google Sheets + LLM + Search)
# ═══════════════════════════════════════════

scopes = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
gc = gspread.authorize(creds)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0.3)


# ═══════════════════════════════════════════
# LEAD SCORING — Rubric-based signal detection
# ═══════════════════════════════════════════

class LeadSignals(BaseModel):
    funding_detected: bool = Field(description="Recent funding round, Series A/B/C/D, raised capital, investment announced")
    funding_evidence: str = Field(default="", description="One-line evidence, empty if not detected")
    hiring_detected: bool = Field(description="Job postings, team expansion, scaling headcount, hiring spree")
    hiring_evidence: str = Field(default="", description="One-line evidence, empty if not detected")
    product_launch_detected: bool = Field(description="New product, major feature launch, expansion to new market, rebrand")
    product_launch_evidence: str = Field(default="", description="One-line evidence, empty if not detected")
    tech_alignment_detected: bool = Field(description="Technology or use-case signals that suggest a fit with our offering")
    tech_alignment_evidence: str = Field(default="", description="One-line evidence, empty if not detected")
    engagement_detected: bool = Field(description="Recent blog posts, conference appearances, webinars, public thought leadership")
    engagement_evidence: str = Field(default="", description="One-line evidence, empty if not detected")
    negative_detected: bool = Field(description="Layoffs, hiring freeze, budget cuts, pivoting away, company struggling or shutting down")
    negative_evidence: str = Field(default="", description="One-line evidence, empty if not detected")


# Fixed point values — score is deterministic once signals are mapped
_SIGNAL_POINTS = {
    "funding":         25,
    "hiring":          20,
    "product_launch":  15,
    "tech_alignment":  15,
    "engagement":      10,
    "negative":       -25,
}
_BASE_SCORE = 15  # every lead starts here


def _calculate_score(signals: LeadSignals) -> tuple[int, dict]:
    score = _BASE_SCORE
    breakdown = {}

    checks = [
        ("funding",        signals.funding_detected,        signals.funding_evidence,        "+25"),
        ("hiring",         signals.hiring_detected,         signals.hiring_evidence,         "+20"),
        ("product_launch", signals.product_launch_detected, signals.product_launch_evidence, "+15"),
        ("tech_alignment", signals.tech_alignment_detected, signals.tech_alignment_evidence, "+15"),
        ("engagement",     signals.engagement_detected,     signals.engagement_evidence,     "+10"),
        ("negative",       signals.negative_detected,       signals.negative_evidence,       "-25"),
    ]

    labels = {
        "funding":         "Funding signals",
        "hiring":          "Hiring / growth",
        "product_launch":  "Product launch",
        "tech_alignment":  "Tech alignment",
        "engagement":      "Engagement",
        "negative":        "Negative signals",
    }

    for key, detected, evidence, pts in checks:
        if detected:
            score += _SIGNAL_POINTS[key]
            label = labels[key]
            breakdown[label] = f"{pts} pts — {evidence}" if evidence else f"{pts} pts"

    return max(0, min(100, score)), breakdown


scoring_llm = ChatAnthropic(
    model="claude-sonnet-4-20250514", temperature=0
).with_structured_output(LeadSignals)


# ═══════════════════════════════════════════
# DRAFT QUALITY EVALUATION
# ═══════════════════════════════════════════

class DraftQuality(BaseModel):
    personalization_score: int = Field(ge=1, le=5, description="1-5: how specific is the email to this company/person? 5=very specific, 1=generic template")
    personalization_feedback: str = Field(description="What's missing or what's good")
    relevance_score: int = Field(ge=1, le=5, description="1-5: how well does the angle match what we know about their needs?")
    relevance_feedback: str = Field(description="Brief feedback on the angle chosen")
    cta_score: int = Field(ge=1, le=5, description="1-5: how soft and low-pressure is the call to action? 5=curious/conversational, 1=pushy/aggressive")
    cta_feedback: str = Field(description="Brief feedback on the CTA")
    passes_quality: bool = Field(description="True only if all three scores are 3 or above and no major issues exist")
    rewrite_instructions: str = Field(default="", description="Specific, actionable fix instructions if passes_quality is False. Empty if passing.")


_QUALITY_THRESHOLD = 3       # minimum score per dimension to pass
_MAX_AUTO_REDRAFTS = 2       # max automatic redraft cycles before handing off to human regardless

_GENERIC_PHRASES = [
    "i hope this finds you well",
    "i hope you're doing well",
    "i wanted to reach out",
    "touching base",
    "circle back",
    "synergy",
    "leverage",
    "game-changer",
    "revolutionary",
    "best-in-class",
    "quick win",
    "low-hanging fruit",
]


def _rule_checks(subject: str, body: str) -> list[str]:
    """Fast, free checks before spending an LLM call on quality eval."""
    issues = []
    word_count = len(body.split())
    if word_count > 100:
        issues.append(f"Body is {word_count} words — must be under 100. Cut aggressively.")
    if len(subject.split()) > 8:
        issues.append(f"Subject is {len(subject.split())} words — keep it under 8 words.")
    body_lower = body.lower()
    for phrase in _GENERIC_PHRASES:
        if phrase in body_lower:
            issues.append(f"Contains generic phrase '{phrase}' — replace with something specific to the research.")
    return issues


eval_llm = ChatAnthropic(
    model="claude-sonnet-4-20250514", temperature=0
).with_structured_output(DraftQuality)


# ═══════════════════════════════════════════
# MEMORY SYSTEM
# ═══════════════════════════════════════════

def init_db():
    """Create the SQLite database and tables if they don't exist."""
    conn = sqlite3.connect("agent_memory.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS style_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rep_name TEXT DEFAULT 'default',
            observation TEXT,
            example TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS draft_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            contact_name TEXT,
            original_draft TEXT,
            final_draft TEXT,
            action TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def get_style_preferences(rep_name: str = "default") -> str:
    """Load stored style preferences to inject into the draft prompt."""
    conn = init_db()
    rows = conn.execute(
        "SELECT observation, example FROM style_preferences WHERE rep_name = ? "
        "ORDER BY created_at DESC LIMIT 15",
        (rep_name,)
    ).fetchall()
    conn.close()

    if not rows:
        return "No style preferences recorded yet. Write naturally."

    prefs = "\n".join([f"- {r[0]} (e.g., {r[1]})" for r in rows])
    return f"""YOUR STYLE PREFERENCES (learned from past edits — apply these automatically):
{prefs}

The rep should NOT need to make the same edits again."""


def learn_from_edit(original_draft: str, edited_draft: str, rep_name: str = "default"):
    """Analyze the diff between original and edited draft, store observations."""
    analysis_llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)

    prompt = f"""Compare these two email drafts. The rep edited the original.
Identify specific style preferences — what they changed and what it implies.

ORIGINAL:
{original_draft}

EDITED:
{edited_draft}

Return a JSON array of observations. Only substantive changes, not typo fixes:
[{{"observation": "Prefers shorter subject lines under 5 words", "example": "Changed 'Exploring Solutions for Your Team' to 'Quick idea'"}}]

Valid JSON only, no other text."""

    result = analysis_llm.invoke(prompt)
    try:
        text = result.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        observations = json.loads(text)
    except json.JSONDecodeError:
        console.print("[red]Could not parse style observations[/red]")
        return []

    conn = init_db()
    for obs in observations:
        conn.execute(
            "INSERT INTO style_preferences (rep_name, observation, example) VALUES (?, ?, ?)",
            (rep_name, obs["observation"], obs.get("example", ""))
        )
    conn.commit()
    conn.close()

    console.print(f"[bold green]🧠 Learned {len(observations)} style preference(s) from your edit[/bold green]")
    for obs in observations:
        console.print(f"[dim]   → {obs['observation']}[/dim]")

    return observations


def log_draft(company: str, contact_name: str, original: str, final: str, action: str):
    """Log every draft and what happened to it."""
    conn = init_db()
    conn.execute(
        "INSERT INTO draft_history (company, contact_name, original_draft, final_draft, action) "
        "VALUES (?, ?, ?, ?, ?)",
        (company, contact_name, original, final, action)
    )
    conn.commit()
    conn.close()


def compact_memories(rep_name: str = "default"):
    """Consolidate redundant preferences. Run this when memory gets bloated."""
    conn = init_db()
    rows = conn.execute(
        "SELECT id, observation, example FROM style_preferences WHERE rep_name = ?",
        (rep_name,)
    ).fetchall()

    if len(rows) < 10:
        console.print(f"[dim]Only {len(rows)} preferences stored — no compaction needed yet[/dim]")
        return

    all_prefs = "\n".join([f"- {r[1]} ({r[2]})" for r in rows])
    compact_llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)

    prompt = f"""Consolidate these preferences into 5-8 non-redundant ones:

{all_prefs}

Return JSON array: [{{"observation": "...", "example": "..."}}]
Valid JSON only."""

    result = compact_llm.invoke(prompt)
    try:
        text = result.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        consolidated = json.loads(text)
    except json.JSONDecodeError:
        return

    conn.execute("DELETE FROM style_preferences WHERE rep_name = ?", (rep_name,))
    for obs in consolidated:
        conn.execute(
            "INSERT INTO style_preferences (rep_name, observation, example) VALUES (?, ?, ?)",
            (rep_name, obs["observation"], obs.get("example", ""))
        )
    conn.commit()
    conn.close()
    console.print(f"[green]Compacted {len(rows)} preferences → {len(consolidated)}[/green]")


# ═══════════════════════════════════════════
# RESEARCH SUBAGENT
# ═══════════════════════════════════════════

research_search = TavilySearchResults(
    max_results=3,
    description="Search the web for company news, funding, recent developments"
)


@tool
def scrape_website(url: str) -> str:
    """Scrape a company's website to understand their products, positioning,
    and any signals relevant to outreach. Pass the full URL including https://"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        response = requests.get(url, timeout=10, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.title.string.strip() if soup.title else "No title"
        meta = soup.find("meta", attrs={"name": "description"})
        description = meta["content"] if meta else ""

        # Look for configurable signals on the website
        nav_links = soup.find_all("a")
        signals = []
        for link in nav_links:
            text = link.get_text(strip=True).lower()
            href = (link.get("href") or "").lower()
            if any(kw in text or kw in href for kw in WEBSITE_SIGNAL_KEYWORDS):
                signals.append(link.get_text(strip=True))

        body_text = soup.get_text(separator=" ", strip=True)[:1500]
        result = f"Title: {title}\nDescription: {description}\n"
        if signals:
            result += f"\n🔥 SIGNALS DETECTED: {', '.join(set(signals))}\n"
        result += f"\nContent:\n{body_text[:800]}"
        return result
    except Exception as e:
        return f"Failed to scrape {url}: {e}"


@tool
def lookup_crm(company_name: str) -> str:
    """Look up all contacts for a company in the CRM sheet. Read-only."""
    all_leads = sheet.get_all_records()
    matches = [l for l in all_leads
               if l["Company"].lower().strip() == company_name.lower().strip()]
    if not matches:
        return f"No leads found for '{company_name}'"
    result = f"Found {len(matches)} contact(s):\n"
    for l in matches:
        result += (f"- {l['Contact Name']} | {l['Title']} | "
                   f"{l['Email']} | URL: {l.get('Company URL', 'N/A')} | Status: {l['Status']}\n")
    return result


research_subagent = create_react_agent(
    model=ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0.2),
    tools=[research_search, scrape_website, lookup_crm],
    prompt=f"""You are a research subagent for a GTM outbound system.
Your ONLY job is to gather intelligence about a company.
You do NOT write emails. You do NOT make outreach decisions.

CONTEXT: You are researching companies for {COMPANY_NAME}.
{COMPANY_DESCRIPTION}

RESEARCH CHECKLIST:
1. Look up the company in the CRM for their website URL and contacts
2. Scrape their website — look for relevant signals
3. Search the web for recent news: funding, growth, challenges
4. If the website scrape fails, do extra web searches to compensate

Always end with this structure:
COMPANY: [name]
WEBSITE SUMMARY: [2-3 sentences]
SIGNALS: [list or "none detected"]
RECENT NEWS: [key findings]
CONTACTS IN CRM: [list with statuses]
"""
)


# ═══════════════════════════════════════════
# STATE DEFINITION
# ═══════════════════════════════════════════

class GTMState(TypedDict):
    lead: dict
    all_company_contacts: list
    should_contact: bool
    skip_reason: str
    website_data: str
    web_search_results: str
    signals: list
    lead_score: int
    score_breakdown: dict
    relationship_type: str
    draft_email: str
    draft_subject: str
    reasoning: str
    eval_passed: bool
    eval_feedback: str
    auto_redraft_count: int
    human_decision: str
    edit_instructions: str
    attempt_number: int
    original_draft: str


# ═══════════════════════════════════════════
# NODE FUNCTIONS
# ═══════════════════════════════════════════

def check_should_contact(state: GTMState) -> dict:
    """Gate node: should we reach out to this lead?"""
    lead = state["lead"]
    company = lead["Company"]

    all_leads = sheet.get_all_records()
    company_contacts = [l for l in all_leads
                       if l["Company"].lower().strip() == company.lower().strip()]

    if str(lead["Status"]).lower() == "contacted":
        return {
            "should_contact": False,
            "skip_reason": f"{lead['Contact Name']} is already 'contacted'. Consider a follow-up.",
            "all_company_contacts": company_contacts
        }

    return {
        "should_contact": True,
        "skip_reason": "",
        "all_company_contacts": company_contacts
    }


def research_company(state: GTMState) -> dict:
    """Research node — uses the subagent to gather intel flexibly."""
    lead = state["lead"]
    company = lead["Company"]
    company_url = lead.get("Company URL", "")

    console.print(f"\n[bold cyan]🤖 Research subagent activated for {company}...[/bold cyan]")

    research_prompt = f"Research the company '{company}'."
    if company_url:
        research_prompt += f" Their website is {company_url} — start by scraping it."

    result = research_subagent.invoke({
        "messages": [("human", research_prompt)]
    })

    research_summary = ""
    for msg in reversed(result["messages"]):
        if msg.type == "ai" and isinstance(msg.content, str) and len(msg.content) > 100:
            research_summary = msg.content
            break

    tools_used = [msg.name for msg in result["messages"] if msg.type == "tool"]
    console.print(f"[dim]🔧 Subagent used: {', '.join(tools_used)}[/dim]")

    # Extract signals from research
    signals = []
    summary_lower = research_summary.lower()
    for kw in RESEARCH_SIGNAL_KEYWORDS:
        if kw in summary_lower:
            signals.append(kw)

    return {
        "website_data": research_summary,
        "web_search_results": "",
        "signals": list(set(signals))
    }


def score_lead(state: GTMState) -> dict:
    """Score the lead 0-100 using a fixed rubric applied to research findings."""
    lead = state["lead"]
    research = state.get("website_data", "")

    console.print(f"\n[bold cyan]📊 Scoring lead: {lead['Contact Name']} @ {lead['Company']}...[/bold cyan]")

    prompt = f"""Analyze the research below about {lead['Company']} and detect which signals are present.

Company description of who we are selling for context on tech alignment:
{COMPANY_DESCRIPTION}

Research summary:
{research[:2000]}

Be strict — only mark a signal as detected if there is clear evidence in the research text.
Do not infer or assume. If the research is thin, most signals should be False."""

    signals: LeadSignals = scoring_llm.invoke(prompt)
    score, breakdown = _calculate_score(signals)

    # Color-coded label for terminal output
    if score >= 75:
        score_display = f"[bold green]{score}/100 — Hot lead[/bold green]"
    elif score >= 50:
        score_display = f"[bold yellow]{score}/100 — Warm lead[/bold yellow]"
    elif score >= 25:
        score_display = f"[dim]{score}/100 — Cold lead[/dim]"
    else:
        score_display = f"[bold red]{score}/100 — Weak lead[/bold red]"

    console.print(f"   Lead score: {score_display}")
    for label, detail in breakdown.items():
        console.print(f"   [dim]→ {label}: {detail}[/dim]")
    if not breakdown:
        console.print("   [dim]→ No signals detected (base score only)[/dim]")

    result: dict = {"lead_score": score, "score_breakdown": breakdown}

    # Auto-skip if below configured threshold (0 = informational only)
    if LEAD_SCORE_THRESHOLD > 0 and score < LEAD_SCORE_THRESHOLD:
        result["should_contact"] = False
        result["skip_reason"] = (
            f"Lead score {score}/100 is below threshold of {LEAD_SCORE_THRESHOLD}. "
            f"Signals found: {', '.join(breakdown.keys()) or 'none'}."
        )

    return result


def evaluate_draft(state: GTMState) -> dict:
    """Quality gate: rule-based checks then LLM scoring. Auto-redrafts up to _MAX_AUTO_REDRAFTS times."""
    subject = state.get("draft_subject", "")
    body = state.get("draft_email", "")
    research = state.get("website_data", "")
    lead = state["lead"]
    auto_count = state.get("auto_redraft_count", 0)

    console.print(f"\n[bold cyan]🔍 Evaluating draft quality (attempt {auto_count + 1}/{_MAX_AUTO_REDRAFTS + 1})...[/bold cyan]")

    # ── Step 1: Rule-based checks (free, instant) ──
    rule_issues = _rule_checks(subject, body)
    if rule_issues:
        feedback = "RULE VIOLATIONS — fix before rewriting:\n" + "\n".join(f"• {i}" for i in rule_issues)
        console.print(f"[yellow]   ✗ Rule checks failed[/yellow]")
        for issue in rule_issues:
            console.print(f"   [dim]  → {issue}[/dim]")
        return {"eval_passed": False, "eval_feedback": feedback, "auto_redraft_count": auto_count + 1}

    # ── Step 2: LLM quality check (structured output) ──
    quality: DraftQuality = eval_llm.invoke(
        f"""Evaluate this outreach email draft for {lead['Contact Name']} ({lead['Title']}) at {lead['Company']}.

Research context used to write it:
{research[:1000]}

Subject: {subject}

Body:
{body}

Score each dimension 1-5. Be strict: a 4+ means genuinely impressive, not just acceptable.
Only set passes_quality=True if ALL three scores are {_QUALITY_THRESHOLD} or above."""
    )

    scores = {
        "Personalization": quality.personalization_score,
        "Relevance":       quality.relevance_score,
        "CTA softness":    quality.cta_score,
    }
    avg = sum(scores.values()) / len(scores)
    score_line = "  ".join(f"{k}: {v}/5" for k, v in scores.items()) + f"  → avg {avg:.1f}"

    passes = quality.passes_quality and all(v >= _QUALITY_THRESHOLD for v in scores.values())

    if passes:
        console.print(f"[green]   ✓ Quality check passed[/green] — {score_line}")
        return {"eval_passed": True, "eval_feedback": "", "auto_redraft_count": auto_count}

    # Build targeted feedback for the redraft
    feedback_lines = []
    dim_feedback = [
        ("Personalization", quality.personalization_score, quality.personalization_feedback),
        ("Relevance",       quality.relevance_score,       quality.relevance_feedback),
        ("CTA softness",    quality.cta_score,             quality.cta_feedback),
    ]
    for dim, score, fb in dim_feedback:
        if score < _QUALITY_THRESHOLD:
            feedback_lines.append(f"• {dim} ({score}/5): {fb}")
    if quality.rewrite_instructions:
        feedback_lines.append(f"• Overall: {quality.rewrite_instructions}")

    feedback = "\n".join(feedback_lines)
    console.print(f"[yellow]   ✗ Quality check failed[/yellow] — {score_line}")
    for line in feedback_lines:
        console.print(f"   [dim]  {line}[/dim]")

    return {"eval_passed": False, "eval_feedback": feedback, "auto_redraft_count": auto_count + 1}


def route_after_eval(state: GTMState) -> str:
    if state.get("eval_passed", True):
        return "human_review"
    # Out of auto-redraft budget — pass to human with a warning
    if state.get("auto_redraft_count", 0) > _MAX_AUTO_REDRAFTS:
        console.print(
            f"[bold yellow]⚠️  Quality check still failing after {_MAX_AUTO_REDRAFTS} "
            f"auto-redrafts — handing off to you.[/bold yellow]"
        )
        return "human_review"
    return "draft"


def classify_relationship(state: GTMState) -> dict:
    """Classify: cold or contacted_other_person."""
    lead = state["lead"]
    all_contacts = state.get("all_company_contacts", [])

    contacted_others = [c for c in all_contacts
                       if str(c["Status"]).lower() == "contacted"
                       and c["Contact Name"] != lead["Contact Name"]]

    if contacted_others:
        return {"relationship_type": "contacted_other_person"}
    return {"relationship_type": "cold"}


def draft_email(state: GTMState) -> dict:
    """Draft the outreach email with memory integration."""
    lead = state["lead"]
    relationship = state["relationship_type"]
    attempt = state.get("attempt_number", 1)
    edit_instructions = state.get("edit_instructions", "")

    # Load style preferences from memory
    style_prefs = get_style_preferences()

    # Build context about other contacts
    other_contacted = ""
    company_contacts = state.get("all_company_contacts", [])
    contacted_others = [c for c in company_contacts
                       if str(c["Status"]).lower() == "contacted"
                       and c["Contact Name"] != lead["Contact Name"]]
    if contacted_others:
        names = ", ".join([f"{c['Contact Name']} ({c['Title']})" for c in contacted_others])
        other_contacted = f"\n⚠️ Already contacted at this company: {names}. Acknowledge lightly."

    relationship_guide = {
        "cold": "Cold outreach. Brief, research-backed, curiosity-driven. No hard sell.",
        "contacted_other_person": "Someone else at this company was contacted. Fresh angle for THIS person's role.",
    }

    edit_note = ""
    if attempt > 1 and edit_instructions:
        edit_note = f"\n\nREVISION #{attempt}. Rep feedback: {edit_instructions}"

    # Auto-redraft feedback from the quality evaluation node
    eval_note = ""
    auto_redraft_count = state.get("auto_redraft_count", 0)
    eval_feedback = state.get("eval_feedback", "")
    if auto_redraft_count > 0 and eval_feedback:
        eval_note = (
            f"\n\nAUTO-QUALITY-CHECK FAILED (redraft #{auto_redraft_count}). "
            f"Fix ALL of these issues before anything else:\n{eval_feedback}"
        )

    prompt = f"""Write a personalized outreach email.

ABOUT US:
{COMPANY_NAME}: {COMPANY_DESCRIPTION}

TARGET PERSONAS: {TARGET_PERSONAS}
PAIN POINTS WE SOLVE: {PAIN_POINTS}

LEAD:
- Company: {lead['Company']}
- Contact: {lead['Contact Name']}
- Title: {lead['Title']}
- Email: {lead['Email']}
{other_contacted}

RELATIONSHIP: {relationship}
{relationship_guide.get(relationship, '')}

RESEARCH:
{state.get('website_data', 'None')[:1500]}

SIGNALS DETECTED: {', '.join(state.get('signals', [])) or 'None found'}

{EMAIL_STYLE_GUIDE}

{style_prefs}
{edit_note}
{eval_note}

FORMAT:
SUBJECT: [subject line]

[email body — under 100 words, specific reference from research, soft CTA]

REASONING: [2-3 sentences on why this angle]

KEY SIGNALS: [what research informed this]
"""

    result = llm.invoke(prompt)
    response = result.content

    # Parse response
    subject = ""
    reasoning = ""
    body = response

    if "SUBJECT:" in response:
        parts = response.split("SUBJECT:", 1)[1]
        subject_and_rest = parts.split("\n", 1)
        subject = subject_and_rest[0].strip()
        body = subject_and_rest[1] if len(subject_and_rest) > 1 else ""

    if "REASONING:" in body:
        body, reasoning_part = body.split("REASONING:", 1)
        reasoning = reasoning_part.strip()

    if "KEY SIGNALS:" in reasoning:
        reasoning = reasoning.split("KEY SIGNALS:")[0].strip()

    original = state.get("original_draft", "")
    if attempt == 1:
        original = body.strip()

    return {
        "draft_email": body.strip(),
        "draft_subject": subject,
        "reasoning": reasoning,
        "attempt_number": attempt,
        "original_draft": original
    }


def human_review(state: GTMState) -> dict:
    """Show draft to human, get decision, learn from edits."""
    lead = state["lead"]

    score = state.get("lead_score", 0)
    if score >= 75:
        score_str = f"[bold green]{score}/100[/bold green]"
    elif score >= 50:
        score_str = f"[bold yellow]{score}/100[/bold yellow]"
    elif score >= 25:
        score_str = f"[dim]{score}/100[/dim]"
    else:
        score_str = f"[bold red]{score}/100[/bold red]"

    console.print("\n")
    console.print(Panel(
        f"[bold]To:[/bold] {lead['Contact Name']} ({lead['Title']}) @ {lead['Company']}\n"
        f"[bold]Email:[/bold] {lead['Email']}\n"
        f"[bold]Type:[/bold] {state['relationship_type']} | "
        f"[bold]Attempt:[/bold] #{state.get('attempt_number', 1)} | "
        f"[bold]Score:[/bold] {score_str}",
        title="📧 DRAFT EMAIL",
        border_style="cyan"
    ))

    if not state.get("eval_passed", True) and state.get("auto_redraft_count", 0) > _MAX_AUTO_REDRAFTS:
        console.print(
            f"[bold red]⚠️  Quality check did not pass after {_MAX_AUTO_REDRAFTS} auto-redrafts. "
            f"Review carefully.[/bold red]\n"
        )

    console.print(f"\n[bold]Subject:[/bold] {state['draft_subject']}\n")
    console.print(state["draft_email"])

    if state.get("reasoning"):
        console.print(Panel(state["reasoning"], title="🧠 Reasoning", border_style="yellow"))

    breakdown = state.get("score_breakdown", {})
    if breakdown:
        breakdown_lines = "  ".join([f"{k} ({v.split(' — ')[0]})" for k, v in breakdown.items()])
        console.print(f"[green]📊 Score breakdown:[/green] {breakdown_lines}\n")

    signals = state.get("signals", [])
    if signals:
        console.print(f"[green]🔍 Research signals:[/green] {', '.join(signals)}\n")

    conn = init_db()
    pref_count = conn.execute(
        "SELECT COUNT(*) FROM style_preferences WHERE rep_name = 'default'"
    ).fetchone()[0]
    conn.close()
    if pref_count > 0:
        console.print(f"[dim]🧠 {pref_count} style preferences active[/dim]")

    console.print("\n[bold]Action:[/bold]  [green][S]end[/green]  |  [yellow][E]dit[/yellow]  |  [red][C]ancel[/red]")
    decision = input("\nChoice: ").strip().lower()

    if decision == "e":
        instructions = input("What should change? → ")
        return {
            "human_decision": "edit",
            "edit_instructions": instructions,
            "attempt_number": state.get("attempt_number", 1) + 1
        }

    elif decision == "s":
        original = state.get("original_draft", "")
        final = state.get("draft_email", "")

        if state.get("attempt_number", 1) > 1 and original and final and original != final:
            console.print("\n[bold cyan]🧠 Analyzing your edits to learn preferences...[/bold cyan]")
            learn_from_edit(original, final)

        log_draft(
            company=lead["Company"],
            contact_name=lead["Contact Name"],
            original=original,
            final=final,
            action="send"
        )
        return {"human_decision": "send"}

    else:
        log_draft(
            company=lead["Company"],
            contact_name=lead["Contact Name"],
            original=state.get("original_draft", ""),
            final="",
            action="cancel"
        )
        return {"human_decision": "cancel"}


def update_crm(state: GTMState) -> dict:
    """Update Google Sheet status to 'contacted'."""
    lead = state["lead"]
    all_leads = sheet.get_all_records()

    for i, row in enumerate(all_leads):
        if (row["Company"] == lead["Company"] and
            row["Contact Name"] == lead["Contact Name"]):
            # Find the Status column index dynamically
            headers = sheet.row_values(1)
            status_col = headers.index("Status") + 1
            sheet.update_cell(i + 2, status_col, "contacted")
            console.print(f"[green]✅ Updated {lead['Contact Name']} → 'contacted'[/green]")
            break
    return {}


def log_skip(state: GTMState) -> dict:
    """Log why we skipped."""
    console.print(Panel(
        state.get("skip_reason", "Unknown reason"),
        title=f"⏭️ Skipping {state['lead']['Contact Name']}",
        border_style="red"
    ))
    log_draft(
        company=state["lead"]["Company"],
        contact_name=state["lead"]["Contact Name"],
        original="", final="", action="skip"
    )
    return {}


def log_cancel(state: GTMState) -> dict:
    """Log cancellation."""
    console.print(f"[red]❌ Cancelled: {state['lead']['Contact Name']}[/red]")
    return {}


# ═══════════════════════════════════════════
# BUILD THE GRAPH
# ═══════════════════════════════════════════

graph = StateGraph(GTMState)

graph.add_node("check_should_contact", check_should_contact)
graph.add_node("research", research_company)
graph.add_node("score_lead", score_lead)
graph.add_node("classify", classify_relationship)
graph.add_node("draft", draft_email)
graph.add_node("evaluate_draft", evaluate_draft)
graph.add_node("human_review", human_review)
graph.add_node("update_crm", update_crm)
graph.add_node("log_skip", log_skip)
graph.add_node("log_cancel", log_cancel)

graph.set_entry_point("check_should_contact")

graph.add_conditional_edges(
    "check_should_contact",
    lambda s: "research" if s["should_contact"] else "log_skip",
)

graph.add_edge("research", "score_lead")

# After scoring: skip if below threshold, otherwise continue
graph.add_conditional_edges(
    "score_lead",
    lambda s: "log_skip" if not s.get("should_contact", True) else "classify",
)

graph.add_edge("classify", "draft")
graph.add_edge("draft", "evaluate_draft")

# After eval: pass → human_review | fail + budget remaining → draft | fail + budget exhausted → human_review
graph.add_conditional_edges("evaluate_draft", route_after_eval)

graph.add_conditional_edges(
    "human_review",
    lambda s: {"send": "update_crm", "edit": "draft", "cancel": "log_cancel"}[s["human_decision"]]
)

graph.add_edge("update_crm", END)
graph.add_edge("log_skip", END)
graph.add_edge("log_cancel", END)

app = graph.compile()


# ═══════════════════════════════════════════
# RUN IT
# ═══════════════════════════════════════════

if __name__ == "__main__":
    all_leads = sheet.get_all_records()
    new_leads = [l for l in all_leads if str(l["Status"]).lower() == "new"]

    console.print(f"\n[bold cyan]═══ {COMPANY_NAME} GTM Agent ═══[/bold cyan]")
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
        console.print(f"[dim]📡 LangSmith tracing active → project: {LANGSMITH_PROJECT}[/dim]")
    console.print(f"[bold]Found {len(new_leads)} new leads[/bold]\n")

    conn = init_db()
    pref_count = conn.execute(
        "SELECT COUNT(*) FROM style_preferences WHERE rep_name = 'default'"
    ).fetchone()[0]
    draft_count = conn.execute("SELECT COUNT(*) FROM draft_history").fetchone()[0]
    conn.close()
    console.print(f"[dim]🧠 Memory: {pref_count} style preferences | {draft_count} drafts logged[/dim]\n")

    table = Table(title="New Leads")
    table.add_column("#", style="dim")
    table.add_column("Company", style="cyan")
    table.add_column("Contact", style="green")
    table.add_column("Title")
    for i, lead in enumerate(new_leads):
        table.add_row(str(i + 1), lead["Company"], lead["Contact Name"], lead["Title"])
    console.print(table)

    choice = input("\nLead # to process (or 'all' or 'compact'): ").strip()

    if choice.lower() == "compact":
        compact_memories()
        exit()

    def make_initial_state(lead):
        return {
            "lead": lead,
            "all_company_contacts": [],
            "should_contact": True,
            "skip_reason": "",
            "website_data": "",
            "web_search_results": "",
            "signals": [],
            "lead_score": 0,
            "score_breakdown": {},
            "relationship_type": "",
            "draft_email": "",
            "draft_subject": "",
            "reasoning": "",
            "eval_passed": True,
            "eval_feedback": "",
            "auto_redraft_count": 0,
            "human_decision": "",
            "edit_instructions": "",
            "attempt_number": 1,
            "original_draft": ""
        }

    if choice.lower() == "all":
        for lead in new_leads:
            console.print(f"\n{'═' * 60}")
            console.print(f"[bold]Processing: {lead['Contact Name']} @ {lead['Company']}[/bold]")
            app.invoke(make_initial_state(lead))
    else:
        idx = int(choice) - 1
        lead = new_leads[idx]
        console.print(f"\n[bold]Processing: {lead['Contact Name']} @ {lead['Company']}[/bold]")
        app.invoke(make_initial_state(lead))

    conn = init_db()
    pref_count = conn.execute(
        "SELECT COUNT(*) FROM style_preferences WHERE rep_name = 'default'"
    ).fetchone()[0]
    conn.close()
    console.print(f"\n[dim]🧠 Memory now has {pref_count} style preferences[/dim]")