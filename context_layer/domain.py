"""IndiaMART domain knowledge (contexts/indiamart_domain_knowledge.md) for the bot.

The knowledge base is ~36 KB. Following its own implementation note, it is NOT injected whole:
every prompt gets a small CORE (operating principles, privacy, voice style, missing/conflicting/
stale-data rules), plus the sections that match the caller's current intent, under a size budget.
Intent routing is deterministic keyword matching (English + Hinglish, seeded from Appendix B and the
Section 7 table) – no extra LLM call, no added latency. Recent intents stay "sticky" for a couple of
turns so follow-up questions keep the right sections. The file is re-read when it changes on disk,
so the domain team can edit it without a restart.

    domain.select(role, user_text, phase="turn", sticky=()) -> (text, intents)
"""
import re
import threading

from config import CONTEXT_DIR

PATH = CONTEXT_DIR / "indiamart_domain_knowledge.md"
BUDGET_CHARS = 7600   # ≈1.9k tokens on top of the ~3k-char context file
_lock = threading.Lock()
_cache = {"mtime": None, "sections": {}}

CORE = ["Core operating principles", "12. Privacy, Security, and Authorised Actions", "13. Response Style for Voice",
        "Missing data", "Conflicting data", "Stale data", "No history"]

# intent -> (keyword regex, sections in priority order)
ROUTES = {
    "lead_generation": (r"lead|leads|enquir(y|ies) (nahi|kam|drop)|business nahi|customer|grahak|order nahi aa|need more|kam ho",
                        ["5.1 Lead", "5.2 BuyLead", "5.3 Lead Received", "A. Seller reports low or no leads"]),
    "lead_quality": (r"wrong|galat|fake|irrelevant|bekar|faltu|quality|relevant|nahi chahiye",
                     ["5.8 Lead Relevance or Lead Quality", "B. Seller reports irrelevant leads", "5.2 BuyLead"]),
    "contact_outcome": (r"pick|utha|not answer|nahi uth|connect|switch ?off|band hai|phone nahi|call nahi|respond",
                        ["5.4 Lead Attempted", "5.5 Call Connected or Answered", "5.6 Not Answered",
                         "5.7 Interested, Not Interested, or Follow-up Required"]),
    "listing_visibility": (r"show nahi|dikh|visible|search|upar|rank|listing|catalog|catalogue|product (add|daal|jod)|photo|"
                           r"price (add|daal)|reject|approve",
                           ["5.10 Product Listing Status", "5.11 Product Visibility and Search Ranking", "5.9 Product Catalogue",
                            "D. Seller reports a missing product listing"]),
    "service_payment": (r"payment|paise|pay kar|plan|service|renew|subscription|membership|refund|cancel|expire|khatam|"
                        r"nach|auto.?debit|invoice|package|paid",
                        ["5.13 Paid Services, Membership, and Subscription", "E. Caller reports a payment or service issue"]),
    "kyc": (r"kyc|verify|verif|document|gst|pan card|aadhaar",
            ["5.12 Seller KYC or Business Verification", "4.9 Buyer KYC or Verification"]),
    "buyer_enquiry": (r"enquiry (ki|kiya|bheji)|supplier|seller ka|quotation|quote|rate|kitne ka|khareed|buy|chahiye|requirement|"
                      r"rfq|sample",
                      ["4.4 Enquiry", "4.5 Buy Requirement", "4.6 RFQ or Quotation Request", "4.7 Supplier Contact",
                       "C. Buyer reports no supplier response"]),
    "purchase_order": (r"\border\b|purchase|deal (ho|done)|kharid liya|delivery",
                       ["4.8 Purchase or Order"]),
    "cross_channel": (r"kal|yesterday|pehle|already|bataya tha|whatsapp pe|last time|phir se|again|wahi",
                      ["Conversation resumption", "Open issue", "Resolved issue", "Callback",
                       "F. Caller reports an unresolved previous interaction", "Cross-channel safety"]),
    "escalation": (r"insaan|human|agent|executive|manager|senior|complaint|shikayat|speak to someone|baat karni",
                   ["F. Caller reports an unresolved previous interaction"]),
}
OPENING = {"buyer": ["Buyer examples", "Step 3: Identify the latest relevant activity"],
           "seller": ["Seller examples", "Step 3: Identify the latest relevant activity"]}
FALLBACK = ["7. Understanding What the Caller Really Means"]      # intent unclear -> the statement→concept table


def _load():
    with _lock:
        mtime = PATH.stat().st_mtime if PATH.exists() else None
        if mtime != _cache["mtime"]:
            text = PATH.read_text(encoding="utf-8") if mtime else ""
            sections = {}
            for part in re.split(r"(?m)^(?=#{1,3} )", text):
                if part.strip():
                    head = re.sub(r"^#+\s*", "", part.splitlines()[0]).strip()
                    sections[head] = part.strip()
            _cache.update(mtime=mtime, sections=sections)
        return _cache["sections"]


def intents(text):
    t = (text or "").lower()
    return [name for name, (rx, _) in ROUTES.items() if re.search(rx, t)]


def select(role, user_text="", phase="turn", sticky=()):
    """Returns (knowledge_text, intents_matched). phase: 'opening' | 'turn' | 'summary'."""
    sec = _load()
    if not sec:
        return "", []
    found = intents(user_text)
    names = list(CORE)
    if phase == "opening":
        names += OPENING.get(role, [])
    for it in list(dict.fromkeys(found + list(sticky))):
        names += ROUTES[it][1]
    if phase == "turn" and not found and not sticky:
        names += FALLBACK
    out, size = [], 0
    for n in dict.fromkeys(names):              # keep order, drop duplicates
        body = sec.get(n)
        if body and size + len(body) <= BUDGET_CHARS:
            out.append(body)
            size += len(body)
    return "\n\n".join(out), found


def available():
    return bool(_load())
