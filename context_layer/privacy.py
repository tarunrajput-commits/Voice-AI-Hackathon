"""Privacy helpers. Files carry only what the bot needs:
- first name + city (for a natural greeting), never phone / email / address / IDs
- KYC as verified/pending flags, never the GST/PAN/Aadhaar numbers themselves
- the counterpart on an enquiry/lead appears as "FirstName, City" (buyer) or company + city (seller)
Free text (conversation summaries) is scrubbed with the patterns below before it is written,
and bot replies are scrubbed again before they are sent.
"""
import re

PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"), "[gstin]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[pan]"),
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "[id-number]"),          # Aadhaar-like
    (re.compile(r"(?:\+?91[\s-]?)?\b[6-9]\d{9}\b"), "[phone]"),
    (re.compile(r"\b\d{9,18}\b"), "[account-number]"),                   # bank a/c-like
]


def scrub(text):
    if not text:
        return text
    for pat, repl in PATTERNS:
        text = pat.sub(repl, text)
    return text


def first_name(full):
    return (full or "").strip().split(" ")[0] if full else ""


# Fact keys the bot may never store or repeat even if a user volunteers them
BLOCKED_FACT_KEYS = re.compile(r"phone|mobile|email|address|pan|gst_?(no|number)|aadhaar|account|ifsc|password|otp",
                               re.I)


def safe_facts(facts):
    out = {}
    for k, v in (facts or {}).items():
        if BLOCKED_FACT_KEYS.search(k):
            continue
        out[k] = scrub(str(v))[:80]
    return out
