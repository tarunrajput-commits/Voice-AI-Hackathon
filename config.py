"""Central configuration: paths, lookback windows, size budgets, models."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Load .env without an extra dependency
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "events.db"
FRESHNESS_LOG = DATA_DIR / "freshness.jsonl"
CONTEXT_DIR = ROOT / "contexts"          # contexts/<glid>/buyer.md, seller.md

# Lookback window per source, in days. Justification lives in README.md ("Lookback windows").
LOOKBACK_DAYS = {
    "enquiries": 90,         # seller's lead lifecycle; matches the API's own enq_last_90_days
    "enquiry_messages": 90,  # tied to the enquiries they belong to
    "pns_calls": 90,         # buyer calls received; matches the API's pns_received_90_days
    "buyleads": 45,          # warehouse only keeps ~45 days of purchases
    "whatsapp": 30,          # delivery/read signals are engagement: rolling 30d
    "wa_chat": 60,           # chatbot threads (requirements, photo uploads, feedback) stay resumable ~2 months
    "call_extractions": 90,  # products/specs/prices discussed stay relevant for a quote cycle
    "vani_calls": 180,       # VANI calls are sparse (~2/seller in 6 months); the bot must remember every past call,
                             # objection and disposition so it never repeats a pitch
    "exec_calls": 60,        # executive touchpoints: recent relationship context
    "buyer_activity": 30,    # searches / browsing intent decays fast (API returns ~4 weeks anyway)
    "conversations": 30,     # this bot's own write-backs (voice / WhatsApp / chat)
    # profile, KYC, account, tickets, catalog, market = live state from the Global Context API: latest only.
}

# Hard cap on file size. 3,000 chars ≈ 750-850 tokens (Hinglish/proper nouns tokenise worse than English).
# Real sellers have 11 source families + live account state; 3,000 keeps every family represented at
# <1% of a 128K context, and stays readable by a human in ~30 s.
MAX_FILE_CHARS = 3000

# Row caps per section (keep files compact and consistently shaped)
CAPS = {"enquiries": 4, "leads": 4, "conversations": 4, "open_threads": 4, "facts": 10, "care": 6,
        "buyleads": 3, "searches": 5, "requirements": 4, "sellers": 4}

# Refresh mechanism (hybrid)
DEBOUNCE_MS = 50              # coalesce bursts of events for the same GLID
SWEEP_INTERVAL_S = 15 * 60    # scheduled full rebuild: ages out lookback windows, polls pull-only sources
SESSION_IDLE_END_S = 180      # auto-close idle chat sessions (writes the conversation summary)

# Sarvam models
LLM_CHAT_MODEL = "sarvam-105b-conversations"   # low latency, tuned for dialogue / voice agents
LLM_TASK_MODEL = "sarvam-105b-conversations"   # summarisation + fact extraction (JSON mode, ~0.5 s)
LLM_TASK_FALLBACK = "sarvam-105b"               # slower reasoning model, used if the fast one returns bad JSON
STT_MODEL = "saaras:v3"
TTS_MODEL = "bulbul:v4-flash"
TTS_SPEAKER = "ritu_hi_customer"   # chosen on the /voices page

DATA_LABEL = os.environ.get("DATA_LABEL", "REAL (internal use only)")
BOT_NAME = os.environ.get("BOT_NAME", "Vani")

# Demo set: real GLIDs chosen to cover the situations the bot must handle (kept warm in the live-API cache)
FEATURED = {
    "209139024": "rich: exec meeting fixed + keyword-mapping note; also sourcing as a buyer",
    "239368219": "churn risk: told exec no results in 3 months, prefers Amazon; already with executive",
    "42559301": "showed frustration on VANI calls; trust/privacy objection",
    "7444262": "DO-NOT-CALL requested; 150+ enquiries",
    "5397256": "last VANI call: meeting fixed",
    "83127677": "last VANI call: asked to call back later",
    "47648617": "asked if talking to a bot",
    "12855767": "live WhatsApp chats in API; high enquiry volume",
}
