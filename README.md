# Hitachi Theme 5 — AI Research Intelligence System

Automated research intelligence pipeline for **Hitachi Theme 5: "The Growing Value of Safety & Reliability in the AI Era"** (AI時代における安全性・信頼性の価値としての高まり).

Built to support the PM (Sudeep Surender, Chief Researcher, Hitachi) in preparing for:
- Board of Directors presentation — May 2026
- Advisory Committee — July 2026
- Tokyo camp Part 2 — December 2026

---

## Architecture

### 1. Nightly Research Digest (`research_digest.py`)
Runs every night at 9 PM via launchd. Scans:
- **Hacker News** (via Algolia API) — AI safety/governance discussions
- **arXiv** — recent academic papers on AI safety, alignment, governance
- **YouTube** (via yt-dlp) — videos on AI safety, regulation, trustworthy AI

Filters for relevance to Theme 5 keywords (safety, reliability, governance, alignment, explainability, etc.) and appends curated entries to `research_journal.md` with source + 2-3 sentence excerpt.

### 2. Weekend Reorganizer (`research_reorganize.py`)
Runs every Saturday at 10:00 AM. Reads the accumulated journal and reorganizes all entries by topic:
- AI Governance & Regulation
- AI Safety & Alignment
- Reliability & Robustness
- Explainability & Transparency
- Societal Impact & Human Value
- Technical Research

### 3. Research Council (`research_council.py`)
Runs every Monday and Thursday at 9:30 PM. Four AI expert agents run **simultaneously** (parallel API calls), each using a different frontier model for diverse perspectives:

| Agent | Model | Focus |
|-------|-------|-------|
| AI Safety Scientist | Claude Sonnet 4.6 (Anthropic) | Technical alignment & reliability |
| AI Policy Analyst | GPT-4o (OpenAI via OpenRouter) | Governance, regulation, EU AI Act |
| Industry Strategist | Gemini Pro 1.5 (Google via OpenRouter) | Competitive landscape |
| Communications Advisor | Mistral Large 2 (via OpenRouter) | Japanese Board framing & executive comms |
| **Synthesizer** | **Claude Opus 4.6 (Anthropic)** | **Final Board Memo** |

Output: structured **Board Memo** delivered via Telegram + saved to `board_memos/`.

---

## Board Memo Format

```
BOARD MEMO — Theme 5: AI Safety & Reliability
[Date]

EXECUTIVE SUMMARY

KEY SIGNALS THIS WEEK
1. [signal + implication]
2. [signal + implication]
3. [signal + implication]

STRATEGIC RECOMMENDATION FOR MAY BOARD PRESENTATION

SUGGESTED ACTIONS (next 2 weeks)

WATCH LIST
```

---

## Setup

### Prerequisites
```bash
pip3 install anthropic openai pdfminer.six yt-dlp requests icalendar pytz
```

### API Keys (stored in macOS Keychain — never on disk)
```bash
# Anthropic (Claude Sonnet + Opus)
security add-generic-password -s "anthropic-api-key" -a "$(whoami)" -w "sk-ant-..." -U

# OpenRouter (GPT-4o, Gemini, Mistral)
security add-generic-password -s "openrouter-api-key" -a "$(whoami)" -w "sk-or-..." -U

# Telegram Bot Token
# Store in ~/.claude/channels/telegram/.env as TELEGRAM_BOT_TOKEN=...
```

### Schedule (launchd — auto-starts on login)
```
9:00 PM daily     → research_digest.py      (nightly news scan)
Sat 10:00 AM      → research_reorganize.py  (weekly topic sort)
Mon+Thu 9:30 PM   → research_council.py     (Board Memo)
```

Install agents:
```bash
launchctl load ~/Library/LaunchAgents/com.brihaspati.researchdigest.plist
launchctl load ~/Library/LaunchAgents/com.brihaspati.researchreorganize.plist
launchctl load ~/Library/LaunchAgents/com.brihaspati.researchcouncil.plist
```

### Documents
Drop any PDF or DOCX into `~/Documents/EraOfAI/` and the Research Council will automatically read and incorporate them into its analysis.

---

## Output Files
- `research_journal.md` — running log of all curated research links
- `board_memos/board_memo_YYYY-MM-DD.md` — weekly Board Memos

---

## Cost Estimate
~$0.25–0.35 per Research Council run (2×/week = ~$25–35/year).
