"""Runtime voice actions from skill.md §11: live transfer, callback request, meeting request.

The guardrails are enforced here in code, not only in the prompt:
  * consent      – the caller's latest words must agree (or ask for it) before any action runs
  * hours        – live transfer only inside the executive window parsed from skill.md (09:00–19:00 IST)
  * honesty      – no live-transfer system is connected yet (§12), so transfer returns "unavailable";
                   callback / meeting are recorded as PREFERENCES awaiting confirmation, never as bookings
  * duplicates   – an open request of the same kind in the last 24 h is returned instead of a new one
  * identity     – unidentified callers can't have requests recorded against an account
  * do-not-call  – requests from a DO-NOT-CALL seller are recorded for policy review, not for outbound contact
Every attempt and its outcome is logged on the session and written back to the context file.
"""
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from context_layer import refresher, skill, store

IST = timezone(timedelta(hours=5, minutes=30))

TOOLS = [
    {"type": "function", "function": {
        "name": "transfer_to_executive",
        "description": "Connect the caller to a live IndiaMART executive. Only after the caller has clearly agreed to be connected now.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "Why a human is needed, in a few words"},
            "handoff_summary": {"type": "string", "description": "Role, intent, verified facts, what was tried, open question"},
            "caller_consented": {"type": "boolean"}}, "required": ["reason", "handoff_summary", "caller_consented"]}}},
    {"type": "function", "function": {
        "name": "request_callback",
        "description": "Record a callback request for an executive to call the caller back. Only after the caller agreed.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "Reason in the caller's own words"},
            "preferred_time": {"type": "string", "description": "Caller's preferred date/time or window, if given"},
            "caller_consented": {"type": "boolean"}}, "required": ["reason", "caller_consented"]}}},
    {"type": "function", "function": {
        "name": "request_meeting",
        "description": "Record a meeting request with an executive (purpose + preferred slot). Only after the caller agreed.",
        "parameters": {"type": "object", "properties": {
            "purpose": {"type": "string"},
            "preferred_time": {"type": "string"},
            "caller_consented": {"type": "boolean"}}, "required": ["purpose", "caller_consented"]}}},
]

_YES = re.compile(r"\b(haan|ha|han|yes|yeah|ok|okay|theek|thik|sure|kar do|kar dijiye|kariye|karo|please|zaroor|bilkul|chalega|"
                  r"connect|callback|call back|meeting|transfer)\b|हाँ|हां|ठीक|कर दो|करो|ज़रूर|जरूर|बिल्कुल|चलेगा", re.I)
_NO = re.compile(r"\b(nahi|nahin|no|mat|don't|dont|not now|abhi nahi)\b|नहीं|मत", re.I)


def in_hours(now=None):
    h1, m1, h2, m2 = skill.work_hours()
    t = (now or datetime.now(IST)).astimezone(IST)
    return (h1, m1) <= (t.hour, t.minute) < (h2, m2)


def _hours_label():
    h1, m1, h2, m2 = skill.work_hours()
    return f"{h1:02d}:{m1:02d}–{h2:02d}:{m2:02d} IST"


def _consented(args, user_text):
    t = user_text or ""
    return bool(args.get("caller_consented")) and bool(_YES.search(t)) and not (_NO.search(t) and not _YES.search(t))


def _open_request(glid, kind):
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    rows = store.query("SELECT payload FROM events WHERE glid=? AND type=? AND ts>=? ORDER BY ts DESC", (glid, kind, since))
    return rows[0]["payload"] if rows else None


def execute(session, name, args, user_text):
    """Run one tool call. Returns a JSON-able result the LLM must report truthfully."""
    rec = {"action": name, "at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"), "args": {k: v for k, v in args.items()
                                                                                          if k != "handoff_summary"}}
    if not _consented(args, user_text):
        res = {"status": "needs_consent", "say": "Ask the caller to confirm before doing this. Nothing has been done."}
    elif name == "transfer_to_executive":
        if not in_hours():
            res = {"status": "outside_hours", "hours": _hours_label(),
                   "say": "Executives are outside working hours. Offer a callback or meeting request instead. Do not say transferred."}
        else:
            res = {"status": "unavailable", "reason": "no live-transfer system is connected to this bot yet",
                   "say": "Live transfer is not available right now. Offer a callback or meeting request. Do not say transferred."}
    elif session.glid is None:
        res = {"status": "identity_unresolved",
               "say": "The caller's account could not be identified, so no request can be recorded. Explain the approved support route."}
    else:
        kind = "callback_request" if name == "request_callback" else "meeting_request"
        existing = _open_request(session.glid, kind)
        if existing:
            res = {"status": "duplicate", "reference": existing.get("reference"), "preferred_time": existing.get("preferred_time"),
                   "say": "A request already exists; tell the caller it is already recorded (not confirmed). Do not create another."}
        else:
            dnc = any("do-not-call" in i.lower() for i in session.parsed["sections"].get("Handle with care", {}).get("items", []))
            ref = ("CB-" if kind == "callback_request" else "MT-") + uuid.uuid4().hex[:6].upper()
            payload = {"reference": ref, "reason": (args.get("reason") or args.get("purpose") or "")[:140],
                       "preferred_time": (args.get("preferred_time") or "")[:60], "status": "requested_unconfirmed",
                       "channel": session.channel, "session_id": session.id, "in_hours": in_hours(),
                       "contact_restriction": "do_not_call – needs policy review" if dnc else ""}
            refresher.ingest(session.glid, "bot_actions", kind, payload, role=session.role)
            res = {"status": "recorded_unconfirmed", "reference": ref, "preferred_time": payload["preferred_time"] or None,
                   "confirmed": False,
                   "say": ("Request recorded as a PREFERENCE; the team must confirm the actual slot. Never call it booked or fixed."
                           + (" The account has a do-not-call restriction: say the team will review it." if dnc else ""))}
    rec["result"] = res["status"]
    if res.get("reference"):
        rec["reference"] = res["reference"]
    session.actions.append(rec)
    return res


# Claims of a CONFIRMED outcome. No connected system can confirm a transfer, booking or slot yet (skill.md §12),
# so these are always false today.
CLAIM_CONFIRMED = re.compile(
    r"transfer kar (diya|di)|connect kar (diya|di)|transferred|connected you|book(ed| kar (diya|di|li))|"
    r"(meeting|callback|slot|appointment) (fix|confirm|book)\w*|confirm(ed)? (the |your )?(meeting|callback|slot)|"
    r"ट्रांसफर कर दिया|कनेक्ट कर दिया|बुक कर (दी|दिया|ली)|(मीटिंग|कॉलबैक) (फिक्स|कन्फर्म)", re.I)
# Claims that a request was recorded / raised: true only if a tool recorded it this turn (or it already existed).
CLAIM_RAISED = re.compile(r"request (raise|record|darj|note) kar|raised (a|the|your) request|request (has been )?(raised|recorded|submitted)|"
                          r"रिक्वेस्ट (दर्ज|रिकॉर्ड|रेज़)", re.I)


def unsupported_claim(text, turn_results):
    if CLAIM_CONFIRMED.search(text or ""):
        return True
    if CLAIM_RAISED.search(text or ""):
        return not ({"recorded_unconfirmed", "duplicate"} & set(turn_results))
    return False
