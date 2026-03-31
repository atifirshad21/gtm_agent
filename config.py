"""
Configuration — Edit this file to customize the agent for your business.

This is the ONLY file you need to change. Everything else works automatically.
"""

# ─── Your Company ───
COMPANY_NAME = "Your Company"

COMPANY_DESCRIPTION = """
We help [target customers] solve [problem] by [solution].
[Add 1-2 sentences about your key value props.]
"""

# ─── Who you're targeting ───
TARGET_PERSONAS = "VP of Sales, Head of Operations, CTO, Directors of Engineering"

PAIN_POINTS = """
- [Pain point 1 your product solves]
- [Pain point 2]
- [Pain point 3]
"""

# ─── Email style ───
EMAIL_STYLE_GUIDE = """
RULES FOR WRITING OUTREACH EMAILS:
- Keep the email body under 100 words
- Use an opportunity-first framing (not problem-first)
- Reference something specific from the research
- Match tone to the contact's seniority (C-suite = strategic, Director = tactical)
- End with a soft CTA ("would it make sense to explore..." not "book a call")
"""

# ─── Research signals ───
# Keywords to look for on company websites (nav links, sections)
# These help the agent find relevant signals during research
WEBSITE_SIGNAL_KEYWORDS = [
    "pricing", "enterprise", "demo", "contact sales",
    "case studies", "integrations", "api",
    # Add keywords relevant to YOUR industry:
    # e.g., for fashion: "sale", "archive", "outlet", "clearance"
    # e.g., for SaaS: "pricing", "free trial", "enterprise"
    # e.g., for recruiting: "careers", "open roles", "hiring"
]

# Keywords to look for in web search results
# These get extracted from the research summary as "signals"
RESEARCH_SIGNAL_KEYWORDS = [
    "funding", "raised", "series", "growth", "expansion",
    "hiring", "layoffs", "acquisition", "partnership",
    "launch", "new product", "revenue",
    # Add keywords relevant to YOUR outreach angle:
    # e.g., for fashion: "deadstock", "sustainability", "overproduction"
    # e.g., for DevTools: "developer experience", "open source", "migration"
]

# ─── Google Sheet ───
# Name of your Google Sheet (must be shared with your service account)
GOOGLE_SHEET_NAME = "Mock_GTM"

# Required columns in your sheet:
# Lead ID | Company | Company URL | Contact Name | Title | Email | Status
#
# "Status" should be either "new" or "contacted"
# The agent will only process leads with status "new"
# and will update status to "contacted" after you approve a draft