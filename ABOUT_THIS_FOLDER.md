# About This Folder — EraOfAI

This folder is my personal intelligence system for Hitachi Theme 5 research.

**Theme 5:** "The Growing Value of Safety & Reliability in the AI Era"
(AI時代における安全性・信頼性の価値としての高まり)
**My role:** Project Manager
**Key deadlines:** Board of Directors (May 2026) → Advisory Committee (Jul 2026) → Tokyo (Dec 2026)

---

## What Runs Automatically

**Every night at 9 PM — Research Digest**
Scans the internet (Hacker News, arXiv papers, YouTube) for anything relevant to AI safety,
governance, regulation, alignment, reliability, and explainability.
Appends curated links with summaries to: `research_journal.md`

**Every Monday & Thursday at 9:30 PM — Research Council**
Four AI experts (Claude, GPT-4o, Gemini, Mistral) read the journal in parallel, debate it
from their different angles, and Claude Opus synthesizes a Board Memo for my review.
Saved to: `board_memos/` folder. Also sent to me via Telegram.

**Every Saturday at 10 AM — Weekly Reorganizer**
Sorts everything in the journal by topic so it stays readable and searchable.

---

## What I Add Manually

Drop any PDF or Word document into this folder and it will automatically be read
by the Research Council on the next Monday or Thursday run. No extra steps needed.

Current documents:
- My two Hitachi research proposals (English)
- The Hitachi 2026 research themes PDF (Japanese, Theme 5 is my project)

---

## Key Files

| File | What it is |
|------|-----------|
| `research_journal.md` | All collected research links, organized by topic |
| `board_memos/` | Weekly Board Memos from the Research Council |
| `research_digest.py` | The nightly scanner script |
| `research_council.py` | The multi-model expert council script |
| `research_reorganize.py` | The weekend topic organizer script |
| `README.md` | Technical setup guide (for GitHub) |

---

## Cost

Only the Research Council costs money (~$2-3/month via Claude API + OpenRouter).
Everything else (nightly digest, reorganizer) is free.

---

*System built by Claude Code (Brihaspati), March 2026.*
