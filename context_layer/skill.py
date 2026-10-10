"""skill.md is the source of truth. This module reads it and hands its rules to the system.

  * pipeline settings  – lookback windows (§2 table), file size cap (§6), API time budget (§1),
                         executive working hours (§11). Parsed from the text; if a value can't be
                         read, the built-in default is kept and the drift is reported.
  * bot instructions   – §10 and §11: the always-on core (decision order, escalate-instead-of-guessing,
                         working hours, hard guardrails, write-back) plus the transfer / callback /
                         meeting procedure that matches what the caller is asking for.

The file is re-read whenever it changes on disk (edit skill.md, no restart needed). Markdown escapes
added by rich-text editors (\\_ \\[ \\--- …) are removed on load; the file itself is never modified.
"""
import re
import threading

import config
from config import ROOT

PATH = ROOT / "skill.md"
_lock = threading.Lock()
_cache = {"mtime": None, "text": "", "sections": {}, "settings": {}, "report": []}

DEFAULTS = {"lookback_days": dict(config.LOOKBACK_DAYS), "max_file_chars": config.MAX_FILE_CHARS,
            "api_budget_s": 3.0, "work_hours": (9, 0, 19, 0)}

# §2 lookback table: row label (lower-case, as written in skill.md) -> config keys it sets
LOOKBACK_ROWS = {
    "enquiries, enquiry messages, buyer calls": ["enquiries", "enquiry_messages", "pns_calls"],
    "buy-leads bought": ["buyleads"],
    "vani calls and transcripts": ["vani_calls"],
    "whatsapp chatbot, executive calls": ["wa_chat", "exec_calls"],
    "call extractions": ["call_extractions"],
    "whatsapp delivery, buyer activity (searches)": ["whatsapp", "buyer_activity"],
    "bot conversation write-backs": ["conversations"],
}


def _unescape(t):
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|&<>~])", r"\1", t)


def _sections(text):
    """Split on #/##/### headings and on bold paragraph labels used inside §11 ("Live transfer procedure:")."""
    out, head, buf = {}, "_preamble", []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.*)$", line) or re.match(r"^([A-Z][A-Za-z /&,()-]{3,60}):\s*$", line.strip())
        if m:
            out[head] = "\n".join(buf).strip()
            head, buf = m.group(1).strip(), [line]
        else:
            buf.append(line)
    out[head] = "\n".join(buf).strip()
    return out


def _parse_settings(text, sections):
    s, report = {"lookback_days": dict(DEFAULTS["lookback_days"])}, []
    # lookbacks
    seen = 0
    for row in re.findall(r"^\|([^|\n]+)\|(\d+)d\|", text, re.M):
        label, days = row[0].strip().lower(), int(row[1])
        for k in LOOKBACK_ROWS.get(label, []):
            if s["lookback_days"].get(k) != days:
                report.append(f"lookback {k}: {s['lookback_days'].get(k)}d -> {days}d (from skill.md)")
            s["lookback_days"][k] = days
            seen += 1
    if not seen:
        report.append("lookback table not found in skill.md – using built-in defaults")
    m = re.search(r"≤\s*([\d,]+)\s*characters", text)
    s["max_file_chars"] = int(m.group(1).replace(",", "")) if m else DEFAULTS["max_file_chars"]
    if not m:
        report.append("size cap not found – using default")
    m = re.search(r"api_budget_s`?\s*\((\d+(?:\.\d+)?)s\)", text) or re.search(r"time budget \(default (\d+(?:\.\d+)?)s", text)
    s["api_budget_s"] = float(m.group(1)) if m else DEFAULTS["api_budget_s"]
    m = re.search(r"(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})\s*India Standard Time", text)
    s["work_hours"] = tuple(int(x) for x in m.groups()) if m else DEFAULTS["work_hours"]
    if not m:
        report.append("working hours not found – using 09:00–19:00 IST")
    return s, report


def _load():
    with _lock:
        mtime = PATH.stat().st_mtime if PATH.exists() else None
        if mtime != _cache["mtime"]:
            text = _unescape(PATH.read_text(encoding="utf-8")) if mtime else ""
            sections = _sections(text)
            settings, report = _parse_settings(text, sections) if text else (dict(DEFAULTS), ["skill.md missing – defaults"])
            _cache.update(mtime=mtime, text=text, sections=sections, settings=settings, report=report)
            # apply pipeline settings so every build follows the current skill.md
            config.LOOKBACK_DAYS.clear()
            config.LOOKBACK_DAYS.update(settings["lookback_days"])
            config.MAX_FILE_CHARS = settings["max_file_chars"]
        return _cache


def settings():
    return _load()["settings"]


def report():
    c = _load()
    return {"path": str(PATH), "loaded": bool(c["text"]), "chars": len(c["text"]), "settings": c["settings"],
            "notes": c["report"], "sections": list(c["sections"].keys())}


def _get(name):
    return _load()["sections"].get(name, "")


CORE = ["10. How the bot uses the result", "Decision order for every unresolved request",
        "Escalate instead of guessing when", "Executive working hours", "Hard guardrails"]
PROCEDURES = {
    "transfer": (r"executive|insaan|human|agent|manager|senior|kisi se baat|transfer|connect kar", ["Live transfer procedure"]),
    "callback": (r"call ?back|wapas call|baad mein call|phone kar(na|iye|o)|call kar(na|iye|o)|contact kar", ["Callback request procedure"]),
    "meeting": (r"meeting|milna|visit|appointment|demo", ["Meeting request procedure"]),
}


def bot_instructions(user_text="", sticky=()):
    """Returns (text, procedures_loaded) for the bot prompt."""
    t = (user_text or "").lower()
    found = [k for k, (rx, _) in PROCEDURES.items() if re.search(rx, t)]
    names = list(CORE)
    for k in dict.fromkeys(found + list(sticky)):
        names += PROCEDURES[k][1]
    names += ["Voice wording examples", "Required write-back after transfer, callback or meeting flow"] if (found or sticky) else []
    body = "\n\n".join(x for x in (_get(n) for n in dict.fromkeys(names)) if x)
    return body, found


def work_hours():
    return settings()["work_hours"]
