#!/usr/bin/env python3
"""
Hitachi Theme 5 — Weekly Research Council
Four parallel AI expert agents analyze the research journal and your EraOfAI documents.
A synthesizer produces a Board Memo with strategic recommendations.
Runs every Saturday after the journal reorganizer.
"""

import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import anthropic
from openai import OpenAI

# ── Config ─────────────────────────────────────────────────────────────────────
ERAOFAI_DIR = os.path.expanduser("~/Documents/EraOfAI")
JOURNAL_PATH = os.path.join(ERAOFAI_DIR, "research_journal.md")
MEMOS_DIR = os.path.join(ERAOFAI_DIR, "board_memos")
BOT_TOKEN_FILE = "/Users/ssurender/.claude/channels/telegram/.env"
TELEGRAM_CHAT_ID = "8105393549"
SYNTHESIZER_MODEL = "claude-opus-4-6"   # Anthropic direct — best synthesis
MAX_JOURNAL_CHARS = 40000   # ~10K tokens — last ~2 weeks of entries
MAX_DOC_CHARS = 3000        # per document excerpt

# Model routing: experts use OpenRouter for multi-model diversity
# Synthesizer uses Anthropic (Opus) directly
EXPERT_MODELS = {
    "AI Safety Scientist":    {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "AI Policy Analyst":      {"provider": "openrouter", "model": "openai/gpt-4o"},
    "Industry Strategist":    {"provider": "openrouter", "model": "google/gemini-pro-1.5"},
    "Communications Advisor": {"provider": "openrouter", "model": "mistralai/mistral-large-2407"},
}


# ── API key helpers ────────────────────────────────────────────────────────────
def get_keychain(service):
    try:
        return subprocess.check_output(
            ["security", "find-generic-password", "-s", service, "-w"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


def make_anthropic_client():
    key = get_keychain("anthropic-api-key") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("No Anthropic API key found in keychain.", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic(api_key=key)


def make_openrouter_client():
    key = get_keychain("openrouter-api-key") or os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print("No OpenRouter API key found in keychain.", file=sys.stderr)
        sys.exit(1)
    return OpenAI(
        api_key=key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": "https://hitachi-theme5.local"},
    )


# ── Telegram ───────────────────────────────────────────────────────────────────
def get_bot_token():
    try:
        with open(BOT_TOKEN_FILE) as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.strip().split("=", 1)[1]
    except Exception:
        pass
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def send_telegram(text, chat_id=TELEGRAM_CHAT_ID):
    token = get_bot_token()
    if not token:
        return
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    ctx = ssl.create_default_context()
    for chunk in chunks:
        payload = json.dumps({"chat_id": chat_id, "text": chunk}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, context=ctx, timeout=10)
        except Exception as e:
            print(f"Telegram error: {e}", file=sys.stderr)
        time.sleep(0.3)


# ── Context loading ────────────────────────────────────────────────────────────
def load_journal_recent():
    """Load the most recent MAX_JOURNAL_CHARS of the research journal."""
    if not os.path.exists(JOURNAL_PATH):
        return "(No research journal found yet.)"
    with open(JOURNAL_PATH) as f:
        content = f.read()
    if len(content) <= MAX_JOURNAL_CHARS:
        return content
    # Take the tail — most recent entries
    return "...[earlier entries omitted]...\n\n" + content[-MAX_JOURNAL_CHARS:]


def extract_text_from_file(path):
    """Extract text from PDF or DOCX files."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            from pdfminer.high_level import extract_text
            return extract_text(path) or ""
        elif ext in (".docx", ".doc"):
            result = subprocess.run(
                ["python3", "-c",
                 f"import docx; d=docx.Document('{path}'); print('\\n'.join(p.text for p in d.paragraphs))"],
                capture_output=True, text=True, timeout=15,
            )
            return result.stdout
        elif ext in (".txt", ".md"):
            with open(path) as f:
                return f.read()
    except Exception as e:
        print(f"Could not extract {path}: {e}", file=sys.stderr)
    return ""


def load_eraofai_documents():
    """Load text excerpts from all documents in EraOfAI folder (not scripts/logs/journal)."""
    skip_exts = {".py", ".log", ".json", ".plist", ".db"}
    skip_names = {"research_journal.md"}
    docs = []
    for fname in sorted(os.listdir(ERAOFAI_DIR)):
        if fname.startswith("."):
            continue
        if fname in skip_names:
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext in skip_exts or not ext:
            continue
        fpath = os.path.join(ERAOFAI_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        text = extract_text_from_file(fpath)
        if text.strip():
            excerpt = text.strip()[:MAX_DOC_CHARS]
            docs.append(f"=== {fname} ===\n{excerpt}\n")
    return "\n".join(docs) if docs else "(No documents found.)"


# ── Expert agent definitions ───────────────────────────────────────────────────
EXPERTS = [
    {
        "name": "AI Safety Scientist",
        "focus": "technical AI safety and alignment",
        "persona": (
            "You are a senior AI safety researcher with expertise in alignment, "
            "reliability, interpretability, and failure mode analysis. "
            "You think like a researcher at MIRI, Anthropic, or DeepMind Safety team."
        ),
        "question": (
            "Based on this week's research signals, what are the most important "
            "technical developments in AI safety and reliability? "
            "What should a Hitachi research team focused on 'Safety & Reliability as Value' "
            "be paying close attention to? Identify 2-3 key findings with implications."
        ),
    },
    {
        "name": "AI Policy Analyst",
        "focus": "AI governance, regulation, and policy",
        "persona": (
            "You are a senior policy analyst specializing in AI regulation and governance. "
            "You track the EU AI Act, US executive orders, G7/G20 AI initiatives, "
            "and national AI strategies — especially in Japan, US, EU, and China."
        ),
        "question": (
            "What governance and regulatory developments from this week's research are "
            "most significant? How do they affect the argument that safety/reliability "
            "is becoming the #1 value in AI? What should Hitachi communicate to its "
            "Board of Directors about the regulatory landscape?"
        ),
    },
    {
        "name": "Industry Strategist",
        "focus": "competitive landscape and market positioning",
        "persona": (
            "You are a technology industry strategist who tracks AI deployments by "
            "major players: Google, Microsoft, OpenAI, Meta, Baidu, and industrial AI "
            "companies like Siemens, Bosch, and Hitachi's competitors. "
            "You focus on how AI reliability and safety are becoming competitive differentiators."
        ),
        "question": (
            "What does this week's research tell us about how the industry is positioning "
            "AI safety and reliability? Are competitors treating it as a differentiator or burden? "
            "What market opportunity does Hitachi's Theme 5 thesis address? "
            "Give 2-3 concrete competitive insights."
        ),
    },
    {
        "name": "Communications Advisor",
        "focus": "executive communications and Japanese business context",
        "persona": (
            "You are a communications advisor specializing in presenting technology strategy "
            "to Japanese corporate boards. You understand nemawashi, the importance of consensus, "
            "how to frame risk in Japanese corporate culture, and how to make complex AI themes "
            "accessible to senior executives who are not technologists."
        ),
        "question": (
            "Given this week's research signals, how should the Hitachi Theme 5 thesis be "
            "framed for a Japanese Board of Directors presentation in May 2026? "
            "What language, analogies, or framing will resonate? "
            "What concerns might the board raise, and how should they be pre-empted?"
        ),
    },
]


# ── Run a single expert ────────────────────────────────────────────────────────
def run_expert(clients, expert, journal_text, docs_text, date_label):
    routing = EXPERT_MODELS.get(expert["name"], {"provider": "anthropic", "model": "claude-sonnet-4-6"})
    provider = routing["provider"]
    model = routing["model"]

    system = (
        f"{expert['persona']}\n\n"
        "You are part of a weekly research council for Hitachi Theme 5: "
        "'The Growing Value of Safety & Reliability in the AI Era' "
        "(AI時代における安全性・信頼性の価値としての高まり).\n"
        "The project manager is Sudeep Surender (Chief Researcher, Hitachi). "
        "Key milestones: Board of Directors (May 2026), Advisory Committee (July 2026), "
        "Tokyo camp Part 2 (December 2026).\n\n"
        "Be specific, cite sources from the research where possible, "
        "and keep your response to 300-400 words."
    )

    user = (
        f"Date: {date_label}\n\n"
        f"=== RESEARCH JOURNAL (recent entries) ===\n{journal_text}\n\n"
        f"=== SUDEEP'S DOCUMENTS (EraOfAI folder) ===\n{docs_text}\n\n"
        f"=== YOUR QUESTION ({expert['focus']}) ===\n{expert['question']}"
    )

    try:
        if provider == "anthropic":
            resp = clients["anthropic"].messages.create(
                model=model, max_tokens=600, system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = resp.content[0].text
            usage = resp.usage
        else:  # openrouter
            resp = clients["openrouter"].chat.completions.create(
                model=model, max_tokens=600,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            text = resp.choices[0].message.content
            usage = resp.usage  # has prompt_tokens / completion_tokens

        return expert["name"], text, usage, provider, model
    except Exception as e:
        return expert["name"], f"[Error from {provider}/{model}: {e}]", None, provider, model


# ── Synthesizer ────────────────────────────────────────────────────────────────
def run_synthesizer(clients, expert_outputs, date_label):
    expert_text = "\n\n".join(
        f"--- {name} ({model}) ---\n{output}"
        for name, output, _, provider, model in expert_outputs
    )

    system = (
        "You are the Chief of Staff to Sudeep Surender, PM for Hitachi Theme 5. "
        "Your job is to synthesize four expert perspectives into a single, crisp "
        "Board Memo — the kind a Japanese Chief Researcher would bring to a Board of Directors. "
        "Write in confident, executive prose. Be concrete. No padding.\n\n"
        "Structure your memo exactly as:\n"
        "BOARD MEMO — Theme 5: AI Safety & Reliability\n"
        "[Date]\n\n"
        "EXECUTIVE SUMMARY (3-4 sentences)\n\n"
        "KEY SIGNALS THIS WEEK\n"
        "1. [signal + implication]\n"
        "2. [signal + implication]\n"
        "3. [signal + implication]\n\n"
        "STRATEGIC RECOMMENDATION FOR MAY BOARD PRESENTATION\n"
        "[1 paragraph — the central argument to make]\n\n"
        "SUGGESTED ACTIONS (next 2 weeks)\n"
        "- [specific action]\n"
        "- [specific action]\n"
        "- [specific action]\n\n"
        "WATCH LIST\n"
        "- [item to monitor next week]"
    )

    user = (
        f"Today is {date_label}. The Board of Directors presentation is in approximately "
        f"{(datetime(2026, 5, 15) - datetime.now()).days} days.\n\n"
        f"Here are the four expert analyses:\n\n{expert_text}"
    )

    try:
        resp = clients["anthropic"].messages.create(
            model=SYNTHESIZER_MODEL,
            max_tokens=1000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text, resp.usage
    except Exception as e:
        return f"[Synthesizer error: {e}]", None


# ── Save memo ──────────────────────────────────────────────────────────────────
def save_memo(memo_text, date_label):
    os.makedirs(MEMOS_DIR, exist_ok=True)
    date_slug = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(MEMOS_DIR, f"board_memo_{date_slug}.md")
    with open(path, "w") as f:
        f.write(memo_text)
    return path


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    date_label = datetime.now().strftime("%Y-%m-%d %A")
    print(f"[{datetime.now():%H:%M}] Research Council starting — {date_label}", flush=True)

    clients = {
        "anthropic": make_anthropic_client(),
        "openrouter": make_openrouter_client(),
    }

    print(f"[{datetime.now():%H:%M}] Loading context...", flush=True)
    journal_text = load_journal_recent()
    docs_text = load_eraofai_documents()
    print(f"  Journal: {len(journal_text):,} chars | Docs: {len(docs_text):,} chars")

    # Run all 4 experts in parallel
    print(f"[{datetime.now():%H:%M}] Running 4 experts in parallel...", flush=True)
    expert_outputs = []
    total_tokens = 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(run_expert, clients, expert, journal_text, docs_text, date_label): expert
            for expert in EXPERTS
        }
        for future in as_completed(futures):
            name, output, usage, provider, model = future.result()
            expert_outputs.append((name, output, usage, provider, model))
            if usage:
                # Anthropic: input_tokens/output_tokens; OpenAI-compat: prompt_tokens/completion_tokens
                tin = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0)
                tout = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", 0)
                total_tokens += tin + tout
            print(f"  [{name}] {provider}/{model.split('/')[-1]} — {len(output)} chars")

    # Synthesize with Opus
    print(f"[{datetime.now():%H:%M}] Synthesizing with Claude Opus...", flush=True)
    memo, synth_usage = run_synthesizer(clients, expert_outputs, date_label)
    if synth_usage:
        total_tokens += synth_usage.input_tokens + synth_usage.output_tokens

    # Save
    memo_path = save_memo(memo, date_label)
    print(f"[{datetime.now():%H:%M}] Memo saved: {memo_path}")

    print(f"  Total tokens (approx): {total_tokens:,}")

    # Send to Telegram
    models_used = " | ".join(
        f"{n.split()[0]}: {m.split('/')[-1]}" for n, _, _, p, m in expert_outputs
    )
    header = f"Research Council — Board Memo\n{date_label}\nModels: {models_used} | Synth: Opus\n\n"
    send_telegram(header + memo)
    print(f"[{datetime.now():%H:%M}] Sent to Telegram. Done.")


if __name__ == "__main__":
    main()
